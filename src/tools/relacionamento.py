"""Relacionamento com o cliente a partir da exportação de PROPOSTAS (SESI/SENAI).

Fonte: exportação do sistema comercial (colunas CNPJ, Entidade, Status,
Emissão, Aprovação, Valor total, Natureza Produto, Porte...). Desde 2018.

Definição (editável em config/referencia/relacionamento.yaml):
  * cliente SESI/SENAI = tem pelo menos uma proposta com status "Aceita"
    daquela entidade (canceladas, recusadas e em negociação não contam)
  * data da compra = data de aprovação (ou emissão, se não houver)
  * situação: "Ativo" se a última compra foi nos últimos N meses (24),
    "Inativo" se foi antes; "Sem compra" se nunca teve proposta aceita

Duas visões, seguindo a lógica do painel:
  * por CNPJ ÚNICO (estabelecimento): esta unidade comprou?
  * por CNPJ RAIZ (empresa): alguma unidade da empresa comprou?
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

RAIZ = Path(__file__).resolve().parents[2]
ARQ_CONFIG = RAIZ / "config" / "referencia" / "relacionamento.yaml"

PORTE_EXPORT = {"1. Grande": "Grande", "2. Médio": "Média", "3. Pequeno": "Pequena", "4. Micro": "Micro",
                "1.Grande": "Grande", "2.Média": "Média", "3.Pequena": "Pequena", "4.Micro": "Micro"}


def carregar_config(caminho: Path = ARQ_CONFIG) -> dict:
    padrao = {"meses_ativo": 24, "status_venda": ["Aceita"], "entidades": ["SESI", "SENAI"]}
    if Path(caminho).exists():
        padrao.update(yaml.safe_load(open(caminho, encoding="utf-8")) or {})
    return padrao


def carregar_propostas(caminho: Path) -> pd.DataFrame:
    df = pd.read_excel(caminho, dtype=str).fillna("")
    df["cnpj"] = df["CNPJ"].str.replace(r"\D", "", regex=True)
    df = df[df["cnpj"].str.len().between(11, 14)].copy()
    df["cnpj"] = df["cnpj"].str.zfill(14)
    df["cnpj_basico"] = df["cnpj"].str[:8]
    aprov = pd.to_datetime(df["Aprovação"], errors="coerce")
    aprov = aprov.where(aprov.dt.year >= 2000)                 # 1900-01-02 = sem data
    df["data"] = aprov.fillna(pd.to_datetime(df["Emissão"], errors="coerce"))
    df["ano"] = df["data"].dt.year
    df["valor"] = pd.to_numeric(df["Valor total"], errors="coerce").fillna(0.0)
    df["produto"] = df["Natureza Produto"].str.strip()
    df["porte_fiea"] = df["Porte"].map(PORTE_EXPORT).fillna("")
    return df


def vendas(propostas: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    return propostas[propostas["Status"].isin(cfg["status_venda"])
                     & propostas["Entidade"].isin(cfg["entidades"])].copy()


def _resumo(v: pd.DataFrame, chave: str, hoje: pd.Timestamp, meses: int) -> pd.DataFrame:
    ult = v.groupby([chave, "Entidade"])["data"].max().unstack()
    for e in ("SESI", "SENAI"):
        if e not in ult:
            ult[e] = pd.NaT
    out = pd.DataFrame(index=ult.index)
    out["TEM_SESI"] = ult["SESI"].notna()
    out["TEM_SENAI"] = ult["SENAI"].notna()
    out["ULTIMA_COMPRA_SESI"] = ult["SESI"].dt.date
    out["ULTIMA_COMPRA_SENAI"] = ult["SENAI"].dt.date
    ultima = ult[["SESI", "SENAI"]].max(axis=1)
    out["ULTIMA_COMPRA"] = ultima.dt.date
    out["SITUACAO_CLIENTE"] = (ultima >= hoje - pd.DateOffset(months=meses)).map({True: "Ativo", False: "Inativo"})
    g = v.groupby(chave)
    out["PRIMEIRA_COMPRA"] = g["data"].min().dt.date
    out["QTD_PROPOSTAS_ACEITAS"] = g.size()
    out["VALOR_ACEITO_TOTAL"] = g["valor"].sum().round(2)
    out["LINHAS_COMPRADAS"] = g["produto"].agg(
        lambda s: "; ".join(s[s != ""].value_counts().index))
    return out.reset_index()


def resumo_por_raiz(v: pd.DataFrame, hoje, meses: int) -> pd.DataFrame:
    r = _resumo(v, "cnpj_basico", pd.Timestamp(hoje), meses)
    cnpjs = v.groupby("cnpj_basico")["cnpj"].nunique().rename("QTD_CNPJS_ATENDIDOS")
    return r.merge(cnpjs, left_on="cnpj_basico", right_index=True)


def resumo_por_cnpj(v: pd.DataFrame, hoje, meses: int) -> pd.DataFrame:
    return _resumo(v, "cnpj", pd.Timestamp(hoje), meses)


def porte_fiea_por_raiz(propostas: pd.DataFrame) -> pd.DataFrame:
    """Porte FIEA mais recente informado nas propostas (qualquer status)."""
    p = propostas[propostas["porte_fiea"] != ""].sort_values("data")
    return p.drop_duplicates("cnpj_basico", keep="last")[["cnpj_basico", "porte_fiea"]]


STATUS = {(False, False): "SEM RELACIONAMENTO", (True, False): "SOMENTE SESI",
          (False, True): "SOMENTE SENAI", (True, True): "SESI + SENAI"}
OPORTUNIDADE = {  # (TEM_SESI, TEM_SENAI) -> GERAL, CROSS_SELL, SESI, SENAI (como na Base Mestre)
    (False, False): ("PROSPECT", "NÃO", "SIM", "SIM"), (True, False): ("CLIENTE", "SENAI", "NÃO", "SIM"),
    (False, True): ("CLIENTE", "SESI", "SIM", "NÃO"), (True, True): ("CLIENTE", "NÃO", "NÃO", "NÃO"),
}
COLS_PUBLICAS = ["SITUACAO_CLIENTE", "ULTIMA_COMPRA", "ULTIMA_COMPRA_SESI", "ULTIMA_COMPRA_SENAI",
                 "PRIMEIRA_COMPRA", "CNPJ_ATENDIDO"]


def aplicar_na_base(base: pd.DataFrame, por_raiz: pd.DataFrame, por_cnpj: pd.DataFrame) -> pd.DataFrame:
    """Recalcula as colunas de cliente da Base Mestre (uma linha por estabelecimento).

    TEM_SESI/TEM_SENAI valem para a EMPRESA (raiz): se qualquer unidade
    comprou, todas as linhas da raiz ficam marcadas. CNPJ_ATENDIDO diz se
    aquela unidade específica comprou.
    """
    b = base.copy()
    raiz = b["CNPJ_BASICO"].astype(str).str.zfill(8)
    cnpj = b["cnpj"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(14)
    r = por_raiz.set_index("cnpj_basico")
    sesi = raiz.map(r["TEM_SESI"]).fillna(False).astype(bool)
    senai = raiz.map(r["TEM_SENAI"]).fillna(False).astype(bool)
    b["TEM_SESI"], b["TEM_SENAI"], b["TEM_SESI_SENAI"] = sesi.astype(str), senai.astype(str), (sesi & senai).astype(str)
    pares = list(zip(sesi, senai))
    b["STATUS_RELACIONAMENTO"] = [STATUS[p] for p in pares]
    for i, col in enumerate(["OPORTUNIDADE_GERAL", "OPORTUNIDADE_CROSS_SELL", "OPORTUNIDADE_SESI", "OPORTUNIDADE_SENAI"]):
        if col in b.columns:
            b[col] = [OPORTUNIDADE[p][i] for p in pares]
    for col in ("SITUACAO_CLIENTE", "ULTIMA_COMPRA", "ULTIMA_COMPRA_SESI", "ULTIMA_COMPRA_SENAI", "PRIMEIRA_COMPRA"):
        b[col] = raiz.map(r[col]).astype("object").where(lambda s: s.notna(), "")
    b["SITUACAO_CLIENTE"] = b["SITUACAO_CLIENTE"].replace("", "Sem compra")
    b["CNPJ_ATENDIDO"] = cnpj.isin(set(por_cnpj["cnpj"])).map({True: "Sim", False: "Não"})
    return b


def ranking_produtos(v: pd.DataFrame, raizes_industria: set[str], hoje, meses: int) -> pd.DataFrame:
    """Produtos mais vendidos — agregado, sem dado de empresa (pode ir ao painel)."""
    x = v.assign(industria_base=v["cnpj_basico"].isin(raizes_industria),
                 recente=v["data"] >= pd.Timestamp(hoje) - pd.DateOffset(months=meses))
    g = x.groupby(["produto", "Entidade", "industria_base"])
    out = g.agg(empresas=("cnpj_basico", "nunique"), propostas=("cnpj", "size"), valor=("valor", "sum")).reset_index()
    rec = x[x["recente"]].groupby(["produto", "Entidade", "industria_base"])["cnpj_basico"].nunique()
    out["empresas_recentes"] = out.set_index(["produto", "Entidade", "industria_base"]).index.map(rec).fillna(0).astype(int)
    out["valor"] = out["valor"].round(2)
    return out[out["produto"] != ""].sort_values("empresas", ascending=False)


def atendimento_por_ano(v: pd.DataFrame, raizes_industria: set[str]) -> pd.DataFrame:
    """Empresas distintas atendidas por ano e entidade — agregado."""
    x = v.dropna(subset=["ano"]).assign(industria_base=v["cnpj_basico"].isin(raizes_industria))
    return (x.groupby(["ano", "Entidade", "industria_base"])["cnpj_basico"].nunique()
            .rename("empresas").reset_index().astype({"ano": int}))
