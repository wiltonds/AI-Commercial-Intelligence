"""
Componente Streamlit para a visão consolidada por CNPJ raiz.

A página continua permitindo navegar entre:
- Empresa (CNPJ raiz)
- Estabelecimento (CNPJ completo)

A visão empresarial não substitui a Base Mestre: ela é uma camada analítica
sobre a base de estabelecimentos.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from empresas_raiz import consolidar_por_raiz, separar_pistas, resumo


COLS_EXIBICAO = [
    "cnpj_raiz",
    "razao_social",
    "Municipio",
    "Municipios",
    "Porte",
    "CNAE PRIMARIO",
    "n_estabelecimentos",
    "TIPO_EMPRESA",
    "STATUS_RELACIONAMENTO_REAL",
]


def _fmt(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


def _cols(df: pd.DataFrame) -> list[str]:
    return [c for c in COLS_EXIBICAO if c in df.columns]


def render_visao_raiz(base_estabelecimentos: pd.DataFrame) -> pd.DataFrame:
    empresas = consolidar_por_raiz(base_estabelecimentos)
    kpi = resumo(base_estabelecimentos, empresas)
    pistas = separar_pistas(empresas)

    st.header("🏢 Visão por Empresa — CNPJ raiz")
    st.caption(
        "A Base Mestre trabalha no nível de estabelecimento (CNPJ completo). "
        "Aqui consolidamos pelo CNPJ raiz para que matriz e demais "
        "estabelecimentos da mesma empresa não sejam contados como empresas distintas."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Empresas (CNPJ raiz)", _fmt(kpi["empresas_raiz"]))
    c2.metric(
        "Estabelecimentos",
        _fmt(kpi["estabelecimentos"]),
        delta=f"+{_fmt(kpi['estabelecimentos_adicionais'])} adicionais",
        delta_color="off",
    )
    c3.metric("Empresas já clientes", _fmt(kpi["ja_clientes"]))
    c4.metric(
        "Empresas multiestabelecimento",
        _fmt(kpi["empresas_multiestabelecimento"]),
    )

    visao = st.radio(
        "Nível de análise",
        ["Empresas (CNPJ raiz)", "Estabelecimentos (CNPJ completo)"],
        horizontal=True,
        help=(
            "Empresa = decisão comercial no nível da organização. "
            "Estabelecimento = potencial local de serviços e operação."
        ),
    )

    if visao == "Empresas (CNPJ raiz)":
        df_view = empresas
    else:
        df_view = base_estabelecimentos.copy()

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
            "Empresas sem relacionamento SESI/SENAI e com apenas um estabelecimento "
            "na base. São separadas para prospecção."
        )
        st.dataframe(
            pistas["novos"][_cols(pistas["novos"])],
            use_container_width=True,
            hide_index=True,
        )

    with aba_antigos:
        st.caption(
            "Empresas que já possuem relacionamento SESI e/ou SENAI, sem "
            "múltiplos estabelecimentos na base. A lógica aqui é expansão/cross-sell."
        )
        st.dataframe(
            pistas["antigos"][_cols(pistas["antigos"])],
            use_container_width=True,
            hide_index=True,
        )

    with aba_multi:
        st.caption(
            "Empresas com mais de um estabelecimento na base. O sistema não "
            "assume que 'multiestabelecimento' seja sinônimo de conta nomeada; "
            "esta é uma classificação estrutural para tratamento comercial."
        )
        st.dataframe(
            pistas["contas_nomeadas"][_cols(pistas["contas_nomeadas"])],
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.subheader("Distribuição da estrutura empresarial")

    estrutura = (
        empresas["n_estabelecimentos"]
        .value_counts()
        .sort_index()
        .rename_axis("Estabelecimentos por empresa")
        .to_frame("Empresas")
    )
    st.bar_chart(estrutura)

    st.divider()
    st.subheader("Empresas multiestabelecimento")

    multi = empresas[empresas["MULTI_ESTABELECIMENTO"]].copy()
    if multi.empty:
        st.info("Nenhuma empresa multiestabelecimento encontrada.")
    else:
        multi["Cobertura"] = multi["STATUS_RELACIONAMENTO_REAL"]
        st.dataframe(
            multi[_cols(multi) + ["Cobertura"]]
            if "Cobertura" not in _cols(multi)
            else multi[_cols(multi)],
            use_container_width=True,
            hide_index=True,
        )

    return df_view
