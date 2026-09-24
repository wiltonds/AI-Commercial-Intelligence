"""
checar_situacao_cadastral.py — Job diário de checagem rotativa de baixa.

Problema que resolve: hoje a única forma de saber que uma empresa saiu
do universo (foi baixada, ficou inapta/suspensa) é esperar a próxima
extração mensal completa da Receita Federal. Este job fecha esse
intervalo, checando individualmente as empresas já cadastradas contra
uma API pública, bem mais rápido que esperar o próximo mês.

Por que "rotativo" e não "todo mundo, todo dia": a Receita Federal só
publica o dataset nacional completo uma vez por mês — não existe dado
novo pra buscar todo dia. E a API pública usada aqui (ReceitaWS, sem
chave) tem limite documentado de ~3 consultas/minuto — checar as
13.978 empresas do universo atual em um dia só não é viável.

Este job, então, checa uma FATIA por execução — sempre a que está há
mais tempo sem checagem (ou nunca checada) — e guarda o resultado num
arquivo de estado. Rodando diariamente, o universo inteiro é revisado
a cada ~28 dias (com o tamanho de lote padrão), e qualquer mudança de
situação cadastral é sinalizada no dia em que a empresa é checada, sem
esperar o ciclo fechar.

Detecção validada manualmente contra um CNPJ já conhecido como INAPTA
na base de auditoria (data/processed/AUDITORIA_RECEITA_GAP_INDUSTRIA.csv)
antes deste job existir — a API confirmou a situação corretamente.

Saída: data/processed/MONITORAMENTO_SITUACAO_CADASTRAL.csv — uma linha
por CNPJ raiz do universo, com a situação mais recente conhecida e se
mudou desde a última checagem. Serve de fonte para a página "Auditoria
de Cobertura" do dashboard e, futuramente, para a tabela equivalente no
Data Warehouse.

Uso:
    python jobs/checar_situacao_cadastral.py                  # roda o lote padrão (500)
    python jobs/checar_situacao_cadastral.py --lote 100        # lote menor (roda mais rápido, ciclo mais longo)
    python jobs/checar_situacao_cadastral.py --delay 21        # segundos entre consultas (padrão respeita ~3/min)

Agendamento: pensado para rodar 1x/dia (Agendador de Tarefas do Windows,
cron, ou o scheduler que o time do Observatório definir no DW). Este
script não agenda a si mesmo — só faz o trabalho de uma execução.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import sleep

import pandas as pd
import requests

# Permite rodar como "python jobs/checar_situacao_cadastral.py" direto
# (por um agendador, por exemplo), sem depender de "python -m".
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.company_data import BASE_PATH
from src.tools.cnpj_raiz import consolidar_por_cnpj_raiz

ARQ_MONITORAMENTO = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "processed"
    / "MONITORAMENTO_SITUACAO_CADASTRAL.csv"
)

RECEITAWS_URL = "https://www.receitaws.com.br/v1/cnpj/{cnpj}"

LOTE_PADRAO = 500
DELAY_PADRAO = 21  # segundos; ReceitaWS gratuita documenta ~3 consultas/min


def carregar_universo() -> pd.DataFrame:
    """Uma linha por empresa (CNPJ raiz), reaproveitando o motor já testado."""

    df = pd.read_csv(BASE_PATH, dtype=str, low_memory=False)
    df["cnpj"] = df["cnpj"].str.replace(r"\D", "", regex=True).str.zfill(14)

    empresas = consolidar_por_cnpj_raiz(df)

    return empresas[["CNPJ_BASICO", "cnpj", "razao_social", "situacao_atual"]].rename(
        columns={"situacao_atual": "situacao_conhecida"}
    )


def carregar_monitoramento(universo: pd.DataFrame) -> pd.DataFrame:
    """Carrega o estado anterior, ou inicializa um novo a partir do universo."""

    # "ultima_checagem" fica como texto (ISO) o tempo todo — evita conflito
    # de fuso horário entre o que o pandas infere ao ler o CSV e o que este
    # script escreve (datetime.now(timezone.utc).isoformat()).
    if ARQ_MONITORAMENTO.exists():
        estado = pd.read_csv(ARQ_MONITORAMENTO, dtype=str).fillna("")

        # Empresas novas no universo (nunca vistas por este job) entram agora.
        novas = universo[~universo["CNPJ_BASICO"].isin(estado["CNPJ_BASICO"])].copy()
        if len(novas):
            novas["situacao_atual"] = novas["situacao_conhecida"]
            novas["ultima_checagem"] = ""
            novas["mudou_status"] = "NAO"
            novas["data_deteccao_mudanca"] = ""
            estado = pd.concat(
                [estado, novas.drop(columns=["situacao_conhecida"])],
                ignore_index=True,
            )

        return estado

    inicial = universo.copy()
    inicial["situacao_atual"] = inicial["situacao_conhecida"]
    inicial["ultima_checagem"] = ""
    inicial["mudou_status"] = "NAO"
    inicial["data_deteccao_mudanca"] = ""

    return inicial.drop(columns=["situacao_conhecida"])


def escolher_lote(estado: pd.DataFrame, tamanho: int) -> pd.DataFrame:
    """Prioriza quem nunca foi checado, depois quem está há mais tempo sem checagem."""

    chave_ordenacao = pd.to_datetime(estado["ultima_checagem"], errors="coerce")
    ordenado = estado.loc[chave_ordenacao.sort_values(na_position="first").index]

    return ordenado.head(tamanho)


def consultar_receita(cnpj: str) -> str | None:
    """Retorna a situação cadastral atual, ou None se a consulta falhar."""

    try:
        resposta = requests.get(
            RECEITAWS_URL.format(cnpj=cnpj), timeout=15
        )
    except requests.RequestException as erro:
        print(f"  [erro de rede] {cnpj}: {erro}")
        return None

    if resposta.status_code == 429:
        print(f"  [limite excedido] {cnpj} — pausando 60s")
        sleep(60)
        return consultar_receita(cnpj)

    if resposta.status_code != 200:
        print(f"  [http {resposta.status_code}] {cnpj}")
        return None

    dados = resposta.json()

    if dados.get("status") == "ERROR":
        print(f"  [nao encontrado na Receita] {cnpj}: {dados.get('message')}")
        return None

    return dados.get("situacao")


def rodar(tamanho_lote: int, delay: float) -> None:
    universo = carregar_universo()
    estado = carregar_monitoramento(universo)

    lote = escolher_lote(estado, tamanho_lote)

    print(f"Universo atual: {len(universo):,} empresas")
    print(f"Checando lote de {len(lote):,} empresas nesta execução")
    print(f"Tempo estimado: {len(lote) * delay / 60:.0f} minutos\n")

    mudancas = []

    for i, (indice, linha) in enumerate(lote.iterrows(), start=1):
        cnpj = linha["cnpj"]
        situacao_anterior = linha["situacao_atual"]

        situacao_nova = consultar_receita(cnpj)

        agora = datetime.now(timezone.utc).isoformat()
        estado.loc[indice, "ultima_checagem"] = agora

        if situacao_nova is None:
            print(f"[{i}/{len(lote)}] {cnpj} — consulta falhou, mantém situação anterior")
        else:
            estado.loc[indice, "situacao_atual"] = situacao_nova

            if situacao_nova != situacao_anterior:
                estado.loc[indice, "mudou_status"] = "SIM"
                estado.loc[indice, "data_deteccao_mudanca"] = agora
                mudancas.append(
                    (cnpj, linha["razao_social"], situacao_anterior, situacao_nova)
                )
                print(
                    f"[{i}/{len(lote)}] {cnpj} — MUDOU: "
                    f"{situacao_anterior} -> {situacao_nova}"
                )
            else:
                print(f"[{i}/{len(lote)}] {cnpj} — sem mudança ({situacao_nova})")

        if i < len(lote):
            sleep(delay)

    ARQ_MONITORAMENTO.parent.mkdir(parents=True, exist_ok=True)
    estado.to_csv(ARQ_MONITORAMENTO, index=False, encoding="utf-8-sig")

    print(f"\nSalvo: {ARQ_MONITORAMENTO}")
    print(f"Checadas nesta execução: {len(lote):,}")
    print(f"Mudanças de situação detectadas: {len(mudancas)}")

    for cnpj, razao_social, antes, depois in mudancas:
        print(f"  - {cnpj} ({razao_social}): {antes} -> {depois}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lote", type=int, default=LOTE_PADRAO,
        help=f"Quantas empresas checar nesta execução (padrão: {LOTE_PADRAO})",
    )
    parser.add_argument(
        "--delay", type=float, default=DELAY_PADRAO,
        help=f"Segundos entre consultas (padrão: {DELAY_PADRAO}, ~3/min)",
    )
    args = parser.parse_args()

    rodar(args.lote, args.delay)


if __name__ == "__main__":
    main()
