"""Cruzamentos do Radar com a base: mercado por município, por setor e por negócio.

Tudo calculado a partir dos arquivos que o painel já publica, sem fonte nova:
  BASE_MESTRE_COMERCIAL.csv   universo de indústrias e relacionamento
  VISAO_360.csv               situação de cada empresa em SSI, EB, STI e EP
  INDICADORES_MUNICIPIOS.csv  PIB, VAB da indústria e população (IBGE)
  SINAIS_*.csv                sinais do radar (CNO, notícias, ...)
  METAS_2027*.csv/xlsx        metas do planejamento (opcional)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.tools.municipios import padronizar

RAIZ = Path(__file__).resolve().parents[2]
P = RAIZ / "data" / "processed"
NEGOCIOS = {"SSI": "Saúde e Segurança na Indústria", "STI": "Serviços de Tecnologia e Inovação",
            "EP": "Educação Profissional", "EB": "Educação Básica"}


def setor_cni(cnae: str) -> str:
    """Grandes setores do Perfil Setorial da Indústria (CNI), pela divisão da CNAE."""
    try:
        d = int(str(cnae).replace(".", "").replace("-", "").replace("/", "")[:2])
    except ValueError:
        return "Não classificado"
    if 5 <= d <= 9:
        return "Indústria Extrativa"
    if 10 <= d <= 33:
        return "Indústria da Transformação"
    if 35 <= d <= 39:
        return "Serviços Industriais de Utilidade Pública"
    if 41 <= d <= 43:
        return "Indústria da Construção"
    return "Outros enquadrados pela CNI"


def carregar_industrias() -> pd.DataFrame:
    m = pd.read_csv(P / "BASE_MESTRE_COMERCIAL.csv", dtype=str, low_memory=False, encoding="utf-8-sig")
    m["cnpj_basico"] = m["cnpj"].str.replace(r"\D", "", regex=True).str.zfill(14).str[:8]
    m = m.drop_duplicates("cnpj_basico")
    out = pd.DataFrame({
        "cnpj_basico": m["cnpj_basico"],
        "municipio": padronizar(m["Municipio"]),
        "porte": m["Porte"],
        "setor_cni": m["SEBRAE_cnae_codigo_recuperado"].fillna("").map(setor_cni),
        "cliente": m["STATUS_RELACIONAMENTO"].fillna("").str.upper().ne("SEM RELACIONAMENTO"),
    })
    v360 = P / "VISAO_360.csv"
    if v360.exists():
        v = pd.read_csv(v360, dtype=str, encoding="utf-8-sig")
        cols = ["cnpj_basico"] + [c for c in v.columns if c.endswith("_status")]
        out = out.merge(v[cols], on="cnpj_basico", how="left")
        st = [c for c in cols if c != "cnpj_basico"]
        out["cliente"] = out["cliente"] | out[st].isin(["compra", "parou", "cross"]).any(axis=1)
    return out


def mercado_municipios(ind: pd.DataFrame, sinais: pd.DataFrame) -> pd.DataFrame:
    g = ind.groupby("municipio").agg(industrias=("cnpj_basico", "size"), clientes=("cliente", "sum"))
    g["sem_relacionamento"] = g["industrias"] - g["clientes"]
    g["penetracao"] = (g["clientes"] / g["industrias"]).round(3)
    arq = P / "INDICADORES_MUNICIPIOS.csv"
    if arq.exists():
        ibge = pd.read_csv(arq, dtype={"cod_ibge": str}, encoding="utf-8-sig").set_index("municipio")
        g = g.join(ibge[[c for c in ["pib_mil", "vab_industria_mil", "part_industria_vab", "populacao"]
                         if c in ibge]], how="outer")
    if not sinais.empty and "municipio" in sinais:
        recentes = sinais[sinais["dias_desde_publicacao"].fillna(9999) <= 90]
        g["sinais_90d"] = recentes.groupby(padronizar(recentes["municipio"].fillna(""))).size()
    g["sinais_90d"] = g.get("sinais_90d", 0)
    g = g.fillna({"industrias": 0, "clientes": 0, "sem_relacionamento": 0, "sinais_90d": 0})
    return g.reset_index().rename(columns={"index": "municipio"}).sort_values("sem_relacionamento", ascending=False)


def mercado_setores(ind: pd.DataFrame, sinais: pd.DataFrame) -> pd.DataFrame:
    g = ind.groupby("setor_cni").agg(industrias=("cnpj_basico", "size"), clientes=("cliente", "sum"))
    g["sem_relacionamento"] = g["industrias"] - g["clientes"]
    g["penetracao"] = (g["clientes"] / g["industrias"]).round(3)
    if not sinais.empty and "cnpj_basico" in sinais:
        s = sinais.dropna(subset=["cnpj_basico"]).merge(ind[["cnpj_basico", "setor_cni"]], on="cnpj_basico")
        g["empresas_com_sinal"] = s.groupby("setor_cni")["cnpj_basico"].nunique()
    g["empresas_com_sinal"] = g.get("empresas_com_sinal", 0)
    return g.fillna(0).reset_index().sort_values("industrias", ascending=False)


def visao_negocios(ind: pd.DataFrame, sinais: pd.DataFrame, metas: pd.DataFrame | None) -> pd.DataFrame:
    linhas = []
    for cod, nome in NEGOCIOS.items():
        col = f"{cod}_status"
        s = ind[col] if col in ind else pd.Series(dtype=str)
        acion = sinais[sinais.get("negocios", pd.Series("", index=sinais.index)).fillna("").str.contains(cod)] \
            if not sinais.empty else sinais
        linha = {
            "negocio": cod, "nome": nome,
            "clientes_ativos": int((s == "compra").sum()), "para_reativar": int((s == "parou").sum()),
            "cross_sell": int((s == "cross").sum()), "para_prospectar": int((s == "prospectar").sum()),
            "sinais_ativos": len(acion),
            "empresas_com_sinal": int(acion["cnpj_basico"].nunique()) if not acion.empty else 0,
        }
        if metas is not None and not metas.empty:
            mm = metas[metas["negocio"] == cod]
            linha["meta_2027"] = float(mm["meta"].sum())
            linha["meta_1tri"] = float(mm[mm["mes"].isin([1, 2, 3])]["meta"].sum())
        linhas.append(linha)
    return pd.DataFrame(linhas)


MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8,
         "set": 9, "out": 10, "nov": 11, "dez": 12}


def carregar_metas() -> pd.DataFrame | None:
    """Metas 2027 no formato longo: negocio, produto, unidade, mes (1-12), meta (R$).

    Procura primeiro o detalhe em data/privado/ (só na máquina local) e, se não
    houver, o resumo publicado em data/processed/METAS_2027_RESUMO.csv.
    """
    for arq in [RAIZ / "data" / "privado" / "METAS_2027.xlsx", RAIZ / "data" / "privado" / "METAS_2027.csv",
                P / "METAS_2027_RESUMO.csv"]:
        if arq.exists():
            df = pd.read_excel(arq) if arq.suffix == ".xlsx" else pd.read_csv(arq, encoding="utf-8-sig")
            df.columns = [str(c).strip().lower() for c in df.columns]
            df["negocio"] = df["negocio"].astype(str).str.upper().str.strip()
            mes = df["mes"].astype(str).str.lower().str[:3]
            df["mes"] = pd.to_numeric(mes.map(MESES).fillna(mes), errors="coerce")
            df["meta"] = pd.to_numeric(df["meta"], errors="coerce").fillna(0)
            df.attrs["arquivo"] = arq.name
            return df
    return None
