"""Log de atualizações de dados — cada job grava aqui quando termina.

`jobs/checar_entradas.py` usa este log para dizer o que está em dia ou
vencido (a data do arquivo no disco não serve: o Git a muda a cada pull).
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

ARQ_LOG = Path(__file__).resolve().parents[2] / "data" / "processed" / "LOG_ATUALIZACOES.csv"
CAMPOS = ["entrada", "data", "resumo"]


def registrar(entrada: str, resumo: str = "", caminho: Path | None = None) -> None:
    caminho = Path(caminho or ARQ_LOG)            # lido na hora: os testes redirecionam ARQ_LOG
    caminho.parent.mkdir(parents=True, exist_ok=True)
    novo = not caminho.exists()
    with open(caminho, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        if novo:
            w.writeheader()
        w.writerow({"entrada": entrada, "data": datetime.now().isoformat(timespec="seconds"),
                    "resumo": str(resumo)[:300]})


def ultimas(caminho: Path | None = None) -> dict[str, dict]:
    caminho = Path(caminho or ARQ_LOG)
    if not caminho.exists():
        return {}
    ult: dict[str, dict] = {}
    with open(caminho, encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            ult[linha["entrada"]] = linha
    return ult
