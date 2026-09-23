"""
Componente Streamlit para a visão consolidada por CNPJ raiz.

Usa o mesmo motor de consolidação do restante do dashboard
(src.tools.cnpj_raiz), para que "quantas empresas existem" nunca
divirja entre esta página e as demais. Esta página sempre trabalha em
nível de empresa — quem quer ver estabelecimento a estabelecimento usa
o toggle global da barra lateral, nas outras páginas.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.tools.cnpj_raiz import (
    consolidar_por_cnpj_raiz,
    resumir_consolidacao,
    separar_pistas,
)


COLS_EXIBICAO = [
    "CNPJ_BASICO",
    "razao_social",
    "Municipio",
    "Municipios",
    "Porte",
    "CNAE PRIMARIO",
    "QTD_ESTABELECIMENTOS",
    "TIPO_EMPRESA",
    "STATUS_RELACIONAMENTO_REAL",
]


def _fmt(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


def _cols(df: pd.DataFrame) -> list[str]:
    return [c for c in COLS_EXIBICAO if c in df.columns]


def render_visao_raiz(base_estabelecimentos: pd.DataFrame) -> None:
    empresas = consolidar_por_cnpj_raiz(base_estabelecimentos)
    kpi = resumir_consolidacao(base_estabelecimentos, empresas)
    pistas = separar_pistas(empresas)

    st.header("🏢 Visão por Empresa — CNPJ raiz")
    st.caption(
        "A Base Mestre trabalha no nível de estabelecimento (CNPJ completo). "
        "Aqui a empresa é a unidade de análise: matriz e filiais da mesma "
        "raiz contam como uma só."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Empresas (CNPJ raiz)", _fmt(kpi["total_empresas"]))
    c2.metric(
        "Estabelecimentos",
        _fmt(kpi["total_estabelecimentos"]),
        delta=f"+{_fmt(kpi['total_filiais'])} filiais",
        delta_color="off",
    )
    c3.metric("Empresas já clientes", _fmt(kpi.get("ja_clientes", 0)))
    c4.metric("Empresas com mais de 1 unidade", _fmt(kpi["empresas_com_filial"]))

    st.divider()
    aba_novos, aba_antigos, aba_multi = st.tabs(
        [
            f"🆕 Novos — frios ({_fmt(len(pistas['novos']))})",
            f"🔄 Clientes — expansão ({_fmt(len(pistas['antigos']))})",
            f"🏢 Multiestabelecimento ({_fmt(len(pistas['contas_nomeadas']))})",
        ]
    )

    with aba_novos:
        st.caption(
            "Empresas sem relacionamento SESI/SENAI e com apenas um "
            "estabelecimento na base. Separadas para prospecção."
        )
        st.dataframe(
            pistas["novos"][_cols(pistas["novos"])],
            use_container_width=True,
            hide_index=True,
        )

    with aba_antigos:
        st.caption(
            "Empresas que já possuem relacionamento SESI e/ou SENAI, sem "
            "múltiplos estabelecimentos na base. Lógica de expansão/cross-sell."
        )
        st.dataframe(
            pistas["antigos"][_cols(pistas["antigos"])],
            use_container_width=True,
            hide_index=True,
        )

    with aba_multi:
        st.caption(
            "Empresas com mais de um estabelecimento na base. "
            "Multiestabelecimento não é sinônimo de conta nomeada; é uma "
            "classificação estrutural para tratamento comercial."
        )
        st.dataframe(
            pistas["contas_nomeadas"][_cols(pistas["contas_nomeadas"])],
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.subheader("Distribuição da estrutura empresarial")
    estrutura = (
        empresas["QTD_ESTABELECIMENTOS"]
        .value_counts()
        .sort_index()
        .rename_axis("Estabelecimentos por empresa")
        .to_frame("Empresas")
    )
    st.bar_chart(estrutura)
