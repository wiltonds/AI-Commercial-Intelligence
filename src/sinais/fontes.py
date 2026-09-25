"""Catálogo de fontes externas + log de execução + semáforo de frescor.

Nasceu de um problema concreto: as tabelas fontes_externas.* do DW
pararam de atualizar e ninguém percebeu. Aqui cada job registra quando
rodou com sucesso, e a página "Saúde das Fontes" compara isso com a
frequência esperada de cada fonte (config/fontes.yaml).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

RAIZ = Path(__file__).resolve().parents[2]
ARQ_CATALOGO = RAIZ / "config" / "fontes.yaml"
ARQ_LOG = RAIZ / "data" / "processed" / "LOG_FONTES.csv"

COLUNAS_LOG = ["fonte", "executado_em", "status", "linhas", "mensagem"]


def carregar_catalogo(caminho: Path = ARQ_CATALOGO) -> dict:
    with open(caminho, encoding="utf-8") as f:
        return yaml.safe_load(f)["fontes"]


def registrar_execucao(
    fonte: str, status: str, linhas: int = 0, mensagem: str = "",
    caminho: Path | None = None,
) -> None:
    caminho = caminho or ARQ_LOG
    caminho.parent.mkdir(parents=True, exist_ok=True)
    linha = pd.DataFrame([{
        "fonte": fonte,
        "executado_em": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "linhas": linhas,
        "mensagem": mensagem[:500],
    }])
    linha.to_csv(
        caminho, mode="a", header=not caminho.exists(), index=False,
        encoding="utf-8-sig",
    )


def carregar_log(caminho: Path | None = None) -> pd.DataFrame:
    caminho = caminho or ARQ_LOG
    if not caminho.exists():
        return pd.DataFrame(columns=COLUNAS_LOG)
    return pd.read_csv(caminho, dtype=str).fillna("")


def saude_das_fontes(
    catalogo: dict, log: pd.DataFrame, agora: datetime | None = None
) -> pd.DataFrame:
    """Uma linha por fonte com o semáforo.

    🟢 último sucesso dentro da frequência esperada (+ 1 dia de folga)
    🟡 atrasada até 3x a frequência
    🔴 atrasada além disso, ou última execução falhou
    ⚪ ainda não implementada / nunca rodou
    """
    agora = agora or datetime.now(timezone.utc)
    linhas = []

    for fonte_id, cfg in catalogo.items():
        registros = log[log["fonte"] == fonte_id]
        sucessos = registros[registros["status"] == "sucesso"]
        ultimo = registros.iloc[-1] if len(registros) else None
        ultimo_ok = (
            pd.to_datetime(sucessos["executado_em"], utc=True).max()
            if len(sucessos) else None
        )
        freq = int(cfg.get("frequencia_dias", 30))

        if cfg.get("status") != "implementado" or ultimo is None:
            semaforo = "⚪"
            atraso = None
        elif ultimo["status"] != "sucesso":
            semaforo = "🔴"
            atraso = (agora - ultimo_ok).days if ultimo_ok is not None else None
        else:
            atraso = (agora - ultimo_ok).days
            semaforo = "🟢" if atraso <= freq + 1 else ("🟡" if atraso <= 3 * freq else "🔴")

        linhas.append({
            "semaforo": semaforo,
            "fonte": fonte_id,
            "nome": cfg.get("nome", fonte_id),
            "modulo": cfg.get("modulo", ""),
            "granularidade": cfg.get("granularidade", ""),
            "status": cfg.get("status", ""),
            "frequencia_dias": freq,
            "ultimo_sucesso": ultimo_ok.strftime("%d/%m/%Y %H:%M") if ultimo_ok is not None else "",
            "dias_desde_sucesso": atraso,
            "ultima_mensagem": "" if ultimo is None else ultimo["mensagem"],
            "tabela_dw": cfg.get("tabela_dw", ""),
            "link": cfg.get("url_pagina") or cfg.get("url_download") or cfg.get("url_api") or "",
        })

    return pd.DataFrame(linhas)
