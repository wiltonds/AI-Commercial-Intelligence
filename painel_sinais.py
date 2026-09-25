"""
Páginas "⚡ Sinais & Momento" e "🚦 Saúde das Fontes".

Sinais respondem "QUANDO abordar": a Base Mestre já diz quem tem
aderência ao portfólio; aqui entra quem está em movimento agora. Cada
fonte vira um CSV em data/processed/SINAIS_<FONTE>.csv, gerado por um
job em jobs/. Hoje: CNO (obra nova).
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import streamlit as st

from src.sinais.fontes import carregar_catalogo, carregar_log, saude_das_fontes

RAIZ = Path(__file__).resolve().parent
ARQ_SINAIS_CNO = RAIZ / "data" / "processed" / "SINAIS_CNO.csv"
ARQ_TRAVA = RAIZ / "data" / "processed" / ".coletando_cno.lock"
TRAVA_MAX_MIN = 30  # trava mais velha que isso é resto de execução interrompida


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

    _bloco_atualizacao()

    if not ARQ_SINAIS_CNO.exists():
        st.warning(
            "Ainda não há sinais coletados neste servidor. Clique em "
            "**🔄 Atualizar sinais** acima, ou rode na sua máquina:\n\n"
            "```\npython jobs/coletar_cno.py\n```"
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
    _carregar_sinais_cno.clear()
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
