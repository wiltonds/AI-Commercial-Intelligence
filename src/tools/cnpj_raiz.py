"""Consolidação da base de estabelecimentos por CNPJ raiz (empresa).

A Receita Federal cadastra cada unidade física (matriz e filiais) com
um CNPJ próprio, mas todas compartilham os 8 primeiros dígitos — o
CNPJ raiz. Sem essa consolidação, uma empresa com filiais aparece
várias vezes nas contagens do dashboard, inflando o tamanho do
mercado: hoje a Base Mestre tem 14.903 estabelecimentos, mas apenas
13.978 CNPJ raízes (empresas) distintos.

Este módulo reduz a base de estabelecimentos a uma linha por empresa,
preservando a visão de filial como um detalhe consultável, não como
ruído nas métricas principais.
"""

import pandas as pd

COLUNAS_RELACIONAMENTO = ["POSSUI_SESI", "POSSUI_SENAI", "POSSUI_SEBRAE"]


def consolidar_por_cnpj_raiz(
    df: pd.DataFrame,
    col_cnpj: str = "cnpj",
    col_raiz: str = "CNPJ_BASICO",
) -> pd.DataFrame:
    """Reduz a base de estabelecimentos a uma linha por CNPJ raiz.

    Critério de representante do grupo: a matriz (ordem "0001" do
    CNPJ) quando presente na base; senão o estabelecimento que já é
    cliente SESI/SENAI; senão o primeiro por CNPJ. O relacionamento
    institucional (SESI/SENAI/SEBRAE) é herdado do grupo inteiro — se
    qualquer filial já é cliente, a empresa conta como cliente, mesmo
    que o relacionamento esteja registrado sob outro CNPJ do grupo.

    Adiciona QTD_ESTABELECIMENTOS, QTD_FILIAIS e TEM_FILIAL para que a
    visão de filial fique disponível sem poluir a contagem principal.
    """
    df = df.copy()

    if col_raiz not in df.columns:
        df[col_raiz] = df[col_cnpj].str[:8]

    eh_matriz = df[col_cnpj].str[8:12] == "0001"

    ja_cliente = pd.Series(False, index=df.index)
    for coluna in ("POSSUI_SESI", "POSSUI_SENAI"):
        if coluna in df.columns:
            ja_cliente |= df[coluna].fillna(False)

    ativa = (
        df["situacao_atual"].astype(str).str.upper().eq("ATIVA")
        if "situacao_atual" in df.columns
        else pd.Series(False, index=df.index)
    )

    df["_prioridade_matriz"] = ~eh_matriz
    df["_prioridade_cliente"] = ~ja_cliente
    df["_prioridade_ativa"] = ~ativa

    representantes = (
        df.sort_values(
            ["_prioridade_matriz", "_prioridade_cliente", "_prioridade_ativa", col_cnpj]
        )
        .drop_duplicates(subset=col_raiz, keep="first")
        .drop(columns=["_prioridade_matriz", "_prioridade_cliente", "_prioridade_ativa"])
    )

    tamanho_grupo = df.groupby(col_raiz).size().rename("QTD_ESTABELECIMENTOS")
    representantes = representantes.merge(tamanho_grupo, on=col_raiz, how="left")
    representantes["QTD_FILIAIS"] = representantes["QTD_ESTABELECIMENTOS"] - 1
    representantes["TEM_FILIAL"] = representantes["QTD_FILIAIS"] > 0

    colunas_grupo = [c for c in COLUNAS_RELACIONAMENTO if c in df.columns]
    if colunas_grupo:
        agregados = df.groupby(col_raiz)[colunas_grupo].any().reset_index()
        representantes = representantes.drop(columns=colunas_grupo).merge(
            agregados, on=col_raiz, how="left"
        )

    if "POSSUI_SESI" in representantes.columns and "POSSUI_SENAI" in representantes.columns:
        representantes["POSSUI_SESI_SENAI"] = (
            representantes["POSSUI_SESI"] & representantes["POSSUI_SENAI"]
        )
        representantes["CLIENTE_SESI_SENAI"] = (
            representantes["POSSUI_SESI"] | representantes["POSSUI_SENAI"]
        )
        representantes["STATUS_RELACIONAMENTO_REAL"] = "Sem relacionamento"
        representantes.loc[
            representantes["POSSUI_SESI"] & ~representantes["POSSUI_SENAI"],
            "STATUS_RELACIONAMENTO_REAL",
        ] = "Somente SESI"
        representantes.loc[
            ~representantes["POSSUI_SESI"] & representantes["POSSUI_SENAI"],
            "STATUS_RELACIONAMENTO_REAL",
        ] = "Somente SENAI"
        representantes.loc[
            representantes["POSSUI_SESI_SENAI"], "STATUS_RELACIONAMENTO_REAL"
        ] = "SESI + SENAI"

    representantes["TIPO_EMPRESA"] = representantes["TEM_FILIAL"].map(
        {True: "Multiestabelecimento", False: "Unidade única"}
    )

    if "Municipio" in df.columns:
        municipios_por_raiz = (
            df.groupby(col_raiz)["Municipio"]
            .apply(_municipios_unicos)
            .rename("Municipios")
            .reset_index()
        )
        representantes = representantes.merge(municipios_por_raiz, on=col_raiz, how="left")

    return representantes.reset_index(drop=True)


def _municipios_unicos(serie: pd.Series) -> str:
    valores = serie.dropna().astype(str).str.strip()
    valores = valores[valores.ne("")]
    return " | ".join(sorted(valores.unique()))


def separar_pistas(df_empresas: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Três lentes comerciais mutuamente exclusivas sobre as empresas.

    novos: sem relacionamento e unidade única — prospecção fria.
    antigos: já clientes e unidade única — expansão/cross-sell.
    contas_nomeadas: mais de um estabelecimento — tratamento estrutural
    próprio, independente de já serem clientes ou não.
    """
    multi = df_empresas["TEM_FILIAL"]
    cliente = df_empresas.get(
        "CLIENTE_SESI_SENAI", pd.Series(False, index=df_empresas.index)
    )

    return {
        "novos": df_empresas[~multi & ~cliente].copy(),
        "antigos": df_empresas[~multi & cliente].copy(),
        "contas_nomeadas": df_empresas[multi].copy(),
    }


def resumir_consolidacao(df_estabelecimentos: pd.DataFrame, df_empresas: pd.DataFrame) -> dict:
    """Números de auditoria para explicar a diferença estabelecimento × empresa."""

    resumo = {
        "total_estabelecimentos": len(df_estabelecimentos),
        "total_empresas": len(df_empresas),
        "empresas_com_filial": int(df_empresas["TEM_FILIAL"].sum()),
        "total_filiais": int(df_empresas["QTD_FILIAIS"].sum()),
    }

    if "CLIENTE_SESI_SENAI" in df_empresas.columns:
        resumo["ja_clientes"] = int(df_empresas["CLIENTE_SESI_SENAI"].sum())

    return resumo
