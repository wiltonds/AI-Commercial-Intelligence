"""
coletar_bndes.py — Financiamentos do BNDES contratados por empresas de AL.

Baixa do portal de dados abertos do BNDES os arquivos de operações (não
automáticas e, com --automaticas, as feitas via bancos: FINAME/BNDES Máquinas,
giro etc.), fica com as empresas privadas de AL dos últimos 24 meses (uma linha
por empresa, com segmento: indústria, construção, comércio e serviços...) e grava
data/processed/SINAIS_BNDES.csv, ligado à base pelo CNPJ.

O BNDES atualiza mensalmente; o GitHub Actions roda às segundas.

Uso:
    python jobs/coletar_bndes.py
    python jobs/coletar_bndes.py --arquivo operacoes.csv     # arquivo baixado à mão
    python jobs/coletar_bndes.py --automaticas               # inclui as via bancos (arquivo grande, usado no Actions)
"""
from __future__ import annotations

import argparse
import sys
import tempfile
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


def _fontes(arquivo: str | None, automaticas: bool, pasta: Path):
    """(origem, caminho) de cada CSV. Baixa em streaming para o disco: o arquivo
    das automáticas tem centenas de MB e não cabe com folga na memória."""
    if arquivo:
        yield ("automática" if automaticas else "não automática"), Path(arquivo)
        return
    import requests

    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (Radar de Oportunidades SENAI-AL)"
    pacote = s.get(API_CKAN, timeout=60).json()
    urls = achar_recursos(pacote, automaticas)
    if not urls:
        raise RuntimeError("nenhum arquivo de operações encontrado no pacote do BNDES")
    for i, (origem, url) in enumerate(urls):
        destino = pasta / f"bndes_{i}{Path(url).suffix.lower() or '.csv'}"
        print(f"  baixando {url.rsplit('/', 1)[-1]} ({origem}) ...", flush=True)
        with s.get(url, timeout=1800, stream=True) as r:
            r.raise_for_status()
            with open(destino, "wb") as f:
                for parte in r.iter_content(chunk_size=1 << 20):
                    f.write(parte)
        print(f"    {destino.stat().st_size / 1e6:,.0f} MB", flush=True)
        if destino.suffix == ".zip":
            with zipfile.ZipFile(destino) as z:
                for nome in z.namelist():
                    if nome.lower().endswith(".csv"):
                        yield origem, Path(z.extract(nome, pasta))
        else:
            yield origem, destino


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo")
    ap.add_argument("--automaticas", action="store_true")
    a = ap.parse_args()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            ops = pd.concat([ler_operacoes(caminho, origem) for origem, caminho
                             in _fontes(a.arquivo, a.automaticas, Path(tmp))], ignore_index=True)
        sinais = para_sinais(ops, carregar_empresas(), date.today())
        sinais.to_csv(SAIDA, index=False, encoding="utf-8-sig")
    except Exception as erro:
        registrar_execucao(FONTE_ID, "falha", 0, f"{type(erro).__name__}: {erro}")
        raise
    n_emp = sinais["cnpj_basico"].nunique() if not sinais.empty else 0
    seg = sinais["segmento"].value_counts().to_dict() if not sinais.empty else {}
    resumo = ", ".join(f"{k} {v}" for k, v in seg.items())
    registrar_execucao(FONTE_ID, "sucesso", len(sinais), f"{n_emp} empresas de AL com financiamento em 24 meses ({resumo})")
    print(f"Pronto: {len(sinais)} operações, {n_emp} empresas de AL.")


if __name__ == "__main__":
    main()
