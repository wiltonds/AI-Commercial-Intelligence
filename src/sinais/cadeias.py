"""Cadeias produtivas de AL: produção do campo (IBGE) × indústria que processa (base).

Responde "onde está a oportunidade" por cadeia (bacia leiteira, cana, coco, ...):
municípios com produção forte, quantas indústrias da cadeia existem ali, quantas já
atendemos e quantos sinais de mercado recentes. Configuração em config/cadeias.yaml.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from src.sinais.ibge import ler_sidra

RAIZ = Path(__file__).resolve().parents[2]
ARQ_CADEIAS = RAIZ / "config" / "cadeias.yaml"
ARQ_PRODUCAO = RAIZ / "data" / "processed" / "CADEIAS_PRODUCAO.csv"
API = ("https://apisidra.ibge.gov.br/values/t/{tabela}/n6/in%20n3%2027/v/{variavel}"
       "/p/last%202/c{classificacao}/{categoria}")


def carregar_cadeias(caminho: Path = ARQ_CADEIAS) -> dict:
    with open(caminho, encoding="utf-8") as f:
        return yaml.safe_load(f)["cadeias"]


def baixar_producao(cadeias: dict, sessao=None) -> pd.DataFrame:
    import requests

    sessao = sessao or requests.Session()
    partes = []
    for cid, c in cadeias.items():
        r = sessao.get(API.format(**c["producao"]), timeout=60)
        r.raise_for_status()
        df = ler_sidra(r.json(), "producao").rename(columns={"ano_producao": "ano"})
        df["cadeia"], df["unidade"] = cid, c["producao"]["unidade"]
        partes.append(df)
    return pd.concat(partes, ignore_index=True)


def industrias_da_cadeia(ind: pd.DataFrame, prefixos: list[str]) -> pd.DataFrame:
    cnae = ind["cnae"].fillna("").astype(str)
    return ind[cnae.str[:4].isin([str(p)[:4] for p in prefixos])]


def resumo_cadeia(cid: str, cfg: dict, ind: pd.DataFrame, producao: pd.DataFrame,
                  sinais: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por município: produção, indústrias da cadeia, clientes, sinais (90 dias)."""
    prod = producao[producao["cadeia"] == cid][["municipio", "producao"]] if not producao.empty \
        else pd.DataFrame(columns=["municipio", "producao"])
    ic = industrias_da_cadeia(ind, cfg["cnae"])
    g = ic.groupby("municipio").agg(industrias=("cnpj_basico", "size"), clientes=("cliente", "sum"))
    out = prod.set_index("municipio").join(g, how="outer").fillna({"industrias": 0, "clientes": 0, "producao": 0})
    out["sem_relacionamento"] = out["industrias"] - out["clientes"]
    if not sinais.empty and "cnpj_basico" in sinais:
        s = sinais[sinais["cnpj_basico"].isin(ic["cnpj_basico"])]
        out["sinais"] = s.groupby("municipio").size()
    out["sinais"] = out.get("sinais", 0)
    out = out.fillna({"sinais": 0})
    total = out["producao"].sum()
    out["participacao_producao"] = (out["producao"] / total).round(4) if total else 0
    return out.reset_index().sort_values(["producao", "industrias"], ascending=False)
