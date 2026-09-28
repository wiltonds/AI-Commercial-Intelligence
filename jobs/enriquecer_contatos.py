"""
enriquecer_contatos.py — Preenche o cadastro de contatos da Base Mestre.

Consulta cada CNPJ UMA vez no cadastro da Receita (BrasilAPI) e salva em
data/contatos/CONTATOS_EMPRESAS.csv: telefones, e-mail, endereço, CNAE
principal e secundários, sócios e o decisor provável.

Ordem de prioridade (o que é mais útil primeiro):
  1. empresas com sinal ativo (qualquer data/processed/SINAIS_*.csv)
  2. resto da Base Mestre, das maiores para as menores (porte)
Quem já tem contato com menos de --validade dias é pulado.

Uso:
    python jobs/enriquecer_contatos.py --limite 20      # teste rápido
    python jobs/enriquecer_contatos.py                  # lote padrão (300)
    python jobs/enriquecer_contatos.py --so-sinais      # só quem tem sinal

Rodando 1x/dia com o lote padrão, as 13.978 empresas ficam cobertas em
cerca de 7 semanas — as com sinal, já no primeiro dia.

Privacidade (LGPD): o arquivo tem nome de sócio e contato. Ele fica em
data/contatos/, que NÃO vai para o Git. Não publique em repositório
público; na versão institucional, isso vai para o DW/CRM.
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from time import sleep

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.contatos import (  # noqa: E402
    ARQ_CONTATOS,
    COLUNAS,
    avaliar_qualidade,
    carregar_contatos,
    extrair_contato,
)

RAIZ = Path(__file__).resolve().parent.parent
URL_API = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
PORTE_ORDEM = {"DEMAIS": 0, "PEQUENO PORTE": 1, "MICRO EMPRESA": 2}


def carregar_universo() -> pd.DataFrame:
    """Base Mestre consolidada por CNPJ raiz (só depende de src/tools, que
    existe em todas as branches — o robô roda na master e na sinais-cno)."""
    from src.tools.cnpj_raiz import consolidar_por_cnpj_raiz
    from src.tools.company_data import BASE_PATH
    df = pd.read_csv(BASE_PATH, dtype=str, low_memory=False, encoding="utf-8-sig")
    df["cnpj"] = df["cnpj"].str.replace(r"\D", "", regex=True).str.zfill(14)
    df["POSSUI_SESI"] = df.get("TEM_SESI", "").astype(str).str.upper().eq("TRUE")
    df["POSSUI_SENAI"] = df.get("TEM_SENAI", "").astype(str).str.upper().eq("TRUE")
    df["POSSUI_SEBRAE"] = False
    emp = consolidar_por_cnpj_raiz(df)
    emp["cnpj_basico"] = emp["CNPJ_BASICO"].astype(str).str.zfill(8)
    return emp[["cnpj_basico", "cnpj", "razao_social", "Porte"]]


def cnpjs_com_sinal() -> set[str]:
    raizes = set()
    for arq in (RAIZ / "data" / "processed").glob("SINAIS_*.csv"):
        try:
            raizes |= set(pd.read_csv(arq, dtype=str, usecols=["cnpj_basico"])["cnpj_basico"].dropna())
        except (ValueError, KeyError):
            continue
    return raizes


def montar_fila(universo: pd.DataFrame, contatos: pd.DataFrame, com_sinal: set[str],
                validade_dias: int, so_sinais: bool = False, hoje: datetime | None = None) -> pd.DataFrame:
    hoje = hoje or datetime.now()
    fila = universo.copy()
    if not contatos.empty:
        atualizado = pd.to_datetime(contatos.set_index("cnpj_basico")["atualizado_em"], errors="coerce")
        recentes = set(atualizado[atualizado >= hoje - timedelta(days=validade_dias)].index)
        fila = fila[~fila["cnpj_basico"].isin(recentes)]
    fila["tem_sinal"] = fila["cnpj_basico"].isin(com_sinal)
    if so_sinais:
        fila = fila[fila["tem_sinal"]]
    fila["_porte"] = fila["Porte"].map(PORTE_ORDEM).fillna(3)
    return fila.sort_values(["tem_sinal", "_porte"], ascending=[False, True]).drop(columns="_porte")


def consultar(cnpj: str, sessao: requests.Session, tentativas: int = 4) -> dict | None:
    for tentativa in range(1, tentativas + 1):
        try:
            r = sessao.get(URL_API.format(cnpj=cnpj), timeout=30)
        except requests.RequestException as erro:
            print(f"  [rede] {cnpj}: {erro}")
            sleep(10 * tentativa)
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            print(f"  [não encontrado] {cnpj}")
            return None
        if r.status_code in (429, 403, 502, 503, 504):
            espera = int(r.headers.get("Retry-After") or 30 * tentativa)
            print(f"  [http {r.status_code}] {cnpj} — aguardando {espera}s")
            sleep(espera)
            continue
        print(f"  [http {r.status_code}] {cnpj}")
        return None
    return None


def salvar(contatos: pd.DataFrame) -> None:
    ARQ_CONTATOS.parent.mkdir(parents=True, exist_ok=True)
    avaliar_qualidade(contatos)[COLUNAS].to_csv(ARQ_CONTATOS, index=False, encoding="utf-8-sig")


def rodar(limite: int, delay: float, validade: int, so_sinais: bool) -> pd.DataFrame:
    contatos = carregar_contatos()
    fila = montar_fila(carregar_universo(), contatos, cnpjs_com_sinal(), validade, so_sinais).head(limite)
    print(f"Na fila agora: {len(fila)} empresas ({int(fila['tem_sinal'].sum())} com sinal)")

    sessao = requests.Session()
    sessao.headers.update({"User-Agent": "Mozilla/5.0 (Inteligencia Comercial FIEA)"})
    novos = []
    for i, linha in enumerate(fila.itertuples(), 1):
        dados = consultar(str(linha.cnpj).zfill(14), sessao)
        if dados:
            reg = extrair_contato(dados)
            reg["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
            novos.append(reg)
            print(f"  {i}/{len(fila)} {reg['razao_social'][:45]:45} "
                  f"tel: {reg['telefone_1'] or '-':16} decisor: {reg['decisor'] or '-'}")
        if i % 25 == 0 and novos:          # salva no caminho: se cair, não perde o lote
            contatos = _mesclar(contatos, novos)
            salvar(contatos)
            novos = []
        sleep(delay)

    contatos = _mesclar(contatos, novos)
    salvar(contatos)
    final = carregar_contatos()
    print(f"\nSalvo: {ARQ_CONTATOS.relative_to(RAIZ)}")
    print(f"Empresas com cadastro de contato: {len(final):,}")
    print(final["confianca"].value_counts().rename("confiança").to_string())
    return final


def _mesclar(contatos: pd.DataFrame, novos: list[dict]) -> pd.DataFrame:
    if not novos:
        return contatos
    return (pd.concat([contatos, pd.DataFrame(novos)], ignore_index=True)
            .drop_duplicates("cnpj_basico", keep="last").fillna(""))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limite", type=int, default=300, help="empresas por execução")
    parser.add_argument("--delay", type=float, default=1.5, help="segundos entre consultas")
    parser.add_argument("--validade", type=int, default=90, help="dias até reconsultar")
    parser.add_argument("--so-sinais", action="store_true", help="só empresas com sinal ativo")
    args = parser.parse_args()
    rodar(args.limite, args.delay, args.validade, args.so_sinais)


if __name__ == "__main__":
    main()
