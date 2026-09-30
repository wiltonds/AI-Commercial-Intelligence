"""Visão 360 — o que cada empresa compra e o que pode comprar, por linha de negócio.

Para cada empresa (CNPJ raiz) e cada linha (SSI, EB, STI, EP):
  * compra      comprou a linha nos últimos N meses
  * parou       já comprou a linha, mas antes disso
  * oportunidade  não compra, e pelo menos X% das empresas PARECIDAS compram
  * baixa       não compra, e poucas parecidas compram

"Parecidas" = mesma classe CNAE e mesmo porte; se o grupo for pequeno, o
percentual é puxado para o do segmento (divisão CNAE) e depois para o geral
(suavização), para não dizer "100%" com base em uma empresa só.
É isso que reduz o viés: a oportunidade vem do que empresas iguais já
compram, não do que o comercial costuma oferecer.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

RAIZ = Path(__file__).resolve().parents[2]
ARQ_LINHAS = RAIZ / "config" / "referencia" / "linhas_negocio.yaml"
ARQ_360 = RAIZ / "data" / "processed" / "VISAO_360.csv"
STATUS_ROTULO = {"compra": "compra", "parou": "comprou e parou", "oportunidade": "oportunidade", "baixa": "pouca aderência"}


def carregar_linhas(caminho: Path = ARQ_LINHAS) -> dict:
    return yaml.safe_load(open(caminho, encoding="utf-8"))


def mapa_produto(cfg: dict) -> dict[tuple[str, str], str]:
    return {(l["entidade"], p.strip().lower()): cod
            for cod, l in cfg["linhas"].items() for p in l["produtos"]}


def marcar_linhas(vendas: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    mapa = mapa_produto(cfg)
    v = vendas.copy()
    v["linha"] = [mapa.get((e, str(p).strip().lower())) for e, p in zip(v["Entidade"], v["produto"])]
    return v


def _penetracao(univ: pd.DataFrame, comprou: pd.Series, k: float) -> pd.Series:
    """% suavizado de empresas parecidas (classe CNAE x porte -> divisão -> geral) que compram."""
    d = univ.assign(y=comprou.astype(float).values)
    geral = d["y"].mean()
    div = d.groupby("div")["y"].agg(["sum", "count"])
    taxa_div = ((div["sum"] + k * geral) / (div["count"] + k))
    cel = d.groupby(["classe", "porte"])["y"].agg(["sum", "count"])
    base = d["div"].map(taxa_div).fillna(geral)
    idx = pd.MultiIndex.from_arrays([d["classe"], d["porte"]])
    s = cel.reindex(idx)["sum"].fillna(0).values
    n = cel.reindex(idx)["count"].fillna(0).values
    # tira a própria empresa da conta (senão quem compra "puxa" o próprio percentual)
    s_out, n_out = s - d["y"].values, n - 1
    return pd.Series((s_out + k * base.values) / (n_out.clip(min=0) + k), index=d.index)


def calcular(univ: pd.DataFrame, vendas_linha: pd.DataFrame, cfg: dict, hoje) -> pd.DataFrame:
    """univ: uma linha por empresa com cnpj_basico, classe (4 dígitos CNAE), div (2), porte."""
    hoje = pd.Timestamp(hoje)
    corte = hoje - pd.DateOffset(months=int(cfg.get("meses_ativo", 24)))
    k, minimo = float(cfg.get("suavizacao", 15)), float(cfg.get("oportunidade_min_pct", 10)) / 100
    out = univ[["cnpj_basico"]].copy()
    ult = vendas_linha.dropna(subset=["linha"]).groupby(["cnpj_basico", "linha"])["data"].max().unstack()
    for cod in cfg["linhas"]:
        u = univ["cnpj_basico"].map(ult[cod]) if cod in ult else pd.Series(pd.NaT, index=univ.index)
        u = pd.to_datetime(u)
        pct = _penetracao(univ, u.notna(), k)
        status = pd.Series("baixa", index=univ.index)
        status[pct >= minimo] = "oportunidade"
        status[u.notna()] = "parou"
        status[u >= corte] = "compra"
        out[f"{cod}_status"] = status.values
        out[f"{cod}_pct"] = (pct * 100).round(0).astype(int).values
        out[f"{cod}_ultima"] = u.dt.date.astype("object").where(u.notna(), "").values
    cods = list(cfg["linhas"])
    out["linhas_ativas"] = sum((out[f"{c}_status"] == "compra").astype(int) for c in cods)
    out["oportunidades_360"] = [
        "; ".join(f"{c} ({int(r[f'{c}_pct'])}%)" for c in sorted(cods, key=lambda c: -r[f"{c}_pct"])
                  if r[f"{c}_status"] == "oportunidade")
        for r in out.to_dict("records")]
    out["retomar_360"] = ["; ".join(c for c in cods if r[f"{c}_status"] == "parou") for r in out.to_dict("records")]
    return out


def preparar_universo(base_empresas: pd.DataFrame) -> pd.DataFrame:
    """Base Mestre consolidada por raiz -> colunas que a Visão 360 usa."""
    d = pd.DataFrame({"cnpj_basico": base_empresas["CNPJ_BASICO"].astype(str).str.zfill(8)})
    cod = base_empresas.get("SEBRAE_cnae_codigo_recuperado", pd.Series("", index=base_empresas.index)).fillna("")
    d["classe"] = cod.str.replace(r"\D", "", regex=True).str[:4].values
    div = base_empresas.get("SEBRAE_cnae_divisao", pd.Series("0", index=base_empresas.index)).fillna("0")
    d["div"] = div.astype(str).str.split(".").str[0].values
    d["porte"] = base_empresas.get("Porte", pd.Series("", index=base_empresas.index)).fillna("").values
    return d.drop_duplicates("cnpj_basico").reset_index(drop=True)


ARQ_NAT_MUN = RAIZ / "data" / "processed" / "ADESAO_NATUREZA_MUNICIPIO.csv"


def adesao_natureza_municipio(vendas_linha: pd.DataFrame, base_empresas: pd.DataFrame, hoje, meses: int = 24) -> pd.DataFrame:
    """Quantas empresas aderiram a cada natureza de produto, por linha e município — agregado,
    sem identificar empresa. Município vem da Base Mestre; quem não está nela fica como
    "Fora da base industrial"."""
    mun = (base_empresas.assign(r=base_empresas["CNPJ_BASICO"].astype(str).str.zfill(8))
           .drop_duplicates("r").set_index("r")["Municipio"])
    v = vendas_linha.dropna(subset=["linha"]).copy()
    v["municipio"] = v["cnpj_basico"].map(mun).fillna("Fora da base industrial")
    v["recente"] = v["data"] >= pd.Timestamp(hoje) - pd.DateOffset(months=meses)
    g = v.groupby(["linha", "produto", "municipio"])
    out = g.agg(empresas=("cnpj_basico", "nunique"), propostas=("cnpj", "size")).reset_index()
    rec = v[v["recente"]].groupby(["linha", "produto", "municipio"])["cnpj_basico"].nunique()
    out["empresas_24m"] = out.set_index(["linha", "produto", "municipio"]).index.map(rec).fillna(0).astype(int)
    return out.sort_values(["linha", "empresas"], ascending=[True, False])


def universo_nao_industrias(ampliada: pd.DataFrame) -> pd.DataFrame:
    """Base ampliada (não indústrias) -> mesmas colunas de preparar_universo."""
    cnae = ampliada["cnae_principal"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(7)
    return pd.DataFrame({"cnpj_basico": ampliada["cnpj_basico"].astype(str).str.zfill(8), "classe": cnae.str[:4],
                         "div": cnae.str[:2].str.lstrip("0"), "porte": ampliada["Porte"].fillna("")}).drop_duplicates("cnpj_basico")
