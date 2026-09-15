import pandas as pd
import streamlit as st

from src.pipeline import CommercialPipeline
from src.tools.company_data import BASE_PATH
from src.presentation import (
    ORIGEM_LABEL,
    classificar_aderencia,
    descrever_check,
    traduzir_alerta,
    traduzir_evidencia,
)


st.set_page_config(
    page_title="AI Commercial Intelligence — Piloto",
    layout="wide",
)


@st.cache_resource
def carregar_pipeline() -> CommercialPipeline:
    return CommercialPipeline()


@st.cache_data
def carregar_empresas() -> pd.DataFrame:
    df = pd.read_csv(
        BASE_PATH,
        dtype=str,
        low_memory=False,
        usecols=["cnpj", "razao_social", "SETOR", "Municipio", "Porte"],
    )

    df["cnpj"] = (
        df["cnpj"].str.replace(r"\D", "", regex=True).str.zfill(14)
    )

    return df


pipeline = carregar_pipeline()
empresas = carregar_empresas()


st.title("AI Commercial Intelligence")
st.caption(
    "Piloto: busca de lead → afinidade setorial → produtos reais do "
    "catálogo SESI/SENAI."
)

mostrar_filtros = st.toggle(
    "Ver critérios de filtro e opções descartadas pelo sistema",
    value=False,
    help=(
        "As oportunidades recomendadas abaixo já passam por um filtro "
        "automático de qualidade antes de chegar até você. Ative esta "
        "opção para ver o que foi descartado e por quê — a decisão "
        "final sobre o que faz sentido oferecer ao cliente é sempre "
        "da equipe comercial, não do sistema."
    ),
)

busca = st.text_input(
    "Buscar empresa por razão social",
    placeholder="Ex: Padaria, Frigorífico, Construtora...",
)

cnpj_selecionado = None

if busca.strip():
    filtradas = empresas[
        empresas["razao_social"].str.contains(
            busca.strip(), case=False, na=False
        )
    ].head(50)

    if filtradas.empty:
        st.info("Nenhuma empresa encontrada com esse termo.")
    else:
        opcoes = {
            f"{linha.razao_social} — {linha.Municipio or 'município N/D'} "
            f"(CNPJ {linha.cnpj})": linha.cnpj
            for linha in filtradas.itertuples()
        }

        escolha = st.selectbox("Selecione a empresa", list(opcoes.keys()))
        cnpj_selecionado = opcoes[escolha]

with st.expander("Ou informar o CNPJ diretamente"):
    cnpj_manual = st.text_input("CNPJ", placeholder="00000000000000")
    if cnpj_manual.strip():
        cnpj_selecionado = cnpj_manual.strip()

if not cnpj_selecionado:
    st.stop()

lead = pipeline.research.pesquisar(cnpj_selecionado)

if lead is None:
    st.error("Empresa não encontrada na base.")
    st.stop()

qualidade = pipeline.data_quality.avaliar(lead)
qualificacao = pipeline.sdr.qualificar(lead)
auditoria = pipeline.opportunity.identificar_com_auditoria(lead)

oportunidades = auditoria["aprovadas"]
rejeitadas = auditoria["rejeitadas"]

st.divider()

col_lead, col_qualidade, col_sdr = st.columns(3)

with col_lead:
    st.subheader(lead.razao_social or "Empresa")
    st.write(f"**CNPJ:** {lead.cnpj}")
    st.write(f"**Município:** {lead.municipio or '—'}")
    st.write(f"**Setor:** {lead.setor or '—'}")
    st.write(f"**Porte:** {lead.porte or '—'}")
    st.write(f"**Relacionamento:** {lead.status_relacionamento or '—'}")
    st.write(
        f"**Já é cliente:** "
        f"SESI: {'Sim' if lead.tem_sesi else 'Não'} · "
        f"SENAI: {'Sim' if lead.tem_senai else 'Não'}"
    )

with col_qualidade:
    st.subheader("Qualidade dos dados")
    st.metric("Score", qualidade["score"])
    st.write(f"**Confiança:** {qualidade['confianca']}")
    st.write(
        f"**Apto para decisão:** "
        f"{'Sim' if qualidade['apto_para_decisao'] else 'Não'}"
    )
    if qualidade["alertas"]:
        for alerta in qualidade["alertas"]:
            st.warning(alerta)

with col_sdr:
    st.subheader("Qualificação SDR")
    st.metric("Score", qualificacao["score"])
    st.write(f"**Prioridade:** {qualificacao['prioridade']}")

st.divider()
st.subheader(f"Oportunidades recomendadas ({len(oportunidades)})")

total_avaliado = len(oportunidades) + len(rejeitadas)

if total_avaliado == 0:
    st.info(
        "Nenhum produto do catálogo foi encontrado para o perfil "
        "desta empresa (sem área de afinidade mapeada para o setor "
        "identificado)."
    )
elif not oportunidades:
    st.warning(
        f"O sistema avaliou {total_avaliado} produto(s) do catálogo "
        "para este perfil, mas nenhum passou no filtro automático de "
        "qualidade. Ative \"Ver critérios de filtro\" acima para "
        "revisar as opções descartadas — pode haver algo aproveitável "
        "que o filtro foi conservador demais para deixar passar."
    )
else:
    st.caption(
        f"De {total_avaliado} produto(s) do catálogo avaliados para "
        f"este perfil, {len(oportunidades)} passaram no filtro "
        f"automático de qualidade e aparecem como sugestão abaixo"
        + (
            f" — {len(rejeitadas)} foram descartados "
            "(ative \"Ver critérios de filtro\" acima para conferir)."
            if rejeitadas
            else "."
        )
        + " Estas são sugestões pré-filtradas: a decisão final sobre "
        "abordar ou não o cliente é sempre da equipe comercial."
    )

for oportunidade in oportunidades:
    titulo = (
        f"{oportunidade.solucao}  ·  {oportunidade.area}  ·  "
        f"Aderência {classificar_aderencia(oportunidade.score_fit)}"
    )

    with st.expander(titulo):
        st.write(f"**Por que recomendamos:** {oportunidade.motivo}")

        st.write(
            f"**Tipo de oportunidade:** "
            f"{ORIGEM_LABEL.get(oportunidade.origem, oportunidade.origem)}"
        )

        st.write("**O que sustenta essa recomendação:**")
        for evidencia in oportunidade.evidencias:
            traduzida = traduzir_evidencia(evidencia)
            if traduzida:
                st.markdown(f"- {traduzida}")

        st.write(
            f"**Produto no catálogo:** {oportunidade.solucao} "
            f"(código {oportunidade.produto_codigo})"
        )
        st.caption(oportunidade.caminho_catalogo)

        if mostrar_filtros:
            st.markdown("---")
            st.markdown("**🔧 Detalhes técnicos**")
            st.write(f"score_fit: {oportunidade.score_fit}")
            st.write(f"confidence (heurística, não calibrada): {oportunidade.confidence}")
            st.write(f"prioridade: {oportunidade.prioridade}")
            st.write(f"fonte: {oportunidade.fonte}")
            st.write(f"tipo_evidencia: {oportunidade.tipo_evidencia}")
            st.write("evidências brutas:")
            for evidencia in oportunidade.evidencias:
                st.code(evidencia, language=None)

if mostrar_filtros:
    st.divider()
    st.subheader(f"Opções descartadas pelo filtro automático ({len(rejeitadas)})")
    st.caption(
        "O sistema encontrou esses produtos no catálogo, mas o filtro "
        "de qualidade não considerou a conexão forte o suficiente para "
        "sugeri-los automaticamente. Isso não significa que estejam "
        "descartados de vez — revise se algum faz sentido para o "
        "contexto que você conhece do cliente."
    )

    if not rejeitadas:
        st.info("Nenhuma opção foi descartada para este lead.")

    for avaliacao in rejeitadas:
        titulo = f"{avaliacao['produto']}  ·  {avaliacao['entidade']}"

        with st.expander(titulo):
            st.write(f"**Área relacionada:** {avaliacao['area_origem']}")

            st.write("**Por que não foi sugerido:**")
            for alerta in avaliacao["alertas"]:
                st.markdown(f"- {traduzir_alerta(alerta)}")

            st.markdown("---")
            st.markdown("**🔧 Detalhes técnicos**")
            st.write(f"score_fit: {avaliacao['score_fit']}")
            st.write(f"origem: {avaliacao['origem']}")

            st.write("Checks avaliados:")
            for nome_check, passou in avaliacao["checks"].items():
                icone = "✅" if passou else "❌"
                st.write(f"{icone} {descrever_check(nome_check)}")

            st.write("Alertas técnicos (originais):")
            for alerta in avaliacao["alertas"]:
                st.code(alerta, language=None)
