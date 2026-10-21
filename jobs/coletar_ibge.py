"""
coletar_ibge.py — Indicadores econômicos dos 102 municípios de AL (IBGE/SIDRA).

Grava data/processed/INDICADORES_MUNICIPIOS.csv com PIB, VAB da indústria,
peso da indústria na economia local e população. O IBGE atualiza uma vez por
ano; o job pode rodar toda semana sem custo (só baixa se a fonte respondeu).

Uso:
    python jobs/coletar_ibge.py
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.sinais.fontes import registrar_execucao  # noqa: E402
from src.sinais.ibge import baixar_indicadores  # noqa: E402

FONTE_ID = "ibge_sidra"
SAIDA = RAIZ / "data" / "processed" / "INDICADORES_MUNICIPIOS.csv"


def main():
    try:
        df = baixar_indicadores()
        if len(df) < 100:
            raise RuntimeError(f"só {len(df)} municípios retornados")
        df.to_csv(SAIDA, index=False, encoding="utf-8-sig")
    except Exception as erro:
        registrar_execucao(FONTE_ID, "falha", 0, f"{type(erro).__name__}: {erro}")
        raise
    registrar_execucao(FONTE_ID, "sucesso", len(df), f"PIB {df['ano_pib_mil'].iloc[0]}, população {df['ano_populacao'].iloc[0]}")
    print(f"Pronto: {len(df)} municípios em {SAIDA.name}")


if __name__ == "__main__":
    main()
