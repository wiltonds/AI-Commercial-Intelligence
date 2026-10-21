"""
enriquecer_cnpj.py — Dá nome aos CNPJs que chegam aos sinais sem nome (ex.: CNO).

Consulta o cadastro público da Receita (BrasilAPI / Minha Receita, grátis) só
para CNPJs ainda não consultados e grava data/processed/CNPJ_NOMES.csv.
Roda no GitHub Actions todo dia, depois das coletas; leva segundos quando não
há CNPJ novo.

Uso:
    python jobs/enriquecer_cnpj.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.sinais.consolidar import carregar_todos_sinais  # noqa: E402
from src.sinais.fontes import registrar_execucao  # noqa: E402
from src.sinais.nomes_cnpj import ARQ_NOMES, carregar_nomes, cnpjs_sem_nome, enriquecer  # noqa: E402

FONTE_ID = "cnpj_nomes"


def main():
    import requests

    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (Radar de Oportunidades SENAI-AL)"
    try:
        alvo = cnpjs_sem_nome(carregar_todos_sinais())
        antes = carregar_nomes()
        depois = enriquecer(alvo, antes, s, date.today())
        depois.to_csv(ARQ_NOMES, index=False, encoding="utf-8-sig")
    except Exception as erro:
        registrar_execucao(FONTE_ID, "falha", 0, f"{type(erro).__name__}: {erro}")
        raise
    novos = len(depois) - len(antes)
    com_nome = int(depois["razao_social"].astype(str).str.strip().ne("").sum())
    faltam = len(set(alvo) - set(depois["cnpj"]))
    registrar_execucao(FONTE_ID, "sucesso", novos,
                       f"{novos} CNPJs consultados agora; {com_nome} com nome no cadastro; {faltam} para a próxima")
    print(f"Pronto: {novos} consultados, {com_nome} com nome, {faltam} pendentes.")


if __name__ == "__main__":
    main()
