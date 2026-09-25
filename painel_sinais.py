"""
Páginas "⚡ Sinais & Momento" e "🚦 Saúde das Fontes".

Sinais respondem "QUANDO abordar": a Base Mestre já diz quem tem
aderência ao portfólio; aqui entra quem está em movimento agora. Cada
fonte vira um CSV em data/processed/SINAIS_<FONTE>.csv, gerado por um
job em jobs/. Hoje: CNO (obra nova).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.sinais.fontes import carregar_catalogo, carregar_log, saude_das_fontes

RAIZ = Path(__file__).resolve().parent
ARQ_SINAIS_CNO = RAIZ / "data" / "processed" / "SINAIS_CNO.csv"


def _fmt(n) -> str:
    return f"{int(n):,}".replace(",", ".")


@st.cache_data(ttl=3600)
def _carregar_sinais_cno(_mtime: float) -> pd.DataFrame:
    df = pd.read_csv(ARQ_SINAIS_CNO, dtype={"cnpj": str, "cnpj_basico": str, "cno": str},
                     encoding="utf-8-sig")
    df["na_base_mestre"] = df["na_base_mestre"].astype(str).str.upper().eq("TRUE")
    df["STATUS_RELACIONAMENTO_REAL"] = df["STATUS_RELACIONAMENTO_REAL"].fillna("Fora da Base Mestre")
    return df


def render_sinais() -> None:
    st.header("⚡ Sinais & Momento")
    st.caption(
        "A Base Mestre diz **quem** tem aderência ao portfólio. Esta página diz "
        "**quem está em movimento agora**. Score de momento = peso do sinal × "
        "decaimento até a validade (regra em `config/fontes.yaml`)."
    )

    if not ARQ_SINAIS_CNO.exists():
        st.warning(
            "Ainda não há sinais coletados. Rode o job:\n\n"
            "```\npython jobs/coletar_cno.py --arquivo <caminho do cno.zip>\n```\n"
            "O cno.zip é baixado na página de dados abertos do CNO "
            "(link na página 🚦 Saúde das Fontes)."
        )
        return

    df = _carregar_sinais_cno(ARQ_SINAIS_CNO.stat().st_mtime)

    st.info(
        "🏗️ **Obra nova (CNO)** — obra ATIVA registrada na Receita nos últimos "
        "meses, com empresa responsável ou vinculada (construtora, incorporadora). "
        "Oferta natural: PGR/PCMSO, NRs de construção, qualificação do canteiro. "
        "Obras de pessoa física não aparecem (a Receita não publica CPF)."
    )

    with st.expander("Filtros", expanded=True):
        c1, c2, c3 = st.columns(3)
        municipios = sorted(df["municipio"].dropna().str.title().unique())
        f_mun = c1.multiselect("Município da obra", municipios)
        f_rel = c2.multiselect("Relacionamento", sorted(df["STATUS_RELACIONAMENTO_REAL"].unique()))
        f_papel = c3.multiselect("Papel na obra", sorted(df["papel"].dropna().unique()))
        so_base = st.toggle("Só empresas da Base Mestre (universo industrial)", value=False)

    v = df.copy()
    if f_mun:
        v = v[v["municipio"].str.title().isin(f_mun)]
    if f_rel:
        v = v[v["STATUS_RELACIONAMENTO_REAL"].isin(f_rel)]
    if f_papel:
        v = v[v["papel"].isin(f_papel)]
    if so_base:
        v = v[v["na_base_mestre"]]

    quentes = v[v["STATUS_RELACIONAMENTO_REAL"].isin(["Sem relacionamento", "Fora da Base Mestre"])]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Sinais ativos", _fmt(len(v)))
    k2.metric("Empresas distintas", _fmt(v["cnpj_basico"].nunique()))
    k3.metric("Já na Base Mestre", _fmt(v.loc[v["na_base_mestre"], "cnpj_basico"].nunique()))
    k4.metric("Sem relacionamento SESI/SENAI", _fmt(quentes["cnpj_basico"].nunique()),
              help="Prospecção quente: em movimento e ainda não é cliente.")

    st.subheader("Prioridade por momento")
    colunas = [c for c in [
        "score_momento", "razao_social", "cnpj", "STATUS_RELACIONAMENTO_REAL",
        "descricao", "data_evento", "idade_dias", "Porte", "CNAE PRIMARIO", "cno",
    ] if c in v.columns]
    st.dataframe(
        v.sort_values("score_momento", ascending=False)[colunas],
        width="stretch", hide_index=True,
        column_config={
            "score_momento": st.column_config.ProgressColumn(
                "Momento", min_value=0, max_value=float(df["score_momento"].max() or 1),
                format="%.1f"),
            "STATUS_RELACIONAMENTO_REAL": "Relacionamento",
            "descricao": "Sinal",
            "data_evento": "Início da obra",
            "idade_dias": "Dias",
        },
    )

    st.download_button(
        "⬇️ Baixar lista filtrada (CSV)",
        v.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig"),
        file_name="sinais_obra_nova.csv", mime="text/csv",
    )

    st.subheader("Onde estão as obras")
    por_mun = (v.assign(Município=v["municipio"].str.title())
                 .groupby("Município")["cnpj_basico"].nunique()
                 .sort_values(ascending=False).head(15))
    st.bar_chart(por_mun)


def render_saude_fontes() -> None:
    st.header("🚦 Saúde das Fontes")
    st.caption(
        "De onde vem cada dado, com que frequência deveria atualizar, e quando "
        "atualizou de fato. Existe porque as tabelas do DW pararam sem ninguém "
        "perceber — aqui, atraso aparece em vermelho."
    )
    saude = saude_das_fontes(carregar_catalogo(), carregar_log())

    c1, c2, c3 = st.columns(3)
    c1.metric("Fontes no catálogo", len(saude))
    c2.metric("Implementadas", int((saude["status"] == "implementado").sum()))
    c3.metric("Em dia (🟢)", int((saude["semaforo"] == "🟢").sum()))

    st.dataframe(
        saude, width="stretch", hide_index=True,
        column_config={
            "semaforo": " ",
            "link": st.column_config.LinkColumn("Fonte oficial"),
            "dias_desde_sucesso": "Dias desde o último sucesso",
            "tabela_dw": "Equivalente no DW",
        },
    )
    st.caption("🟢 em dia · 🟡 atrasada até 3× a frequência · 🔴 atrasada ou última execução falhou · ⚪ não implementada / nunca rodou")
