"""
padronizar_municipios.py — Uma grafia só para cada município de Alagoas nos arquivos de dados.

Em todos os CSVs de data/processed e data/contatos, em toda coluna de
município, troca a grafia pela oficial (src/tools/municipios.py). O painel
também padroniza ao carregar; este job deixa os próprios arquivos limpos,
para quem usa os CSVs fora do painel (Excel, Power BI).

O publicar_dados.ps1 chama este job antes de publicar.

Uso:
    python jobs/padronizar_municipios.py            # corrige os arquivos
    python jobs/padronizar_municipios.py --conferir # só mostra o que mudaria
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.tools.municipios import OFICIAL, colunas_municipio, padronizar  # noqa: E402

PASTAS = [RAIZ / "data" / "processed", RAIZ / "data" / "contatos"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--conferir", action="store_true", help="só mostra, não grava")
    a = ap.parse_args()
    assert len(OFICIAL) == 102, "lista de municípios incompleta"

    total = 0
    for pasta in PASTAS:
        for arq in sorted(pasta.glob("*.csv")):
            cols = colunas_municipio(pd.read_csv(arq, nrows=0, encoding="utf-8-sig").columns)
            if not cols:
                continue
            df = pd.read_csv(arq, dtype=str, keep_default_na=False, encoding="utf-8-sig", low_memory=False)
            mudou = 0
            for c in cols:
                novo = padronizar(df[c])
                mudou += int((novo != df[c]).sum())
                df[c] = novo
            if mudou:
                total += mudou
                print(f"  {arq.relative_to(RAIZ)}: {mudou:,} células corrigidas".replace(",", "."))
                if not a.conferir:
                    df.to_csv(arq, index=False, encoding="utf-8-sig")
    acao = "a corrigir" if a.conferir else "corrigidas"
    print(f"Municípios padronizados: {total:,} células {acao}.".replace(",", "."))


if __name__ == "__main__":
    main()
