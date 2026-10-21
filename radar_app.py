"""
Radar de Oportunidades — SENAI · SESI · Alagoas

Painel separado do de Inteligência Comercial, para olhar TODO DIA:
o que está acontecendo no mercado industrial de Alagoas, com quem,
o que isso significa para SSI, STI, EP e EB, e onde agir.

Lê os mesmos dados do painel comercial (Base Mestre, Visão 360) e os sinais
coletados pelos jobs diários (CNO, notícias, IBGE). Não guarda dono nem status
de negociação: isso fica no Moskit.

Rodar:  streamlit run radar_app.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.sinais.consolidar import ARQ_OFERTAS, aplicar_ofertas, carregar_ofertas, carregar_todos_sinais, marcar_novidades
from src.sinais.mercado import (NEGOCIOS, carregar_industrias, carregar_metas, mercado_municipios,
                                mercado_setores, visao_negocios)
from src.tools.municipios import padronizar

RAIZ = Path(__file__).resolve().parent
P = RAIZ / "data" / "processed"

st.set_page_config(page_title="Radar de Oportunidades · AL", page_icon="📡", layout="wide")

st.markdown("""
<style>
.radar-topo{padding:.2rem 0 1rem;border-bottom:1px solid rgba(128,128,128,.25);margin-bottom:1.2rem}
.radar-topo .k{font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:#B85C00;font-weight:700}
.radar-topo h1{margin:.1rem 0 0;font-size:2rem}
.radar-topo p{margin:.2rem 0 0;opacity:.75}
.chip{display:inline-block;padding:.1rem .55rem;margin:0 .25rem .2rem 0;border-radius:999px;
      font-size:.78rem;font-weight:700;background:rgba(11,58,117,.12);color:inherit}
.chip.SSI{background:rgba(30,91,58,.18)} .chip.STI{background:rgba(11,58,117,.18)}
.chip.EP{background:rgba(242,140,40,.25)} .chip.EB{background:rgba(120,60,160,.18)}
</style>
""", unsafe_allow_html=True)

REL = {"Sem relacionamento": "🎯 Sem relacionamento", "Fora da Base Mestre": "➕ Fora da base",
       "Somente SESI": "🔵 Cliente SESI", "Somente SENAI": "🟠 Cliente SENAI", "SESI + SENAI": "🟣 Cliente SESI + SENAI"}


# ------------------------------------------------------------------ dados
def _assinatura() -> tuple:
    arqs = sorted(P.glob("SINAIS_*.csv")) + [ARQ_OFERTAS, P / "BASE_MESTRE_COMERCIAL.csv", P / "VISAO_360.csv",
                                               P / "INDICADORES_MUNICIPIOS.csv"]
    return tuple((a.name, a.stat().st_mtime) for a in arqs if a.exists())


@st.cache_data(ttl=3600, show_spinner="Carregando o radar ...")
def carregar(assinatura: tuple):  # noqa: ARG001 — a assinatura invalida o cache quando um arquivo muda
    sinais = carregar_todos_sinais()
    if not sinais.empty:
        sinais = aplicar_ofertas(sinais, carregar_ofertas())
        sinais["municipio"] = padronizar(sinais["municipio"].fillna("").astype(str).str.title())
        sinais = marcar_novidades(sinais, pd.Timestamp.now(tz="America/Maceio").date(), 7)
        for c in ("casamento", "url_fonte", "tema", "negocios", "candidatos"):
            if c not in sinais:
                sinais[c] = ""
        sinais["casamento"] = sinais["casamento"].replace("", pd.NA).fillna(
            sinais["cnpj_basico"].notna().map({True: "por CNPJ", False: "sem empresa"}))
    ind = carregar_industrias()
    return sinais, ind


def topo(kicker: str, titulo: str, sub: str) -> None:
    st.markdown(f"<div class='radar-topo'><div class='k'>{kicker}</div><h1>{titulo}</h1><p>{sub}</p></div>",
                unsafe_allow_html=True)


def chips(negocios: str) -> str:
    return "".join(f"<span class='chip {n.strip()}'>{n.strip()}</span>" for n in str(negocios).split("·") if n.strip())


def _n(x) -> str:
    return f"{int(x):,}".replace(",", ".")


def cartao(s) -> None:
    with st.container(border=True):
        c1, c2 = st.columns([5, 1])
        empresa = s["razao_social"] if str(s.get("razao_social") or "").strip() else "Empresa não identificada"
        c1.markdown(f"{s.get('icone', '•')} **{s.get('rotulo_tipo', '')}** · **{empresa}**")
        c2.markdown(f"<div style='text-align:right'>Momento <b>{float(s['score_momento']):.1f}</b></div>",
                    unsafe_allow_html=True)
        data = pd.Timestamp(s["data_publicacao"]).strftime("%d/%m/%Y") if pd.notna(s["data_publicacao"]) else "—"
        rel = REL.get(s.get("STATUS_RELACIONAMENTO_REAL"), s.get("STATUS_RELACIONAMENTO_REAL") or "")
        st.caption(" · ".join(x for x in [str(s.get("municipio") or ""), data, str(s.get("fonte") or ""),
                                         rel if empresa != "Empresa não identificada" else ""] if x))
        st.markdown(f"**{s['descricao']}**")
        if s.get("negocios"):
            st.markdown(chips(s["negocios"]), unsafe_allow_html=True)
        ofertas = [f"SESI: {s['oferta_sesi']}" if s.get("oferta_sesi") else "",
                   f"SENAI: {s['oferta_senai']}" if s.get("oferta_senai") else "",
                   f"Outros: {s['oferta_outros']}" if s.get("oferta_outros") else ""]
        ofertas = " · ".join(o for o in ofertas if o)
        if ofertas:
            st.markdown(f"💡 **O que oferecer:** {ofertas}")
        if s.get("abordagem"):
            st.markdown(f"🗣️ **Como abordar:** {s['abordagem']}")
        if str(s.get("url_fonte") or "").startswith("http"):
            st.markdown(f"[Ler na fonte ↗]({s['url_fonte']})")


# ------------------------------------------------------------------ páginas
def pagina_hoje():
    sinais, ind = carregar(_assinatura())
    hoje = pd.Timestamp.now(tz="America/Maceio")
    topo(f"Radar de Oportunidades · {hoje:%d/%m/%Y}", "O que mudou no mercado",
         "Sinais de mercado da indústria de Alagoas: quem se moveu, o que isso aciona em SSI, STI, EP e EB, e por onde começar.")
    if sinais.empty:
        st.warning("Ainda não há sinais coletados. Rode `python jobs/coletar_noticias.py` ou aguarde a coleta automática diária.")
        return
    novos = sinais[sinais["novo"]]
    quentes = novos[novos["STATUS_RELACIONAMENTO_REAL"].isin(["Sem relacionamento", "Fora da Base Mestre"])
                    & novos["cnpj_basico"].notna()]
    k = st.columns(4)
    k[0].metric("Sinais novos (7 dias)", _n(len(novos)))
    k[1].metric("Empresas identificadas", _n(novos["cnpj_basico"].nunique()))
    k[2].metric("🎯 Ainda não são clientes", _n(quentes["cnpj_basico"].nunique()))
    k[3].metric("Sinais ativos no radar", _n(len(sinais)))

    st.markdown("##### O que os sinais acionam")
    cols = st.columns(len(NEGOCIOS))
    for col, (cod, nome) in zip(cols, NEGOCIOS.items()):
        n = int(sinais["negocios"].fillna("").str.contains(cod).sum())
        nn = int(novos["negocios"].fillna("").str.contains(cod).sum())
        col.metric(f"{cod} · {nome}", f"{_n(n)} sinais", f"{nn} novos" if nn else None)

    esq, dir_ = st.columns([3, 2], gap="large")
    with esq:
        st.markdown("##### Prioridades de hoje")
        base = novos if not novos.empty else sinais
        prio = base.assign(_emp=base["cnpj_basico"].notna()).sort_values(["_emp", "score_momento"], ascending=False)
        for _, s in prio.head(8).iterrows():
            cartao(s)
    with dir_:
        st.markdown("##### Por tipo de sinal")
        por_tipo = sinais.groupby("rotulo_tipo").agg(sinais=("descricao", "size"), novos=("novo", "sum")) \
            .sort_values("sinais", ascending=False)
        st.dataframe(por_tipo, width="stretch")
        revisar = sinais[sinais["casamento"] == "a revisar"]
        st.markdown(f"##### A revisar ({len(revisar)})")
        st.caption("Notícias em que o nome citado pode ser mais de uma empresa da base. Confirme antes de abordar.")
        st.dataframe(revisar[["descricao", "nome_citado", "candidatos"]].head(15) if "nome_citado" in revisar
                     else revisar[["descricao"]].head(15), width="stretch", hide_index=True,
                     column_config={"descricao": "Notícia", "nome_citado": "Nome citado", "candidatos": "Pode ser"})


def pagina_sinais():
    sinais, _ = carregar(_assinatura())
    topo("Radar de Oportunidades", "Todos os sinais", "Filtre, confira a evidência e baixe a lista para o comercial ou para o Moskit.")
    if sinais.empty:
        st.info("Sem sinais ainda.")
        return
    c = st.columns(4)
    f_tipo = c[0].multiselect("Tipo de sinal", sorted(sinais["rotulo_tipo"].dropna().unique()))
    f_neg = c[1].multiselect("Negócio", list(NEGOCIOS))
    f_mun = c[2].multiselect("Município", sorted(m for m in sinais["municipio"].dropna().unique() if m))
    f_rel = c[3].multiselect("Relacionamento", sorted(sinais["STATUS_RELACIONAMENTO_REAL"].dropna().unique()))
    c2 = st.columns(3)
    so_novos = c2[0].toggle("Só novos (7 dias)")
    so_emp = c2[1].toggle("Só com empresa identificada")
    v = sinais
    if f_tipo:
        v = v[v["rotulo_tipo"].isin(f_tipo)]
    if f_neg:
        v = v[v["negocios"].fillna("").apply(lambda x: any(n in x for n in f_neg))]
    if f_mun:
        v = v[v["municipio"].isin(f_mun)]
    if f_rel:
        v = v[v["STATUS_RELACIONAMENTO_REAL"].isin(f_rel)]
    if so_novos:
        v = v[v["novo"]]
    if so_emp:
        v = v[v["cnpj_basico"].notna()]
    v = v.sort_values(["novo", "score_momento"], ascending=False)
    st.caption(f"{_n(len(v))} sinais")
    tabela = v.assign(selo=v["novo"].map({True: "🆕", False: ""}),
                      tipo=v["icone"].fillna("") + " " + v["rotulo_tipo"].fillna(""),
                      relacionamento=v["STATUS_RELACIONAMENTO_REAL"].map(REL).fillna(v["STATUS_RELACIONAMENTO_REAL"]),
                      url=v["url_fonte"].where(v["url_fonte"].astype(str).str.startswith("http"), None))
    st.dataframe(
        tabela[["selo", "tipo", "score_momento", "descricao", "razao_social", "cnpj", "relacionamento", "negocios",
                "oferta_sesi", "oferta_senai", "municipio", "data_publicacao", "casamento", "url"]],
        width="stretch", hide_index=True, height=520,
        column_config={
            "selo": st.column_config.TextColumn(" ", width="small"), "tipo": "Sinal",
            "score_momento": st.column_config.ProgressColumn("Momento", min_value=0,
                                                             max_value=float(sinais["score_momento"].max() or 1), format="%.1f"),
            "descricao": "O que aconteceu", "razao_social": "Empresa", "cnpj": "CNPJ",
            "relacionamento": "Relacionamento", "negocios": "Negócios", "oferta_sesi": "Ofertar SESI",
            "oferta_senai": "Ofertar SENAI", "municipio": "Município",
            "data_publicacao": st.column_config.DateColumn("Publicado em", format="DD/MM/YYYY"),
            "casamento": "Identificação", "url": st.column_config.LinkColumn("Fonte", display_text="abrir ↗"),
        })
    st.download_button("⬇️ Baixar lista (CSV para Excel / Moskit)",
                       tabela.drop(columns=["selo"]).to_csv(index=False, sep=";").encode("utf-8-sig"),
                       file_name=f"radar_sinais_{pd.Timestamp.now():%Y-%m-%d}.csv", mime="text/csv")


def pagina_mercado():
    sinais, ind = carregar(_assinatura())
    topo("Radar de Oportunidades", "Mercado e mercados não atendidos",
         "Onde a indústria pesa na economia (IBGE), quanto dela já atendemos e onde há movimento agora.")
    setores = mercado_setores(ind, sinais)
    st.markdown("##### Por setor (régua do Perfil Setorial da Indústria / CNI)")
    st.dataframe(setores, width="stretch", hide_index=True, column_config={
        "setor_cni": "Setor", "industrias": "Indústrias", "clientes": "Com relacionamento",
        "sem_relacionamento": "Sem relacionamento",
        "penetracao": st.column_config.ProgressColumn("Penetração", min_value=0, max_value=1, format="percent"),
        "empresas_com_sinal": "Empresas com sinal"})

    mun = mercado_municipios(ind, sinais)
    st.markdown("##### Por município")
    tem_ibge = "vab_industria_mil" in mun
    if not tem_ibge:
        st.info("Indicadores do IBGE ainda não coletados (`python jobs/coletar_ibge.py`). Mostrando só a base.")
    else:
        mun["vab_industria_mi"] = (mun["vab_industria_mil"] / 1000).round(1)
        mun["pib_mi"] = (mun["pib_mil"] / 1000).round(1)
        mun["part_industria_vab"] = mun["part_industria_vab"] / 100
    cols = ["municipio", "industrias", "clientes", "sem_relacionamento", "penetracao", "sinais_90d"] + \
           (["vab_industria_mi", "part_industria_vab", "pib_mi", "populacao"] if tem_ibge else [])
    st.dataframe(mun[cols], width="stretch", hide_index=True, height=460, column_config={
        "municipio": "Município", "industrias": "Indústrias", "clientes": "Com relacionamento",
        "sem_relacionamento": "Sem relacionamento",
        "penetracao": st.column_config.ProgressColumn("Penetração", min_value=0, max_value=1, format="percent"),
        "sinais_90d": "Sinais (90 dias)", "vab_industria_mi": "VAB indústria (R$ mi)",
        "part_industria_vab": st.column_config.NumberColumn("Indústria no VAB", format="percent"),
        "pib_mi": "PIB (R$ mi)", "populacao": "População"})
    st.caption("Mercado não atendido = muitas indústrias sem relacionamento e indústria com peso relevante na economia local. "
               "Fonte: Base Mestre, Visão 360 e IBGE (PIB dos Municípios e estimativa de população).")


def pagina_metas():
    sinais, ind = carregar(_assinatura())
    metas = carregar_metas()
    topo("Radar de Oportunidades", "Negócios e metas 2027",
         "Para cada negócio: quem já compra, quem pode comprar e quantos sinais de mercado o acionam agora.")
    neg = visao_negocios(ind, sinais, metas)
    for _, r in neg.iterrows():
        with st.container(border=True):
            st.markdown(f"**{r['negocio']} · {r['nome']}**")
            k = st.columns(6 if metas is not None else 5)
            k[0].metric("Clientes ativos", _n(r["clientes_ativos"]))
            k[1].metric("Para reativar", _n(r["para_reativar"]))
            k[2].metric("Cross-sell", _n(r["cross_sell"]))
            k[3].metric("Para prospectar", _n(r["para_prospectar"]))
            k[4].metric("Sinais ativos", _n(r["sinais_ativos"]), f"{_n(r['empresas_com_sinal'])} empresas", delta_color="off")
            if metas is not None:
                k[5].metric("Meta 2027", f"R$ {r.get('meta_2027', 0)/1e6:,.2f} mi".replace(",", "X").replace(".", ",").replace("X", "."),
                            f"1º TRI R$ {r.get('meta_1tri', 0)/1e3:,.0f} mil".replace(",", "."), delta_color="off")
    if metas is None:
        st.info("**Metas 2027 ainda não carregadas.** Salve o planejamento em `data/privado/METAS_2027.xlsx` com as colunas "
                "`negocio` (SSI, STI, EP, EB), `produto`, `unidade`, `mes` (1 a 12) e `meta` (R$). "
                "O radar lê sempre a versão mais recente: se o planejamento mudar, é só salvar de novo.")
    else:
        st.caption(f"Metas lidas de `{metas.attrs.get('arquivo', '')}`.")


def pagina_fontes():
    from painel_sinais import render_saude_fontes
    render_saude_fontes()


pg = st.navigation({
    "Radar": [st.Page(pagina_hoje, title="Hoje", icon="📡", default=True),
              st.Page(pagina_sinais, title="Sinais", icon="📋")],
    "Inteligência": [st.Page(pagina_mercado, title="Mercado", icon="🗺️"),
                     st.Page(pagina_metas, title="Negócios e metas 2027", icon="🎯")],
    "Governança": [st.Page(pagina_fontes, title="Saúde das fontes", icon="🚦")],
})
st.sidebar.caption("SENAI · SESI · Alagoas — Inteligência de Dados e Mercado")
pg.run()
