"""
coletar_noticias.py — Job diário do Radar: notícias da indústria de Alagoas.

Lê as consultas de config/radar.yaml no Google News (RSS público, grátis),
fica só com o que fala de AL com contexto empresarial, classifica o tema,
liga à empresa da base quando o nome aparece e grava
data/processed/SINAIS_NOTICIAS.csv (acumulando o histórico dos últimos meses).

Roda sozinho todo dia pelo GitHub Actions (.github/workflows/radar.yml).

Uso:
    python jobs/coletar_noticias.py
    python jobs/coletar_noticias.py --dias 30     # busca mais para trás (primeira carga)
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.sinais.fontes import registrar_execucao  # noqa: E402
from src.sinais.noticias import (  # noqa: E402
    baixar, carregar_config, carregar_empresas, juntar_historico, processar,
)

FONTE_ID = "noticias"
SAIDA = RAIZ / "data" / "processed" / "SINAIS_NOTICIAS.csv"


def executar(dias: int | None = None, hoje: date | None = None, avisar=print) -> pd.DataFrame:
    hoje = hoje or date.today()
    cfg = carregar_config()
    anterior = pd.read_csv(SAIDA, dtype=str, encoding="utf-8-sig") if SAIDA.exists() else pd.DataFrame()
    dias = dias or (cfg["janela_dias"] if not anterior.empty else cfg["primeira_carga_dias"])
    try:
        avisar(f"Buscando notícias dos últimos {dias} dias ({len(cfg['consultas'])} consultas) ...")
        noticias = baixar(cfg, dias, avisar=avisar)
        avisar(f"  {len(noticias)} notícias lidas; cruzando com a base ...")
        novos = processar(noticias, carregar_empresas(), cfg, hoje)
        saida = juntar_historico(novos, anterior, hoje, cfg["historico_dias"])
        SAIDA.parent.mkdir(parents=True, exist_ok=True)
        saida.to_csv(SAIDA, index=False, encoding="utf-8-sig")
    except Exception as erro:
        registrar_execucao(FONTE_ID, "falha", 0, f"{type(erro).__name__}: {erro}")
        raise
    com_empresa = int((novos.get("casamento", pd.Series(dtype=str)) == "por nome").sum()) if not novos.empty else 0
    registrar_execucao(FONTE_ID, "sucesso", len(saida),
                       f"{len(novos)} sinais novos ({com_empresa} ligados a empresa); {len(saida)} no histórico")
    avisar(f"Pronto: {len(novos)} sinais nesta coleta, {com_empresa} ligados a empresa da base; "
           f"{len(saida)} no histórico.")
    return saida


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dias", type=int, help="janela de busca em dias (padrão: config/radar.yaml)")
    a = ap.parse_args()
    executar(a.dias)


if __name__ == "__main__":
    main()
