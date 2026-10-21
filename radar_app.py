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

import numpy as np
import pandas as pd
import streamlit as st

from src.sinais.consolidar import ARQ_OFERTAS, aplicar_ofertas, carregar_ofertas, carregar_todos_sinais, marcar_novidades
from src.sinais.cadeias import ARQ_PRODUCAO, carregar_cadeias, industrias_da_cadeia, resumo_cadeia
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
       "Sem empresa identificada": "📰 Sem empresa identificada",
       "Somente SESI": "🔵 Cliente SESI", "Somente SENAI": "🟠 Cliente SENAI", "SESI + SENAI": "🟣 Cliente SESI + SENAI"}


# ------------------------------------------------------------------ dados
def _assinatura() -> tuple:
    arqs = sorted(P.glob("SINAIS_*.csv")) + [ARQ_OFERTAS, ARQ_PRODUCAO, P / "CNPJ_NOMES.csv", P / "PROPENSAO.csv", P / "BASE_MESTRE_COMERCIAL.csv", P / "VISAO_360.csv",
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


def pagina_cadeias():
    sinais, ind = carregar(_assinatura())
    topo("Radar de Oportunidades", "Cadeias produtivas de Alagoas",
         "Onde o campo produz (IBGE), quantas indústrias processam essa produção e quantas já atendemos.")
    cadeias = carregar_cadeias()
    producao = pd.read_csv(ARQ_PRODUCAO, encoding="utf-8-sig") if ARQ_PRODUCAO.exists() else pd.DataFrame()
    if producao.empty:
        st.info("Produção do IBGE ainda não coletada (`python jobs/coletar_ibge.py`, ou aguarde a coleta de segunda-feira). "
                "Mostrando só as indústrias da base.")

    # visão geral: uma linha por cadeia
    linhas = []
    for cid, c in cadeias.items():
        ic = industrias_da_cadeia(ind, c["cnae"])
        p = producao[producao["cadeia"] == cid] if not producao.empty else producao
        linhas.append({"cadeia": c["nome"], "producao": float(p["producao"].sum()) if not p.empty else None,
                       "unidade": c["producao"]["unidade"], "ano": str(p["ano"].max()) if not p.empty else "",
                       "industrias": len(ic), "clientes": int(ic["cliente"].sum()),
                       "sem_relacionamento": int((~ic["cliente"]).sum()),
                       "negocios": " · ".join(c.get("negocios", []))})
    geral = pd.DataFrame(linhas)
    geral["penetracao"] = (geral["clientes"] / geral["industrias"].where(geral["industrias"] > 0)).fillna(0)
    st.dataframe(geral, width="stretch", hide_index=True, column_config={
        "cadeia": "Cadeia", "producao": st.column_config.NumberColumn("Produção em AL", format="localized"),
        "unidade": "Unidade", "ano": "Ano (IBGE)", "industrias": "Indústrias na base",
        "clientes": "Com relacionamento", "sem_relacionamento": "Sem relacionamento",
        "penetracao": st.column_config.ProgressColumn("Penetração", min_value=0, max_value=1, format="percent"),
        "negocios": "Negócios"})

    nomes = {c["nome"]: cid for cid, c in cadeias.items()}
    escolha = st.selectbox("Ver a cadeia por município", list(nomes))
    cid = nomes[escolha]
    cfg = cadeias[cid]
    st.markdown(f"**Oportunidade:** {cfg['oportunidades'].strip()}")
    st.markdown(chips(" · ".join(cfg.get("negocios", []))), unsafe_allow_html=True)
    r = resumo_cadeia(cid, cfg, ind, producao, sinais)
    r = r[(r["producao"] > 0) | (r["industrias"] > 0)]
    k = st.columns(4)
    k[0].metric("Municípios produtores", _n((r["producao"] > 0).sum()))
    top5 = r.nlargest(5, "producao")["participacao_producao"].sum() if r["producao"].sum() else 0
    k[1].metric("5 maiores concentram", f"{top5:.0%}".replace(".", ","))
    k[2].metric("Indústrias da cadeia", _n(r["industrias"].sum()))
    k[3].metric("Sem relacionamento", _n(r["sem_relacionamento"].sum()))
    st.dataframe(r, width="stretch", hide_index=True, height=460, column_config={
        "municipio": "Município",
        "producao": st.column_config.NumberColumn(f"Produção ({cfg['producao']['unidade']})", format="localized"),
        "participacao_producao": st.column_config.ProgressColumn("% da produção de AL", min_value=0,
                                                                 max_value=float(r["participacao_producao"].max() or 1), format="percent"),
        "industrias": "Indústrias", "clientes": "Com relacionamento", "sem_relacionamento": "Sem relacionamento",
        "sinais": "Sinais"})
    st.caption("Município com produção alta e poucas indústrias atendidas = oportunidade de prospecção ou de "
               "ação com produtores e cooperativas. Produção: IBGE (PPM e PAM). Indústrias: Base Mestre, pelo CNAE da cadeia "
               "(config/cadeias.yaml).")
    with st.expander(f"Indústrias da cadeia ({len(industrias_da_cadeia(ind, cfg['cnae']))})"):
        lista = industrias_da_cadeia(ind, cfg["cnae"])
        st.dataframe(lista[["razao_social", "municipio", "porte", "cnae", "cliente"]].sort_values(["cliente", "municipio"]),
                     width="stretch", hide_index=True, column_config={
                         "razao_social": "Empresa", "municipio": "Município", "porte": "Porte", "cnae": "CNAE",
                         "cliente": st.column_config.CheckboxColumn("Já é cliente")})


@st.cache_data(ttl=3600, show_spinner="Montando o mapa ...")
def _pontos(assinatura: tuple):  # noqa: ARG001
    from src.sinais.mapa import carregar_malha, empresas_do_mapa, posicionar
    sinais, ind = carregar(assinatura)
    return posicionar(empresas_do_mapa(ind, sinais), carregar_malha())


@st.cache_data(ttl=3600, show_spinner=False)
def _propensao(assinatura: tuple):  # noqa: ARG001
    arq = P / "PROPENSAO.csv"
    return pd.read_csv(arq, dtype={"cnpj_basico": str}, encoding="utf-8-sig") if arq.exists() else None


@st.cache_data(ttl=3600, show_spinner=False)
def _empresas_todas(assinatura: tuple):  # noqa: ARG001
    from src.sinais.noticias import carregar_empresas
    return carregar_empresas()


def pagina_prioridades():
    from src.sinais.propensao import QUADRANTES, prioridades

    sinais, _ = carregar(_assinatura())
    topo("Radar de Oportunidades", "Prioridades por negócio",
         "Triangulação: quem se parece com quem já compra (modelo) × quem tem sinal agora × onde está.")
    prop = _propensao(_assinatura())
    if prop is None:
        st.warning("Notas de potencial ainda não publicadas. Na máquina local: `python jobs/treinar_propensao.py` "
                   "e depois publicar os dados.")
        return
    neg = st.radio("Negócio", list(NEGOCIOS), horizontal=True, format_func=lambda n: f"{n} · {NEGOCIOS[n]}")
    val_arq = P / "PROPENSAO_VALIDACAO.csv"
    if val_arq.exists():
        val = pd.read_csv(val_arq)
        r = val[(val["negocio"] == neg) & (val["grupo"] == "compradores novos do negócio")]
        r2 = val[(val["negocio"] == neg) & (val["grupo"] == "sem compra anterior em nenhum negócio")]
        if not r.empty and r.iloc[0].get("novos", 0):
            r, r2 = r.iloc[0], (r2.iloc[0] if not r2.empty else None)
            txt = (f"**Teste do modelo:** treinado só com quem comprava até {pd.Timestamp(r['corte']):%m/%Y}, as 10% empresas "
                   f"com maior nota concentraram **{r['top10_captura']:.0%}** dos {int(r['novos'])} compradores novos de {neg} "
                   f"depois disso ({r['top10_captura'] / 0.10:.1f}× o acaso).")
            if r2 is not None and r2.get("novos", 0) >= 15:
                txt += f" Entre empresas sem nenhuma compra anterior: **{r2['top10_captura']:.0%}** ({int(r2['novos'])} casos)."
            elif r2 is not None:
                txt += (f" Para empresas sem nenhuma compra anterior há poucos casos ({int(r2.get('novos', 0))}): "
                        "use a nota principalmente para cross-sell.")
            st.info(txt)
            if r.get("empresas_compradoras", 0) >= 30 and pd.notna(r.get("ticket_medio")):
                st.caption(f"Ticket médio por empresa em {neg} (propostas aceitas): "
                           f"R$ {r['ticket_medio']:,.0f}".replace(",", "."))
    pr = prioridades(prop, _empresas_todas(_assinatura()), sinais, neg)
    c = st.columns(4)
    f_mun = c[0].multiselect("Município", sorted(pr["municipio"].dropna().unique()))
    f_porte = c[1].multiselect("Porte", sorted(pr["Porte"].dropna().astype(str).unique()))
    f_rel = c[2].selectbox("Relação", ["Todas", "Cross-sell (já compra outro negócio)", "Sem compra registrada"])
    so_ind = c[3].toggle("Só indústrias", value=False)
    v = pr
    if f_mun:
        v = v[v["municipio"].isin(f_mun)]
    if f_porte:
        v = v[v["Porte"].astype(str).isin(f_porte)]
    if f_rel.startswith("Cross"):
        v = v[v["relacao"].str.contains("cross-sell")]
    elif f_rel.startswith("Sem"):
        v = v[v["relacao"].eq("Sem compra registrada")]
    if so_ind:
        v = v[v["tipo_empresa"].eq("Indústria")]
    k = st.columns(4)
    for col_, q in zip(k, ["agora", "planejar", "pontual"]):
        col_.metric(QUADRANTES[q], _n((v["quadrante"] == QUADRANTES[q]).sum()))
    k[3].metric("Cross-sell com nota ≥ 90", _n(((v["fit"] >= 90) & v["relacao"].str.contains("cross-sell")).sum()))
    st.caption("🔥 nota ≥ 90 e sinal que aciona o negócio · 📅 nota ≥ 90 sem sinal (prospecção planejada) · "
               "⚡ sinal com nota menor. Nota = percentil do modelo (100 = mais parecida com quem compra).")
    quad = st.multiselect("Quadrante", list(QUADRANTES.values())[:3], default=list(QUADRANTES.values())[:2])
    if quad:
        v = v[v["quadrante"].isin(quad)]
    st.dataframe(v.head(500)[["quadrante", "prioridade", "fit", "momento", "razao_social", "municipio", "Porte",
                              "relacao", "motivo", "sinal", "cnpj_basico"]],
                 width="stretch", hide_index=True, height=520, column_config={
                     "quadrante": "Quadrante",
                     "prioridade": st.column_config.ProgressColumn("Prioridade", min_value=0, max_value=100, format="%.0f"),
                     "fit": st.column_config.NumberColumn("Nota (fit)", help="0 a 100: quanto se parece com quem compra"),
                     "momento": st.column_config.NumberColumn("Momento", format="%.1f"),
                     "razao_social": "Empresa", "municipio": "Município", "Porte": "Porte", "relacao": "Relação",
                     "motivo": "Por que", "sinal": "Sinal agora", "cnpj_basico": "CNPJ raiz"})
    st.download_button(f"⬇️ Baixar prioridades {neg} (CSV para Excel / Moskit)",
                       v.drop(columns=[c_ for c_ in v.columns if c_.startswith("compra_")]).to_csv(index=False, sep=";")
                       .encode("utf-8-sig"), file_name=f"prioridades_{neg}_{pd.Timestamp.now():%Y-%m-%d}.csv",
                       mime="text/csv")


def pagina_mapa():
    import pydeck as pdk

    from src.sinais.mapa import COR_CLIENTE, COR_OPORTUNIDADE, COR_SEM_REL, carregar_malha, malha_com_indicadores

    sinais, ind = carregar(_assinatura())
    topo("Radar de Oportunidades", "Mapa de Alagoas",
         "Onde estão as indústrias, quem já é cliente e onde o radar encontrou oportunidade agora.")
    malha = carregar_malha()
    emp = _pontos(_assinatura())

    # ---------------- filtros
    c = st.columns([2, 2, 2, 3])
    f_setor = c[0].multiselect("Setor", sorted(emp["setor_cni"].dropna().unique()))
    f_porte = c[1].multiselect("Porte", sorted(emp["porte"].dropna().astype(str).unique()))
    neg = c[2].selectbox("Negócio", ["Todos"] + list(NEGOCIOS),
                         help="Escolha um negócio para ver clientes, oportunidades e o potencial (modelo lookalike) dele.")
    prop = _propensao(_assinatura()) if neg != "Todos" else None
    if neg != "Todos" and prop is None:
        st.info("Notas de potencial ainda não publicadas (rode `python jobs/treinar_propensao.py`). "
                "Mostrando só os sinais do negócio.")
    cadeias = carregar_cadeias()
    opcoes = {"Indústrias sem relacionamento": "sem_relacionamento", "Penetração (clientes ÷ indústrias)": "penetracao",
              "Sinais do radar (90 dias)": "sinais_90d", "VAB da indústria (IBGE)": "vab_industria_mil"}
    opcoes.update({f"Produção: {c_['nome']}": f"prod_{cid}" for cid, c_ in cadeias.items()})
    if prop is not None:
        opcoes = {f"Potencial {neg} não atendido (modelo)": "potencial", **opcoes}
    pintar = c[3].selectbox("Pintar os municípios por", list(opcoes))
    if prop is not None:
        rot = {"cli": f"🟢 Clientes {neg}", "sem": "⚪ Demais", "op": f"🟠 Sinal que aciona {neg}",
               "pot": f"🟣 Alto potencial {neg} (nota ≥ 90)"}
    else:
        rot = {"cli": "🟢 Clientes", "sem": "⚪ Sem relacionamento", "op": "🟠 Com oportunidade no radar"}
    c2 = st.columns(len(rot))
    ver = {k: c2[i].toggle(r, value=True) for i, (k, r) in enumerate(rot.items())}

    v = emp
    if f_setor:
        v = v[v["setor_cni"].isin(f_setor)]
    if f_porte:
        v = v[v["porte"].astype(str).isin(f_porte)]
    if neg != "Todos":
        aciona = v["negocios_sinal"].fillna("").str.contains(neg)
        if prop is not None:
            pp = prop[["cnpj_basico", f"fit_{neg}", f"compra_{neg}"]].rename(columns={f"fit_{neg}": "fit",
                                                                                       f"compra_{neg}": "compra_neg"})
            v = v.merge(pp, on="cnpj_basico", how="left")
            aciona = v["negocios_sinal"].fillna("").str.contains(neg)
            v["status"] = np.select([v["compra_neg"].eq(1), aciona, v["fit"].fillna(0) >= 90],
                                    [f"Cliente {neg}", f"Sinal que aciona {neg}", f"Alto potencial {neg}"], "Demais")
            chave = {f"Cliente {neg}": "cli", f"Sinal que aciona {neg}": "op", f"Alto potencial {neg}": "pot",
                     "Demais": "sem"}
        else:
            v = v[aciona]
            chave = {"Cliente": "cli", "Sem relacionamento": "sem", "Com oportunidade no radar": "op"}
    else:
        chave = {"Cliente": "cli", "Sem relacionamento": "sem", "Com oportunidade no radar": "op"}
    v = v[v["status"].map(chave).map(ver).fillna(False).astype(bool)]

    # ---------------- indicadores por município (respeitam setor e porte)
    base_ind = ind
    if f_setor:
        base_ind = base_ind[base_ind["setor_cni"].isin(f_setor)]
    if f_porte:
        base_ind = base_ind[base_ind["porte"].astype(str).isin(f_porte)]
    mun = mercado_municipios(base_ind, sinais)
    if ARQ_PRODUCAO.exists():
        prod = pd.read_csv(ARQ_PRODUCAO, encoding="utf-8-sig")
        prod = prod.sort_values("ano").drop_duplicates(["cadeia", "municipio"], keep="last")
        piv = prod.pivot_table(index="municipio", columns="cadeia", values="producao", aggfunc="sum")
        piv.columns = [f"prod_{c_}" for c_ in piv.columns]
        mun = mun.merge(piv.reset_index(), on="municipio", how="left")
    if prop is not None:
        e_all = _empresas_todas(_assinatura())
        pot = prop[prop[f"compra_{neg}"].eq(0)][["cnpj_basico", f"fit_{neg}"]].merge(
            e_all[["cnpj_basico", "municipio"]], on="cnpj_basico")
        pot = pot[pot[f"fit_{neg}"] >= 90].groupby("municipio").size().rename("potencial").reset_index()
        mun = mun.merge(pot, on="municipio", how="outer").fillna({"potencial": 0})
    col = opcoes[pintar]
    if col not in mun:
        st.info("Esse indicador ainda não foi coletado (aguarde a coleta do IBGE de segunda-feira).")
        mun[col] = 0
    if col == "penetracao":
        fmt = lambda x: f"{x:.0%}"  # noqa: E731
    elif col == "vab_industria_mil":
        fmt = lambda x: f"R$ {x / 1000:,.0f} mi".replace(",", ".")  # noqa: E731
    elif col.startswith("prod_"):
        un = cadeias[col[5:]]["producao"]["unidade"]
        fmt = lambda x, un=un: f"{x:,.0f} {un}".replace(",", ".")  # noqa: E731
    elif col == "potencial":
        fmt = lambda x: f"{_n(x)} empresas com nota ≥ 90 que ainda não compram"  # noqa: E731
    else:
        fmt = lambda x: _n(x)  # noqa: E731
    geo = malha_com_indicadores(malha, mun, col, pintar, fmt)

    # ---------------- pontos
    cores = {"cli": COR_CLIENTE, "sem": COR_SEM_REL, "op": COR_OPORTUNIDADE, "pot": [123, 63, 191]}
    k_ = v["status"].map(chave)
    v = v.assign(cor=[cores.get(x, COR_SEM_REL) + [235] for x in k_],
                 raio=np.select([k_.eq("op"), k_.eq("pot")], [900, 700], 380))
    v["titulo"] = v["razao_social"].fillna("").astype(str)
    porte = v["porte"].where(v["porte"].notna(), "").astype(str).replace({"nan": ""})
    v["detalhe"] = [" · ".join(x for x in (m, p_, st_) if x) for m, p_, st_ in zip(v["municipio"], porte, v["status"])]
    tem = v["n_sinais"] > 0
    v["oport"] = np.where(tem, "Oportunidade: " + v["oportunidade"].fillna("").astype(str), "")
    v["neg"] = np.where(tem, "Negócios: " + v["negocios_sinal"].fillna("").astype(str) + "  ·  clique para ver o que oferecer", "")
    v = v.sort_values("n_sinais")  # oportunidades desenhadas por cima
    camadas = [
        pdk.Layer("GeoJsonLayer", geo["features"], id="municipios", pickable=True, stroked=True, filled=True,
                  get_fill_color="properties.cor", get_line_color=[90, 100, 120, 160], line_width_min_pixels=0.6),
        pdk.Layer("ScatterplotLayer", v[["lon", "lat", "cor", "raio", "titulo", "detalhe", "oport", "neg", "cnpj_basico", "municipio"]],
                  id="empresas", pickable=True, get_position=["lon", "lat"], get_fill_color="cor", get_radius="raio",
                  radius_min_pixels=2, radius_max_pixels=11, stroked=True, get_line_color=[255, 255, 255, 200],
                  line_width_min_pixels=0.4),
    ]
    evento = st.pydeck_chart(
        pdk.Deck(layers=camadas, initial_view_state=pdk.ViewState(latitude=-9.6, longitude=-36.6, zoom=7.7),
                 tooltip={"html": "<b>{titulo}</b><br/>{detalhe}<br/>{oport}<br/><i>{neg}</i>", "style": {"fontSize": "12px", "maxWidth": "320px"}},
                 map_style=None),
        height=620, on_select="rerun", selection_mode="single-object", key="mapa_al")
    sel = (getattr(getattr(evento, "selection", None), "objects", None) or {}) if evento else {}
    emp_sel = (sel.get("empresas") or [None])[0]
    mun_sel = (sel.get("municipios") or [None])[0]
    mun_clicado = (emp_sel or {}).get("municipio") or ((mun_sel or {}).get("properties") or {}).get("municipio")

    if emp_sel:
        cnpj = str(emp_sel.get("cnpj_basico"))
        e = emp[emp["cnpj_basico"].astype(str) == cnpj]
        ops_emp = sinais[sinais["cnpj_basico"].astype(str) == cnpj].sort_values("score_momento", ascending=False) \
            if not sinais.empty else sinais
        st.markdown(f"##### 📌 {emp_sel.get('titulo', '')}")
        if not e.empty:
            r0 = e.iloc[0]
            st.caption(" · ".join(str(x) for x in [r0["municipio"], r0["porte"], r0["setor_cni"], r0["status"]]
                                  if pd.notna(x) and str(x)))
        if ops_emp.empty:
            st.info("Sem oportunidade ativa no radar para esta empresa. "
                    + ("Já é cliente." if not e.empty and bool(e.iloc[0]["cliente"]) else
                       "Ainda não é cliente: entra na prospecção pelo setor e porte."))
        for _, s_ in ops_emp.iterrows():
            cartao(s_)

    leg = st.columns(len(rot) + 1)
    for i, (k, nome) in enumerate(rot.items()):
        leg[i].markdown(f"<span style='display:inline-block;width:.8rem;height:.8rem;border-radius:50%;"
                        f"background:rgb{tuple(cores[k])};margin-right:.4rem'></span>{nome[2:]} "
                        f"(**{_n((v['status'].map(chave) == k).sum())}**)", unsafe_allow_html=True)
    leg[-1].caption(f"Municípios: mais escuro = mais {pintar.lower()}.")
    st.caption("Cada ponto é uma empresa, posicionada dentro do seu município (a base ainda não tem endereço geocodificado; "
               "o ponto não é o endereço). Passe o mouse para ver a empresa; clique no ponto para ver a oportunidade e o que "
               "oferecer, ou no município para ver o detalhe dele.")

    # ---------------- detalhe do município
    st.markdown("##### Olhar um município")
    lista_mun = ["—"] + mun.sort_values("industrias", ascending=False)["municipio"].tolist()
    escolha = st.selectbox("Município (ou clique no mapa)", lista_mun,
                           index=lista_mun.index(mun_clicado) if mun_clicado in lista_mun else 0)
    if escolha != "—":
        r = mun.set_index("municipio").loc[escolha]
        k = st.columns(4)
        k[0].metric("Indústrias", _n(r.get("industrias", 0)))
        k[1].metric("Clientes", _n(r.get("clientes", 0)))
        k[2].metric("Sem relacionamento", _n(r.get("sem_relacionamento", 0)))
        k[3].metric("Sinais (90 dias)", _n(r.get("sinais_90d", 0)))
        ops = sinais[sinais["municipio"] == escolha].sort_values("score_momento", ascending=False) if not sinais.empty \
            else sinais
        if not ops.empty:
            st.markdown("**Oportunidades no radar**")
            st.dataframe(ops[["rotulo_tipo", "descricao", "razao_social", "STATUS_RELACIONAMENTO_REAL", "negocios",
                              "oferta_senai", "oferta_sesi"]], width="stretch", hide_index=True, column_config={
                "rotulo_tipo": "Sinal", "descricao": "O que aconteceu", "razao_social": "Empresa",
                "STATUS_RELACIONAMENTO_REAL": "Relacionamento", "negocios": "Negócios",
                "oferta_senai": "Ofertar SENAI", "oferta_sesi": "Ofertar SESI"})
        lista = emp[emp["municipio"] == escolha].sort_values(["n_sinais", "cliente"], ascending=[False, True])
        st.markdown(f"**Empresas ({_n(len(lista))})**")
        st.dataframe(lista[["razao_social", "status", "porte", "setor_cni", "oportunidade"]], width="stretch",
                     hide_index=True, height=360, column_config={
                         "razao_social": "Empresa", "status": "Situação", "porte": "Porte", "setor_cni": "Setor",
                         "oportunidade": "Oportunidade"})
        st.download_button("⬇️ Baixar lista do município (CSV)",
                           lista.drop(columns=["lon", "lat"]).to_csv(index=False, sep=";").encode("utf-8-sig"),
                           file_name=f"radar_{escolha}.csv", mime="text/csv")


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
              st.Page(pagina_sinais, title="Sinais", icon="📋"),
              st.Page(pagina_prioridades, title="Prioridades por negócio", icon="🎯")],
    "Inteligência": [st.Page(pagina_mapa, title="Mapa de Alagoas", icon="📍"),
                     st.Page(pagina_mercado, title="Mercado", icon="🗺️"),
                     st.Page(pagina_cadeias, title="Cadeias produtivas", icon="🌾"),
                     st.Page(pagina_metas, title="Negócios e metas 2027", icon="🎯")],
    "Governança": [st.Page(pagina_fontes, title="Saúde das fontes", icon="🚦")],
})
st.sidebar.caption("SENAI · SESI · Alagoas — Inteligência de Dados e Mercado")
pg.run()
