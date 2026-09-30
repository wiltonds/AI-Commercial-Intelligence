"""Página "🔗 Canais e Conexões" — escritórios que cuidam de várias empresas ao mesmo tempo.

Ideia em uma frase: um escritório de contabilidade (ou uma consultoria de
segurança do trabalho) atende dezenas de empresas; uma conversa com ele pode
abrir todas de uma vez. Como identificamos: o mesmo domínio de e-mail aparece
no cadastro de 5 ou mais empresas da base.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[2]
ARQ_CANAIS = RAIZ / "data" / "processed" / "HUBS_CANAIS_PUBLICO.csv"
ARQ_MEMBROS = RAIZ / "data" / "processed" / "HUBS_MEMBROS_PUBLICO.csv"
ARQ_360 = RAIZ / "data" / "processed" / "VISAO_360.csv"

TIPOS = {  # nome no plural para os cartões, e a abordagem sugerida
    "Contabilidade": ("Escritórios de contabilidade",
                      "Cuida da parte fiscal e trabalhista das empresas. Proposta: parceria para apresentar SESI e SENAI "
                      "à carteira dele (SST obrigatória, qualificação, aprendizagem)."),
    "Consultoria de SST": ("Consultorias de segurança do trabalho",
                           "Vende saúde e segurança para várias empresas. Pode ser concorrente do SESI ou parceira "
                           "(exames, treinamentos de NR que ela não oferece)."),
    "Assessoria / despachante": ("Assessorias e despachantes",
                                 "Cuida da regularização das empresas. Porta de entrada para documentação de SST "
                                 "(PGR, PCMSO) e cursos obrigatórios."),
    "Grupo empresarial": ("Grupos empresariais",
                          "Várias empresas da mesma organização: uma negociação vale para todos os CNPJs."),
    "Outro": ("Outros contatos compartilhados",
              "Um mesmo contato cadastrado em várias empresas. Vale descobrir quem é antes de abordar."),
}


def _n(x) -> str:
    return f"{int(x):,}".replace(",", ".")


def _nome(hub: str) -> str:
    """@contabilmaceio.com.br -> contabilmaceio.com.br (como a pessoa digitaria no navegador)."""
    return str(hub).lstrip("@")


def render() -> None:
    st.header("🔗 Canais e Conexões")
    st.markdown("Alguns escritórios cuidam de **várias empresas ao mesmo tempo**: contabilidades, consultorias de "
                "segurança do trabalho, assessorias. **Uma conversa com eles pode abrir dezenas de portas.** "
                "Esta tela mostra quais são, quantas empresas cada um atende e quem nunca comprou do Sistema.")
    if not ARQ_CANAIS.exists():
        st.info("Os dados desta tela ainda não foram gerados. Rode `python jobs/mapear_hubs.py` e publique.")
        return
    c = pd.read_csv(ARQ_CANAIS, encoding="utf-8-sig")
    if c.empty:
        st.info("Nenhum escritório atende 5 ou mais empresas da base.")
        return
    m = pd.read_csv(ARQ_MEMBROS, dtype=str, encoding="utf-8-sig").fillna("") if ARQ_MEMBROS.exists() else pd.DataFrame()

    # 1. resumo em uma frase
    st.info(f"Encontramos **{_n(len(c))} escritórios** que, juntos, cuidam de **{_n(c['empresas'].sum())} empresas** "
            f"da base. **{_n(c['sem_compra'].sum())} delas nunca compraram** do SESI ou do SENAI.", icon="💡")

    # 2. um cartão por tipo
    tipos = [t for t in TIPOS if t in set(c["tipo_canal"])]
    for col, t in zip(st.columns(len(tipos)), tipos):
        sub = c[c["tipo_canal"] == t]
        col.metric(TIPOS[t][0], _n(len(sub)), f"cuidam de {_n(sub['empresas'].sum())} empresas", delta_color="off")

    # 3. os que abrem mais portas
    st.subheader("Os que abrem mais portas")
    st.caption("Ordenados por quantas empresas **nunca compraram**. \"Quem pode apresentar\" = cliente nosso que "
               "já trabalha com esse escritório — peça a indicação a ele.")
    tipo_sel = st.multiselect("Tipo", tipos, default=tipos, format_func=lambda t: TIPOS[t][0])
    vis = c[c["tipo_canal"].isin(tipo_sel)].copy()
    clientes = (m[m["situacao"].isin(["Ativo", "Inativo"])].groupby("hub")["razao_social"]
                .agg(lambda s: ", ".join(s.head(2))) if not m.empty else pd.Series(dtype=str))
    vis["Quem pode apresentar"] = vis["hub"].map(clientes).fillna("—")
    tabela = vis.rename(columns={"empresas": "Empresas que atende", "sem_compra": "Nunca compraram"})
    tabela["Escritório"] = tabela["hub"].map(_nome)
    tabela["Tipo"] = tabela["tipo_canal"].map(lambda t: TIPOS.get(t, (t,))[0])
    st.dataframe(tabela[["Escritório", "Tipo", "Empresas que atende", "Nunca compraram", "Quem pode apresentar"]],
                 use_container_width=True, hide_index=True, height=330,
                 column_config={"Nunca compraram": st.column_config.ProgressColumn(
                     format="%d", min_value=0, max_value=int(tabela["Nunca compraram"].max() or 1))})

    # 4. abrir a carteira de um escritório
    st.subheader("Ver as empresas de um escritório")
    if vis.empty:
        return
    sel = st.selectbox("Escritório", vis["hub"].tolist(),
                       format_func=lambda h: f"{_nome(h)} — atende {int(vis.loc[vis['hub'] == h, 'empresas'].iat[0])} empresas")
    t = vis.loc[vis["hub"] == sel, "tipo_canal"].iat[0]
    st.caption(f"**Como abordar:** {TIPOS.get(t, ('', ''))[1]}")
    if m.empty:
        return
    car = m[m["hub"] == sel].copy()
    if ARQ_360.exists():
        v = pd.read_csv(ARQ_360, dtype=str, encoding="utf-8-sig").fillna("")
        car = car.merge(v[["cnpj_basico", "oportunidades_360", "retomar_360"]], on="cnpj_basico", how="left").fillna("")
    car["É cliente?"] = car["situacao"].map({"Ativo": "✅ Sim", "Inativo": "⏸️ Já foi"}).fillna("Não")
    car["O que oferecer"] = car.get("oportunidades_360", "").map(lambda s: " · ".join(x.split(" (")[0] for x in str(s).split("; ") if x))
    car["Retomar"] = car.get("retomar_360", "")
    from src.paginas.casas import acentuar
    car["segmento"] = car.get("segmento", "").map(acentuar)
    car = car.sort_values("É cliente?").rename(columns={"razao_social": "Empresa", "municipio": "Município", "segmento": "Segmento"})
    cols = [c_ for c_ in ["Empresa", "Município", "Segmento", "É cliente?", "O que oferecer", "Retomar"] if c_ in car.columns]
    st.dataframe(car[cols], use_container_width=True, hide_index=True)
    st.download_button("⬇️ Baixar empresas deste escritório", car[cols].to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"carteira_{_nome(sel).replace('.', '_')}.csv", mime="text/csv")
