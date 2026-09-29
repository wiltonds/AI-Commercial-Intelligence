"""Página "🗓️ Rotina de Dados" — o que precisa ser atualizado, quando e como.

Mesma lógica de jobs/checar_entradas.py (config/entradas.yaml + log de
atualizações), em forma de painel: funciona também no app online, porque o
log é publicado junto com os dados.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
import yaml

from jobs.checar_entradas import ARQ_ENTRADAS, avaliar
from src.tools.log_atualizacoes import ARQ_LOG, ultimas

COR = {"em dia": "🟢", "vence": "🟡", "VENCIDO": "🔴", "NUNCA": "⚪", "FALTANDO": "🔴", "OK": "🟢", "MANUAL": "🔵"}


def _icone(status: str) -> str:
    return next((c for k, c in COR.items() if status.startswith(k)), "⚪")


def render() -> None:
    st.header("🗓️ Rotina de Dados")
    st.caption("O que precisa ser baixado e rodado para o painel ficar em dia. A lista vem de "
               "`config/entradas.yaml`; as datas, do log que cada job grava ao terminar. "
               "Passo a passo completo em `docs/manual_atualizacao.md`.")
    entradas = yaml.safe_load(open(ARQ_ENTRADAS, encoding="utf-8"))["entradas"]
    log = ultimas()
    agora = datetime.now()
    linhas = avaliar(entradas, log, agora)

    pendentes = [x for x in linhas if x["atencao"]]
    c1, c2, c3 = st.columns(3)
    c1.metric("Pendentes", len(pendentes))
    c2.metric("Em dia", sum(1 for x in linhas if x["status"].startswith(("em dia", "OK"))))
    c3.metric("Vencendo em 7 dias", sum(1 for x in linhas if x["status"].startswith("vence")))

    tabela = []
    for x in linhas:
        ult = log.get(x["chave"], {}).get("data")
        proxima = ""
        if ult:
            proxima = (datetime.fromisoformat(ult) + timedelta(days=x["freq"])).strftime("%d/%m/%Y")
        tabela.append({"": _icone(x["status"]), "Entrada": x["nome"], "Situação": x["status"],
                       "Última atualização": x["ultima"], "Próxima prevista": proxima or "-",
                       "Frequência": f"{x['freq']} dias",
                       "Último resultado": log.get(x["chave"], {}).get("resumo", "")})
    st.dataframe(pd.DataFrame(tabela), use_container_width=True, hide_index=True)

    st.subheader("O que fazer agora" if pendentes else "Tudo em dia ✅")
    for x in linhas:
        with st.expander(f"{_icone(x['status'])} {x['nome']} — {x['status']}", expanded=x["atencao"]):
            st.markdown(f"**O que baixar:** {x['como_obter']}")
            if x["colunas"]:
                st.markdown("**Colunas obrigatórias:** " + ", ".join(f"`{c}`" for c in x["colunas"]))
            st.markdown(f"**Onde colocar:** `{x['onde']}`")
            st.markdown("**O que rodar:**")
            for cmd in [c.strip() for c in x["comando"].split(";") if c.strip()]:
                st.code(cmd, language="powershell")
            st.markdown(f"**O que atualiza:** {' '.join(str(entradas[x['chave']].get('atualiza', '')).split())}")

    if ARQ_LOG.exists():
        with st.expander("Histórico de atualizações"):
            st.dataframe(pd.read_csv(ARQ_LOG).iloc[::-1], use_container_width=True, hide_index=True)
