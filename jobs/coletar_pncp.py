"""
coletar_pncp.py — Job de sinais "venceu licitação" (PNCP).

Fluxo de uma execução:
  1. para cada dia da janela (padrão 90 dias), consulta /v1/contratos
     da API pública do PNCP, todas as páginas
  2. guarda só os contratos de órgãos de AL num cache por dia
     (data/raw/pncp/AAAAMMDD.json) — dia já baixado não é baixado de novo,
     exceto os últimos 2 dias, que ainda recebem publicações
  3. filtra o recorte construção (obra / serviço de engenharia)
  4. gera uma linha por (CNPJ fornecedor, contrato), pontua e cruza com a
     Base Mestre pelo CNPJ raiz
  5. grava data/processed/SINAIS_PNCP.csv e registra no LOG_FONTES.csv

Uso:
    python jobs/coletar_pncp.py                 # janela do fontes.yaml
    python jobs/coletar_pncp.py --dias 30       # janela menor (teste)
    python jobs/coletar_pncp.py --so-cache      # reprocessa sem internet

A PRIMEIRA execução baixa a janela inteira (o PNCP publica milhares de
contratos por dia no Brasil todo e a API não filtra UF): pode levar de
vários minutos a meia hora. As seguintes baixam só os dias novos.

Agendamento: 1x/dia, no mesmo .bat do CNO.
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from time import sleep

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.sinais.fontes import carregar_catalogo, registrar_execucao  # noqa: E402
from src.sinais.pncp import (  # noqa: E402
    cruzar_com_base,
    extrair_sinais,
    filtrar_recentes,
    normalizar_contratos,
    pontuar,
    recorte_construcao,
    so_uf,
)

RAIZ = Path(__file__).resolve().parent.parent
PASTA_CACHE = RAIZ / "data" / "raw" / "pncp"
ARQ_SAIDA = RAIZ / "data" / "processed" / "SINAIS_PNCP.csv"
FONTE_ID = "pncp"
URL_API = "https://pncp.gov.br/api/consulta/v1/contratos"
TAMANHO_PAGINA = 500      # teto do endpoint de contratos
DIAS_RECARREGAR = 2       # hoje e ontem ainda recebem publicações
TENTATIVAS = 4
ESPERA_SEG = 10
PAUSA_ENTRE_PAGINAS = 0.3

COLUNAS_SAIDA = [
    "score_momento", "cnpj_basico", "cnpj", "razao_social", "na_base_mestre",
    "STATUS_RELACIONAMENTO_REAL", "Porte", "CNAE PRIMARIO",
    "tipo_sinal", "descricao", "orgao", "objeto", "categoria", "valor",
    "municipio", "data_evento", "data_publicacao", "data_vigencia_fim",
    "idade_dias", "peso", "validade_dias", "numero_controle", "url_fonte", "fonte",
]


def _get(sessao: requests.Session, params: dict, avisar=print) -> dict:
    ultimo = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            r = sessao.get(URL_API, params=params, timeout=90)
            if r.status_code == 204:          # sem registros no dia
                return {"data": [], "totalPaginas": 0}
            r.raise_for_status()
            if "json" not in r.headers.get("content-type", ""):
                raise ValueError("resposta não é JSON (portal fora do ar ou bloqueio)")
            return r.json()
        except (requests.RequestException, ValueError) as erro:
            ultimo = erro
            avisar(f"  tentativa {tentativa}/{TENTATIVAS} falhou: {erro}")
            if tentativa < TENTATIVAS:
                sleep(ESPERA_SEG * tentativa)
    raise RuntimeError(f"PNCP não respondeu ({ultimo})")


def baixar_dia(dia: date, uf: str, sessao: requests.Session, avisar=print) -> list[dict]:
    """Todas as páginas de um dia, devolvendo só os contratos da UF."""
    d = dia.strftime("%Y%m%d")
    guardados, pagina, total = [], 1, 1
    while pagina <= total:
        resp = _get(sessao, {"dataInicial": d, "dataFinal": d, "pagina": pagina,
                             "tamanhoPagina": TAMANHO_PAGINA}, avisar)
        guardados += so_uf(resp.get("data") or [], uf)
        total = int(resp.get("totalPaginas") or 0)
        pagina += 1
        sleep(PAUSA_ENTRE_PAGINAS)
    return guardados


def carregar_janela(
    hoje: date, janela: int, uf: str, so_cache: bool = False, avisar=print,
    pasta: Path = PASTA_CACHE, baixar=baixar_dia,
) -> list[dict]:
    pasta.mkdir(parents=True, exist_ok=True)
    sessao = requests.Session()
    sessao.headers.update({"Accept": "application/json",
                           "User-Agent": "Mozilla/5.0 (Inteligencia Comercial FIEA)"})
    registros, baixados = [], 0
    for n in range(janela, -1, -1):
        dia = hoje - timedelta(days=n)
        arq = pasta / f"{dia:%Y%m%d}.json"
        recente = n < DIAS_RECARREGAR
        if arq.exists() and (not recente or so_cache):
            registros += json.loads(arq.read_text(encoding="utf-8"))
            continue
        if so_cache:
            continue
        do_dia = baixar(dia, uf, sessao, avisar)
        arq.write_text(json.dumps(do_dia, ensure_ascii=False), encoding="utf-8")
        registros += do_dia
        baixados += 1
        avisar(f"  {dia:%d/%m/%Y}: {len(do_dia)} contratos de {uf}")
    avisar(f"Dias baixados agora: {baixados} | lidos do cache: {janela + 1 - baixados}")
    return registros


def carregar_empresas() -> pd.DataFrame:
    # mesma Base Mestre consolidada por CNPJ raiz usada pelo CNO
    from jobs.coletar_cno import carregar_empresas as _base
    return _base()


def rodar(hoje: date, dias: int | None = None, so_cache: bool = False,
          avisar=print) -> pd.DataFrame:
    cfg = carregar_catalogo()[FONTE_ID]
    regra = cfg["sinal"]
    janela = int(dias or regra.get("janela_coleta_dias", 90))
    uf = str(cfg.get("uf", "AL"))

    avisar(f"Consultando contratos do PNCP ({janela} dias, órgãos de {uf}) ...")
    brutos = carregar_janela(hoje, janela, uf, so_cache=so_cache, avisar=avisar)
    contratos = normalizar_contratos(brutos)
    avisar(f"Contratos de {uf} na janela: {len(contratos):,}")
    if contratos.empty:
        raise RuntimeError("Nenhum contrato retornado — verifique a conexão ou a API.")

    obras = contratos[recorte_construcao(contratos, cfg.get("recorte", {}))]
    avisar(f"No recorte construção: {len(obras):,}")

    recentes = filtrar_recentes(obras, hoje, janela)
    sinais = extrair_sinais(recentes)
    sinais = pontuar(sinais, hoje, regra)
    sinais = cruzar_com_base(sinais, carregar_empresas())

    saida = sinais[[c for c in COLUNAS_SAIDA if c in sinais.columns]]
    ARQ_SAIDA.parent.mkdir(parents=True, exist_ok=True)
    saida.to_csv(ARQ_SAIDA, index=False, encoding="utf-8-sig")

    na_base = int(saida.loc[saida["na_base_mestre"], "cnpj_basico"].nunique())
    avisar(f"Salvo: {ARQ_SAIDA.name}")
    avisar(f"Sinais (CNPJ x contrato): {len(saida):,} | empresas distintas: "
           f"{saida['cnpj_basico'].nunique():,} | já na Base Mestre: {na_base:,}")
    return saida


def executar(hoje: date | None = None, dias: int | None = None,
             so_cache: bool = False, avisar=print) -> pd.DataFrame:
    """Roda e registra no LOG_FONTES (sucesso ou falha)."""
    hoje = hoje or date.today()
    try:
        saida = rodar(hoje, dias, so_cache, avisar)
    except Exception as erro:
        registrar_execucao(FONTE_ID, "falha", 0, f"{type(erro).__name__}: {erro}")
        raise
    registrar_execucao(FONTE_ID, "sucesso", len(saida),
                       f"{saida['cnpj_basico'].nunique()} empresas")
    return saida


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dias", type=int, help="janela em dias (padrão: fontes.yaml)")
    parser.add_argument("--so-cache", action="store_true", help="não acessa a internet")
    parser.add_argument("--hoje", help="data de referência AAAA-MM-DD (testes)")
    args = parser.parse_args()
    hoje = date.fromisoformat(args.hoje) if args.hoje else date.today()
    executar(hoje, args.dias, args.so_cache)


if __name__ == "__main__":
    main()
