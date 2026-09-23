# ============================================================
# PÁGINA: BASE QUALIFICADA (para o consultor)
# Cole como uma nova página do app (ex.: elif pagina == "🎯 Base Qualificada":)
# Lê o CSV gerado por qualificar_base.py.
# ============================================================
from pathlib import Path
import pandas as pd
import streamlit as st

ARQ_QUALIFICADA = (
    Path(__file__).resolve().parent / "data" / "processed" / "BASE_QUALIFICADA_CRM.csv"
)


@st.cache_data
def carregar_base_qualificada():
    return pd.read_csv(ARQ_QUALIFICADA, dtype={"cnpj": str})


df = carregar_base_qualificada()

# ---- banner de honestidade (o rótulo direcional na cara do consultor) ----
st.info(
    "🧭 **Leitura direcional.** Esta priorização usa CNAE + porte — é um ponto "
    "de partida para o consultor, **não uma previsão validada**. O produto "
    "sugerido é hipótese até o contato confirmar."
)

st.subheader("🎯 Base qualificada")

# ============================================================
# FILTROS (todos saem de colunas que a base já tem)
# ============================================================
with st.sidebar:
    st.markdown("### Filtros")

    f_tratamento = st.multiselect(
        "Tratamento",
        sorted(df["tratamento"].dropna().unique()),
        help="Cross-sell = já é cliente · Aquisição = sem vínculo (inferência)",
    )
    f_municipio = st.multiselect(
        "Município", sorted(df["municipio"].dropna().unique())
    )
    f_porte = st.multiselect("Porte", sorted(df["porte"].dropna().unique()))
    f_setor = st.multiselect("Setor", sorted(df["setor"].dropna().unique()))
    f_status = st.multiselect(
        "Status de relacionamento",
        sorted(df["status_relacionamento"].dropna().unique()),
    )
    f_sebrae = st.checkbox("Somente elegíveis SEBRAE")
    prio_min = st.slider("Prioridade comercial mínima", 0, 100, 0, step=5)

# ---- aplica os filtros ----
filtro = df.copy()
if f_tratamento:
    filtro = filtro[filtro["tratamento"].isin(f_tratamento)]
if f_municipio:
    filtro = filtro[filtro["municipio"].isin(f_municipio)]
if f_porte:
    filtro = filtro[filtro["porte"].isin(f_porte)]
if f_setor:
    filtro = filtro[filtro["setor"].isin(f_setor)]
if f_status:
    filtro = filtro[filtro["status_relacionamento"].isin(f_status)]
if f_sebrae and "sebrae_elegivel" in filtro.columns:
    filtro = filtro[filtro["sebrae_elegivel"] == True]  # noqa: E712
filtro = filtro[filtro["prioridade_comercial"] >= prio_min]

# ---- manchete ----
c1, c2, c3 = st.columns(3)
c1.metric("Empresas na seleção", f"{len(filtro):,}")
c2.metric(
    "Cross-sell (já clientes)",
    f"{int((filtro['tratamento'] == 'CROSS-SELL').sum()):,}",
)
c3.metric(
    "Aquisição (novos)",
    f"{int((filtro['tratamento'].str.startswith('AQUISIÇÃO')).sum()):,}",
)

# ---- tabela para o consultor ----
colunas = [
    "cnpj", "razao_social", "municipio", "porte", "setor",
    "tratamento", "prioridade_comercial", "top_produtos", "motivo",
]
colunas = [c for c in colunas if c in filtro.columns]

st.dataframe(
    filtro[colunas].sort_values("prioridade_comercial", ascending=False),
    use_container_width=True,
    hide_index=True,
)

# ---- exportar a seleção filtrada (para levar ao CRM em recortes) ----
st.download_button(
    "⬇️ Baixar seleção (CSV)",
    filtro[colunas].to_csv(index=False, encoding="utf-8-sig"),
    file_name="selecao_qualificada.csv",
    mime="text/csv",
)
