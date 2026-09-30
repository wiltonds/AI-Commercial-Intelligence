"""Página "🔗 Canais e Conexões" — quem conecta muitas empresas de uma vez.

Lê a versão pública do mapa de hubs (jobs/mapear_hubs.py): canais identificados
por domínio de empresa (escritórios de contabilidade, consultorias de SST,
assessorias, grupos empresariais). Telefones, e-mails pessoais e sócios em
comum ficam só no arquivo local data/privado/HUBS_CANAIS.xlsx.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[2]
ARQ_CANAIS = RAIZ / "data" / "processed" / "HUBS_CANAIS_PUBLICO.csv"
ARQ_MEMBROS = RAIZ / "data" / "processed" / "HUBS_MEMBROS_PUBLICO.csv"
ARQ_360 = RAIZ / "data" / "processed" / "VISAO_360.csv"
POR_QUE = {
    "Contabilidade": "Atende a carteira inteira na parte fiscal e trabalhista — pode apresentar o Sistema a todas de uma vez.",
    "Consultoria de SST": "Vende saúde e segurança para várias indústrias: para o SESI, pode ser concorrente ou parceira.",
    "Assessoria / despachante": "Cuida da parte burocrática de várias empresas — porta de entrada para regularização (NRs, PGR).",
    "Grupo empresarial": "Várias empresas da mesma organização: uma negociação, vários CNPJs.",
    "Outro": "Contato comum a várias empresas — vale entender quem é.",
}


def _n(x) -> str:
    return f"{int(x):,}".replace(",", ".")


def render() -> None:
    st.header("🔗 Canais e Conexões")
    if not ARQ_CANAIS.exists():
        st.info("Mapa de canais ainda não gerado. Rode `python jobs/mapear_hubs.py` e publique.")
        return
    c = pd.read_csv(ARQ_CANAIS, encoding="utf-8-sig")
    if c.empty:
        st.info("Nenhum canal com 5 ou mais empresas encontrado.")
        return
    st.caption("Um modelo que aprende com o passado enxerga empresas; parte da oportunidade está nas conexões entre elas. "
               "Aqui: contatos de empresa (domínio de e-mail) cadastrados em 5 ou mais empresas da base. "
               "Telefones, e-mails pessoais e sócios em comum ficam só na versão local (data/privado).")
    tipos = sorted(c["tipo_canal"].dropna().unique())
    escolha = st.multiselect("Tipo de canal", tipos, default=tipos)
    c = c[c["tipo_canal"].isin(escolha)]

    k = st.columns(4)
    k[0].metric("Canais", _n(len(c)))
    k[1].metric("Empresas alcançáveis", _n(c["empresas"].sum()), help="Soma dos vínculos: uma empresa pode estar em mais de um canal.")
    k[2].metric("Sem compra", _n(c["sem_compra"].sum()))
    k[3].metric("Com porta de entrada", _n(c["porta_de_entrada"].astype(str).eq("True").sum()),
                help="Canais em que pelo menos uma empresa da carteira já é cliente — dá para pedir a apresentação.")

    st.dataframe(c[["hub", "tipo_canal", "empresas", "ja_clientes", "sem_compra", "segmentos", "exemplos"]]
                 .rename(columns={"hub": "Canal", "tipo_canal": "Tipo", "empresas": "Empresas", "ja_clientes": "Já clientes",
                                  "sem_compra": "Sem compra", "segmentos": "Principais segmentos", "exemplos": "Exemplos"}),
                 use_container_width=True, hide_index=True, height=360)

    st.subheader("Carteira de um canal")
    sel = st.selectbox("Canal", c["hub"].tolist(),
                       format_func=lambda h: f"{h} — {c.loc[c['hub'] == h, 'tipo_canal'].iat[0]} · "
                                             f"{int(c.loc[c['hub'] == h, 'empresas'].iat[0])} empresas")
    tipo = c.loc[c["hub"] == sel, "tipo_canal"].iat[0]
    st.caption(f"**{tipo}:** {POR_QUE.get(tipo, '')}")
    if ARQ_MEMBROS.exists():
        m = pd.read_csv(ARQ_MEMBROS, dtype=str, encoding="utf-8-sig").fillna("")
        m = m[m["hub"] == sel].drop(columns=["hub"])
        if ARQ_360.exists():
            v = pd.read_csv(ARQ_360, dtype=str, encoding="utf-8-sig").fillna("")
            m = m.merge(v[["cnpj_basico", "linhas_ativas", "oportunidades_360", "retomar_360"]], on="cnpj_basico", how="left")
        m = m.rename(columns={"razao_social": "Empresa", "segmento": "Segmento", "situacao": "Situação cliente",
                              "tipo_empresa": "Tipo", "linhas_ativas": "Linhas ativas",
                              "oportunidades_360": "Oportunidades 360", "retomar_360": "Retomar"})
        st.dataframe(m, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Baixar carteira do canal", m.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"carteira_{sel.strip('@').replace('.', '_')}.csv", mime="text/csv")
