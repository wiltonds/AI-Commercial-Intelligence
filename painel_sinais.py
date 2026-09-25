"""
Páginas "⚡ Sinais & Momento" e "🚦 Saúde das Fontes".

Sinais respondem "QUANDO abordar e O QUE ofertar": a Base Mestre já
diz quem tem aderência ao portfólio; aqui entra quem está em movimento
agora. A página é genérica: lê todo data/processed/SINAIS_*.csv (um por
fonte/job), marca novidades pela data de publicação na fonte e aplica a
oferta sugerida de config/ofertas.yaml. Fonte nova = job novo, sem mexer
na tela. Hoje: CNO (obra nova).
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import streamlit as st

from src.sinais.consolidar import (
    ARQ_OFERTAS,
    aplicar_ofertas,
    carregar_ofertas,
    carregar_todos_sinais,
    marcar_novidades,
)
from src.sinais.fontes import carregar_catalogo, carregar_log, saude_das_fontes

RAIZ = Path(__file__).resolve().parent
ARQ_SINAIS_CNO = RAIZ / "data" / "processed" / "SINAIS_CNO.csv"
ARQ_TRAVA = RAIZ / "data" / "processed" / ".coletando_cno.lock"
TRAVA_MAX_MIN = 30  # trava mais velha que isso é resto de execução interrompida


REL_BADGE = {
    "Sem relacionamento": "🎯 Sem relacionamento",
    "Fora da Base Mestre": "➕ Fora da Base Mestre",
    "Somente SESI": "🔵 Cliente SESI",
    "Somente SENAI": "🟠 Cliente SENAI",
    "SESI + SENAI": "🟣 Cliente SESI + SENAI",
}


def _assinatura() -> tuple:
    """Muda quando algum SINAIS_*.csv ou o ofertas.yaml muda → invalida o cache."""
    arquivos = sorted(ARQ_SINAIS_CNO.parent.glob("SINAIS_*.csv")) + [ARQ_OFERTAS]
    return tuple((a.name, a.stat().st_mtime) for a in arquivos if a.exists())


@st.cache_data(ttl=3600)
def _carregar_sinais(assinatura: tuple) -> pd.DataFrame:  # noqa: ARG001 (chave do cache)
    df = carregar_todos_sinais()
    return aplicar_ofertas(df, carregar_ofertas()) if not df.empty else df


def _data(valor) -> str:
    return pd.Timestamp(valor).strftime("%d/%m/%Y") if pd.notna(valor) else "—"


def _card(linha) -> None:
    with st.container(border=True):
        c1, c2 = st.columns([4, 1])
        c1.markdown(f"{linha['icone']} **{linha['rotulo_tipo']}** · **{linha['razao_social']}**")
        c2.markdown(f"<div style='text-align:right'>Momento <b>{linha['score_momento']:.1f}</b></div>",
                    unsafe_allow_html=True)
        st.caption(
            f"{REL_BADGE.get(linha['STATUS_RELACIONAMENTO_REAL'], linha['STATUS_RELACIONAMENTO_REAL'])}"
            f" · CNPJ {linha.get('cnpj', '')} · publicado em {_data(linha['data_publicacao'])}"
            f" (há {int(linha['dias_desde_publicacao'])} dias)"
        )
        st.markdown(linha["descricao"])
        ofertas = [f"**SESI:** {linha['oferta_sesi']}" if linha["oferta_sesi"] else "",
                   f"**SENAI:** {linha['oferta_senai']}" if linha["oferta_senai"] else "",
                   f"**Outros:** {linha['oferta_outros']}" if linha["oferta_outros"] else ""]
        perfil = linha["perfil"] + (f" + {linha['perfil_extra']}" if linha["perfil_extra"] else "")
        st.markdown(f"💡 **Ofertar** ({perfil}) — " + " · ".join(o for o in ofertas if o))
        st.markdown(f"🗣️ **Como abordar:** {linha['abordagem']}")


def render_sinais() -> None:
    st.header("⚡ Sinais & Momento")
    st.caption(
        "A Base Mestre diz **quem** tem aderência ao portfólio. Esta página diz **quem está em "
        "movimento agora**, **o que ofertar** e **como abordar**. Ofertas editáveis em "
        "`config/ofertas.yaml`; peso e validade de cada sinal em `config/fontes.yaml`."
    )

    _bloco_atualizacao()

    df = _carregar_sinais(_assinatura())
    if df.empty:
        st.warning(
            "Ainda não há sinais coletados neste servidor. Clique em "
            "**🔄 Atualizar sinais** acima, ou rode na sua máquina:\n\n"
            "```\npython jobs/coletar_cno.py\n```"
        )
        return

    hoje = pd.Timestamp.now(tz="America/Maceio").date()
    dias = st.segmented_control(
        "O que conta como novidade", options=[7, 15, 30], default=7,
        format_func=lambda d: f"Últimos {d} dias",
    ) or 7
    df = marcar_novidades(df, hoje, dias)
    novos = df[df["novo"]]

    # ---------------- NOVIDADES ----------------
    st.subheader(f"🆕 Novidades — últimos {dias} dias")
    quentes = novos[novos["STATUS_RELACIONAMENTO_REAL"].isin(["Sem relacionamento", "Fora da Base Mestre"])]
    k1, k2, k3 = st.columns(3)
    k1.metric("Sinais novos", len(novos))
    k2.metric("Empresas com sinal novo", novos["cnpj_basico"].nunique())
    k3.metric("🎯 Ainda não são clientes", quentes["cnpj_basico"].nunique(),
              help="Sem relacionamento SESI/SENAI ou fora da Base Mestre: prospecção quente.")

    por_tipo = df.groupby(["icone", "rotulo_tipo"]).agg(
        total=("cnpj_basico", "size"), novos=("novo", "sum")).reset_index()
    colunas_tipo = st.columns(max(len(por_tipo), 1))
    for col, (_, t) in zip(colunas_tipo, por_tipo.iterrows()):
        col.metric(f"{t['icone']} {t['rotulo_tipo']}", f"{int(t['novos'])} novos",
                   help=f"{int(t['total'])} sinais ativos no total")

    if novos.empty:
        st.info(f"Nenhum sinal novo nos últimos {dias} dias. Veja todos os sinais ativos abaixo "
                "ou amplie o período.")
    else:
        destaque = novos.sort_values("score_momento", ascending=False).head(8)
        st.caption(f"Os {len(destaque)} sinais novos de maior momento:")
        for _, linha in destaque.iterrows():
            _card(linha)

    # ---------------- TODOS ----------------
    st.subheader("📋 Todos os sinais ativos")
    with st.expander("Filtros", expanded=False):
        c1, c2, c3 = st.columns(3)
        f_tipo = c1.multiselect("Tipo de sinal", sorted(df["rotulo_tipo"].unique()))
        f_mun = c2.multiselect("Município", sorted(df["municipio"].dropna().str.title().unique()))
        f_rel = c3.multiselect("Relacionamento", sorted(df["STATUS_RELACIONAMENTO_REAL"].unique()))
        c4, c5 = st.columns(2)
        so_novos = c4.toggle(f"Só novidades ({dias} dias)")
        so_base = c5.toggle("Só empresas da Base Mestre")

    v = df
    if f_tipo:
        v = v[v["rotulo_tipo"].isin(f_tipo)]
    if f_mun:
        v = v[v["municipio"].str.title().isin(f_mun)]
    if f_rel:
        v = v[v["STATUS_RELACIONAMENTO_REAL"].isin(f_rel)]
    if so_novos:
        v = v[v["novo"]]
    if so_base:
        v = v[v["na_base_mestre"]]

    tabela = v.assign(
        selo=v["novo"].map({True: "🆕", False: ""}),
        tipo=v["icone"] + " " + v["rotulo_tipo"],
        relacionamento=v["STATUS_RELACIONAMENTO_REAL"].map(REL_BADGE).fillna(v["STATUS_RELACIONAMENTO_REAL"]),
    ).sort_values(["novo", "score_momento"], ascending=[False, False])

    st.dataframe(
        tabela[["selo", "tipo", "score_momento", "razao_social", "cnpj", "relacionamento",
                "descricao", "oferta_sesi", "oferta_senai", "abordagem", "data_publicacao", "municipio"]],
        width="stretch", hide_index=True,
        column_config={
            "selo": st.column_config.TextColumn(" ", width="small"),
            "tipo": "Sinal",
            "score_momento": st.column_config.ProgressColumn(
                "Momento", min_value=0, max_value=float(df["score_momento"].max() or 1), format="%.1f"),
            "razao_social": "Empresa",
            "cnpj": "CNPJ",
            "relacionamento": "Relacionamento",
            "descricao": "O que aconteceu",
            "oferta_sesi": "Ofertar SESI",
            "oferta_senai": "Ofertar SENAI",
            "abordagem": "Como abordar",
            "data_publicacao": st.column_config.DateColumn("Publicado em", format="DD/MM/YYYY"),
            "municipio": "Município",
        },
    )
    st.download_button(
        "⬇️ Baixar lista filtrada (CSV, abre no Excel)",
        tabela.drop(columns=["selo"]).to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name=f"sinais_{hoje:%Y-%m-%d}.csv", mime="text/csv",
    )


def _travado() -> bool:
    if not ARQ_TRAVA.exists():
        return False
    if time.time() - ARQ_TRAVA.stat().st_mtime > TRAVA_MAX_MIN * 60:
        ARQ_TRAVA.unlink(missing_ok=True)
        return False
    return True


def _bloco_atualizacao() -> None:
    """Botão que roda o job do CNO dentro do próprio app.

    Serve também de teste: se a Receita bloquear o servidor em nuvem, a
    falha fica registrada em 🚦 Saúde das Fontes com a mensagem do erro.
    """
    c1, c2 = st.columns([1, 3])
    if ARQ_SINAIS_CNO.exists():
        atualizado = pd.Timestamp(ARQ_SINAIS_CNO.stat().st_mtime, unit="s", tz="UTC")
        atualizado = atualizado.tz_convert("America/Maceio").strftime("%d/%m/%Y %H:%M")
        c2.caption(f"Última coleta neste servidor: **{atualizado}**. "
                   "Leva de 2 a 5 minutos (baixa ~315 MB da Receita).")
    else:
        c2.caption("Leva de 2 a 5 minutos (baixa ~315 MB da Receita e filtra Alagoas).")

    ocupado = _travado()
    if not c1.button("🔄 Atualizar sinais", type="primary", disabled=ocupado):
        if ocupado:
            c2.info("⏳ Já existe uma coleta em andamento. Recarregue a página em alguns minutos.")
        return

    from jobs.coletar_cno import executar  # import tardio: só quando clica

    ARQ_TRAVA.parent.mkdir(parents=True, exist_ok=True)
    ARQ_TRAVA.touch()
    barra = st.progress(0.0, text="Baixando o CNO da Receita ...")
    try:
        with st.status("Coletando obras novas (CNO) ...", expanded=True) as status:
            saida = executar(
                avisar=status.write,
                progresso=lambda f: barra.progress(min(f, 1.0), text=f"Baixando o CNO ... {f:.0%}"),
                manter_zip=False,
            )
            status.update(label=f"✅ {saida['cnpj_basico'].nunique()} empresas com obra nova",
                          state="complete", expanded=False)
    except Exception as erro:  # noqa: BLE001 — mostra ao usuário e registra no log
        barra.empty()
        st.error(
            f"A coleta falhou: `{erro}`\n\n"
            "Se for bloqueio da Receita ao servidor em nuvem, rode o job na sua "
            "máquina (`python jobs/coletar_cno.py`). A falha ficou registrada em 🚦 Saúde das Fontes."
        )
        return
    finally:
        ARQ_TRAVA.unlink(missing_ok=True)

    barra.empty()
    _carregar_sinais.clear()
    st.rerun()


ROTULO_STATUS = {"implementado": "✅ Implementada", "planejado": "🗓️ Planejada", "lacuna": "❓ Sem fonte aberta"}
ROTULO_MODULO = {"sinais": "Sinais", "concorrencia": "Concorrência", "enriquecimento": "Enriquecimento"}
ROTULO_GRAN = {"empresa": "Por empresa (CNPJ)", "setor": "Por setor (CNAE × município)"}


def render_saude_fontes() -> None:
    st.header("🚦 Saúde das Fontes")
    st.caption(
        "De onde vem cada dado, com que frequência deveria atualizar, e quando "
        "atualizou de fato. Existe porque as tabelas do DW pararam sem ninguém "
        "perceber — aqui, atraso aparece em vermelho."
    )
    catalogo = carregar_catalogo()
    saude = saude_das_fontes(catalogo, carregar_log())

    implementadas = int((saude["status"] == "implementado").sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Fontes no catálogo", len(saude))
    c2.metric("Implementadas", f"{implementadas} de {len(saude)}")
    c3.metric("Em dia 🟢", int((saude["semaforo"] == "🟢").sum()))
    st.progress(implementadas / max(len(saude), 1),
                text="Construção das fontes externas (substituem as tabelas paradas do DW)")

    tabela = saude.assign(
        status=saude["status"].map(ROTULO_STATUS).fillna(saude["status"]),
        modulo=saude["modulo"].map(ROTULO_MODULO).fillna(saude["modulo"]),
        granularidade=saude["granularidade"].map(ROTULO_GRAN).fillna(saude["granularidade"]),
        dias_desde_sucesso=saude["dias_desde_sucesso"].astype("Int64"),
        link=saude["link"].where(saude["link"].str.startswith("http"), None),
    )
    tabela["ordem"] = tabela["status"].map({v: i for i, v in enumerate(ROTULO_STATUS.values())})
    tabela = tabela.sort_values(["ordem", "modulo"]).drop(columns=["ordem", "fonte"])

    st.dataframe(
        tabela[["semaforo", "nome", "status", "modulo", "granularidade", "frequencia_dias",
                "ultimo_sucesso", "dias_desde_sucesso", "ultima_mensagem", "link", "tabela_dw"]],
        width="stretch", hide_index=True,
        column_config={
            "semaforo": st.column_config.TextColumn(" ", width="small"),
            "nome": "Fonte",
            "status": "Situação",
            "modulo": "Alimenta",
            "granularidade": "Identifica",
            "frequencia_dias": st.column_config.NumberColumn("Atualiza a cada (dias)"),
            "ultimo_sucesso": "Última coleta OK",
            "dias_desde_sucesso": st.column_config.NumberColumn("Dias sem atualizar"),
            "ultima_mensagem": "Última mensagem",
            "link": st.column_config.LinkColumn("Fonte oficial", display_text="abrir ↗"),
            "tabela_dw": "Substitui no DW",
        },
    )
    st.caption("🟢 em dia · 🟡 atrasada até 3× a frequência · 🔴 atrasada ou última execução falhou · "
               "⚪ não implementada ou ainda não rodou neste servidor")

    with st.expander("Detalhes de cada fonte (links, chave de junção, observações)"):
        for fonte_id, cfg in catalogo.items():
            st.markdown(f"**{cfg.get('nome', fonte_id)}**  ·  {ROTULO_STATUS.get(cfg.get('status'), '')}")
            linhas = [f"- Junção com a Base Mestre: {cfg.get('chave', '—')}"]
            for chave, rotulo in [("url_pagina", "Página"), ("url_download", "Download"),
                                  ("url_api", "API"), ("url_layout", "Layout")]:
                valor = str(cfg.get(chave) or "")
                if valor:
                    linhas.append(f"- {rotulo}: {valor}" if valor.startswith("http")
                                  else f"- {rotulo}: _{valor.lower()}_")
            if cfg.get("observacao"):
                linhas.append(f"- Observação: {' '.join(str(cfg['observacao']).split())}")
            st.markdown("\n".join(linhas))
