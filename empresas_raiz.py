"""
Camada de visão empresarial da Base Mestre Comercial.

A Base Mestre é uma base de ESTABELECIMENTOS (CNPJ completo).
Este módulo cria uma visão de EMPRESA (CNPJ raiz) sem perder o detalhe
dos estabelecimentos.

Regra:
    empresa = CNPJ raiz (8 primeiros dígitos)
    estabelecimento = CNPJ completo (14 dígitos)

A consolidação é determinística e preserva os dados de cada estabelecimento
na coluna 'estabelecimentos' para uso futuro.
"""
from __future__ import annotations

import pandas as pd


def normalizar_cnpj(valor: object) -> str:
    if pd.isna(valor):
        return ""
    texto = "".join(c for c in str(valor).strip() if c.isdigit())
    return texto.zfill(14) if texto else ""


def _coluna_cnpj(df: pd.DataFrame) -> str:
    for coluna in ("cnpj", "CNPJ_NORMALIZADO", "CNPJ"):
        if coluna in df.columns:
            return coluna
    raise ValueError("A base precisa ter uma coluna de CNPJ.")


def preparar_base(base: pd.DataFrame) -> pd.DataFrame:
    df = base.copy()
    col = _coluna_cnpj(df)

    df["cnpj"] = df[col].map(normalizar_cnpj)
    df["cnpj_raiz"] = df["cnpj"].str[:8]
    df = df[df["cnpj"].ne("") & df["cnpj_raiz"].ne("")].copy()

    if "POSSUI_SESI" not in df.columns:
        df["POSSUI_SESI"] = _bool_col(df, "TEM_SESI")
    if "POSSUI_SENAI" not in df.columns:
        df["POSSUI_SENAI"] = _bool_col(df, "TEM_SENAI")

    df["POSSUI_SESI_SENAI"] = df["POSSUI_SESI"] & df["POSSUI_SENAI"]
    df["CLIENTE_SESI_SENAI"] = df["POSSUI_SESI"] | df["POSSUI_SENAI"]

    return df


def _bool_col(df: pd.DataFrame, coluna: str) -> pd.Series:
    if coluna not in df.columns:
        return pd.Series(False, index=df.index)
    valores = df[coluna].fillna("").astype(str).str.strip().str.upper()
    return valores.isin(["TRUE", "1", "SIM", "S", "VERDADEIRO", "T", "YES"])


def consolidar_por_raiz(base_estabelecimentos: pd.DataFrame) -> pd.DataFrame:
    """
    Consolida estabelecimentos em uma linha por CNPJ raiz.

    A primeira linha de cada raiz é usada como registro-base para atributos
    descritivos. Métricas e relacionamento são consolidados sobre TODOS os
    estabelecimentos da raiz.
    """
    df = preparar_base(base_estabelecimentos)

    if df.empty:
        return pd.DataFrame(columns=["cnpj_raiz", "n_estabelecimentos"])

    ordenado = df.sort_values(["cnpj_raiz", "cnpj"]).copy()

    agregacoes = []
    for raiz, grupo in ordenado.groupby("cnpj_raiz", sort=True):
        registro = grupo.iloc[0].to_dict()

        registro["cnpj_raiz"] = raiz
        registro["cnpj"] = grupo["cnpj"].iloc[0]
        registro["n_estabelecimentos"] = int(grupo["cnpj"].nunique())
        registro["cnpjs_estabelecimentos"] = " | ".join(
            grupo["cnpj"].drop_duplicates().tolist()
        )

        registro["POSSUI_SESI"] = bool(grupo["POSSUI_SESI"].any())
        registro["POSSUI_SENAI"] = bool(grupo["POSSUI_SENAI"].any())
        registro["POSSUI_SESI_SENAI"] = (
            registro["POSSUI_SESI"] and registro["POSSUI_SENAI"]
        )
        registro["CLIENTE_SESI_SENAI"] = (
            registro["POSSUI_SESI"] or registro["POSSUI_SENAI"]
        )

        if "STATUS_RELACIONAMENTO_REAL" in grupo.columns:
            registro["STATUS_RELACIONAMENTO_REAL"] = _status_relacionamento(
                registro["POSSUI_SESI"],
                registro["POSSUI_SENAI"],
            )

        if "STATUS_RELACIONAMENTO" in grupo.columns:
            registro["STATUS_RELACIONAMENTO"] = _status_relacionamento(
                registro["POSSUI_SESI"],
                registro["POSSUI_SENAI"],
            )

        if "Municipio" in grupo.columns:
            municipios = (
                grupo["Municipio"]
                .dropna()
                .astype(str)
                .loc[lambda s: s.str.strip().ne("")]
                .drop_duplicates()
                .tolist()
            )
            registro["Municipios"] = " | ".join(municipios)

        agregacoes.append(registro)

    empresas = pd.DataFrame(agregacoes)

    empresas["MULTI_ESTABELECIMENTO"] = empresas["n_estabelecimentos"].gt(1)
    empresas["TIPO_EMPRESA"] = empresas["MULTI_ESTABELECIMENTO"].map(
        {True: "Multiestabelecimento", False: "Unidade única"}
    )

    return empresas.reset_index(drop=True)


def _status_relacionamento(tem_sesi: bool, tem_senai: bool) -> str:
    if tem_sesi and tem_senai:
        return "SESI + SENAI"
    if tem_sesi:
        return "Somente SESI"
    if tem_senai:
        return "Somente SENAI"
    return "Sem relacionamento"


def separar_pistas(empresas: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Separa as empresas em três pistas MUTUAMENTE EXCLUSIVAS.

    1. contas_nomeadas: multiestabelecimento (>1 estabelecimento)
    2. antigos: cliente SESI/SENAI, não multiestabelecimento
    3. novos: sem relacionamento, não multiestabelecimento
    """
    multi = empresas["MULTI_ESTABELECIMENTO"]
    cliente = empresas["CLIENTE_SESI_SENAI"]

    contas_nomeadas = empresas[multi].copy()
    antigos = empresas[cliente & ~multi].copy()
    novos = empresas[~cliente & ~multi].copy()

    return {
        "novos": novos,
        "antigos": antigos,
        "contas_nomeadas": contas_nomeadas,
    }


def resumo(
    base_estabelecimentos: pd.DataFrame,
    empresas: pd.DataFrame | None = None,
) -> dict[str, int]:
    df = preparar_base(base_estabelecimentos)
    empresas = empresas if empresas is not None else consolidar_por_raiz(df)

    estabelecimentos = int(df["cnpj"].nunique())
    empresas_raiz = int(df["cnpj_raiz"].nunique())

    # Diferença entre estabelecimentos e raízes = estabelecimentos adicionais
    # além da primeira unidade de cada empresa.
    estabelecimentos_adicionais = estabelecimentos - empresas_raiz

    multi = int(empresas["MULTI_ESTABELECIMENTO"].sum())

    ja_clientes = int(empresas["CLIENTE_SESI_SENAI"].sum())

    return {
        "empresas_raiz": empresas_raiz,
        "estabelecimentos": estabelecimentos,
        "filiais_inflacao": estabelecimentos_adicionais,
        "estabelecimentos_adicionais": estabelecimentos_adicionais,
        "ja_clientes": ja_clientes,
        "contas_nomeadas": multi,
        "empresas_multiestabelecimento": multi,
    }
