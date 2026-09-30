"""Cartão "Visão 360" de uma empresa — usado no Explorador."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.tools.visao360 import ARQ_360, carregar_linhas

RAIZ = Path(__file__).resolve().parents[2]
ARQ_HUBS = RAIZ / "data" / "privado" / "HUBS_CANAIS.xlsx"
ICONE = {"compra": "✅", "parou": "⏸️", "oportunidade": "🎯", "baixa": "—"}
TEXTO = {"compra": "cliente ativo", "parou": "para reativar", "oportunidade": "para prospectar", "baixa": "pouco comum nesse perfil"}


@st.cache_data(show_spinner=False)
def carregar_360() -> pd.DataFrame:
    if not ARQ_360.exists():
        return pd.DataFrame()
    return pd.read_csv(ARQ_360, dtype=str, encoding="utf-8-sig").fillna("")


@st.cache_data(show_spinner=False)
def carregar_hubs() -> pd.DataFrame:
    if not ARQ_HUBS.exists():
        return pd.DataFrame()
    return pd.read_excel(ARQ_HUBS, sheet_name="Empresas", dtype=str).fillna("")


def _um_em(pct) -> str:
    from src.paginas.casas import um_em
    return um_em(float(pct or 0) / 100)


def cartao(raiz: str, razao: str, detalhe: str) -> None:
    v = carregar_360()
    if v.empty:
        st.info("Visão 360 ainda não calculada. Rode `python jobs/atualizar_relacionamento.py --arquivo data/privado/propostas.xlsx`.")
        return
    linha = v[v["cnpj_basico"] == raiz]
    if linha.empty:
        st.caption("Empresa fora da base industrial — Visão 360 ainda não disponível para ela.")
        return
    r = linha.iloc[0]
    cfg = carregar_linhas()
    with st.container(border=True):
        a, b = st.columns([3, 1])
        a.markdown(f"**{razao}**  \n{detalhe}")
        b.metric("Linhas ativas", f"{r['linhas_ativas']} de {len(cfg['linhas'])}")
        for entidade, col in zip(("SESI", "SENAI"), st.columns(2)):
            with col:
                st.markdown(f"**{entidade}**")
                for cod, l in cfg["linhas"].items():
                    if l["entidade"] != entidade:
                        continue
                    s = r[f"{cod}_status"]
                    extra = {"compra": f"última em {r[f'{cod}_ultima']}", "parou": f"última em {r[f'{cod}_ultima']}",
                             "oportunidade": _um_em(r[f'{cod}_pct']) + " empresas parecidas compram",
                             "baixa": _um_em(r[f'{cod}_pct']) + " empresas parecidas compram"}[s]
                    st.markdown(f"{ICONE[s]} **{cod}** · {l['nome']}  \n<span style='color:gray'>{TEXTO[s]} · {extra}</span>",
                                unsafe_allow_html=True)
        h = carregar_hubs()
        if not h.empty:
            meus = h[h["cnpj_basico"] == raiz]
            for hub, tipo in meus[["hub", "tipo"]].drop_duplicates().itertuples(index=False):
                n = h.loc[h["hub"] == hub, "cnpj_basico"].nunique() - 1
                quem = "Mesmo sócio" if tipo == "grupo" else "Mesmo contato (provável escritório)"
                st.caption(f"🔗 {quem}: {hub} — conecta mais {n} empresa(s)")
        st.caption("✅ cliente ativo (comprou em 24 meses) · ⏸️ para reativar (comprou antes) · "
                   "🎯 para prospectar (empresas do mesmo ramo e porte compram) · — pouco comum nesse perfil.")
