"""
coletar_bndes.py — Financiamentos do BNDES contratados por empresas de AL.

Baixa do portal de dados abertos do BNDES o arquivo de operações (diretas e
indiretas não automáticas), fica com as empresas privadas de AL dos últimos 24
meses e grava data/processed/SINAIS_BNDES.csv, ligado à base pelo CNPJ.

O BNDES atualiza mensalmente; o GitHub Actions roda às segundas.

Uso:
    python jobs/coletar_bndes.py
    python jobs/coletar_bndes.py --arquivo operacoes.csv     # arquivo baixado à mão
    python jobs/coletar_bndes.py --automaticas               # inclui as automáticas (arquivo grande)
"""
from __future__ import annotations

import argparse
import io
import sys
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.sinais.bndes import API_CKAN, achar_recursos, ler_operacoes, para_sinais  # noqa: E402
from src.sinais.fontes import registrar_execucao  # noqa: E402
from src.sinais.noticias import carregar_empresas  # noqa: E402

FONTE_ID = "bndes"
SAIDA = RAIZ / "data" / "processed" / "SINAIS_BNDES.csv"


def _conteudos(arquivo: str | None, automaticas: bool):
    if arquivo:
        yield Path(arquivo).read_bytes()
        return
    import requests

    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (Radar de Oportunidades SENAI-AL)"
    pacote = s.get(API_CKAN, timeout=60).json()
    urls = achar_recursos(pacote, automaticas)
    if not urls:
        raise RuntimeError("nenhum arquivo de operações encontrado no pacote do BNDES")
    for url in urls:
        print(f"  baixando {url.rsplit('/', 1)[-1]} ...")
        r = s.get(url, timeout=600)
        r.raise_for_status()
        if url.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                for nome in z.namelist():
                    if nome.lower().endswith(".csv"):
                        yield z.read(nome)
        else:
            yield r.content


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo")
    ap.add_argument("--automaticas", action="store_true")
    a = ap.parse_args()
    try:
        ops = pd.concat([ler_operacoes(c) for c in _conteudos(a.arquivo, a.automaticas)], ignore_index=True)
        sinais = para_sinais(ops, carregar_empresas(), date.today())
        sinais.to_csv(SAIDA, index=False, encoding="utf-8-sig")
    except Exception as erro:
        registrar_execucao(FONTE_ID, "falha", 0, f"{type(erro).__name__}: {erro}")
        raise
    n_emp = sinais["cnpj_basico"].nunique() if not sinais.empty else 0
    registrar_execucao(FONTE_ID, "sucesso", len(sinais), f"{n_emp} empresas de AL com financiamento em 24 meses")
    print(f"Pronto: {len(sinais)} operações, {n_emp} empresas de AL.")


if __name__ == "__main__":
    main()
