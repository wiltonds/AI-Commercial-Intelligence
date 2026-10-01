# ============================================================
# INTELIGÊNCIA COMERCIAL + IA — V3
# SESI + SENAI + SEBRAE | Dashboard + Recomendação por IA
#
# V1 (Inteligência Comercial): ETL + dashboard de mercado.
# V2 (AI Commercial Intelligence): pipeline de recomendação por lead.
# V3 (este arquivo): as duas coisas juntas, em um único app — a
# página de diagnóstico por empresa deixou de usar o antigo
# motor_aderencia.py (áreas genéricas, sem produto real) e passou a
# usar o pipeline completo (CNAE → afinidade → catálogo real →
# Supervisor) que construímos em V2.
# ============================================================

import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from src.pipeline import CommercialPipeline
from src.tools.company_data import BASE_PATH
from src.tools.cnpj_raiz import consolidar_por_cnpj_raiz, resumir_consolidacao
from src.agents.sdr_llm import SDRLLMAgent
from painel_empresas_raiz import render_visao_raiz
from painel_arquitetura import render_arquitetura

from src.presentation import (
    ORIGEM_LABEL,
    classificar_aderencia,
    descrever_check,
    traduzir_alerta,
    traduzir_evidencia,
)


st.set_page_config(
    page_title="Inteligência Comercial + IA | SESI + SENAI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).resolve().parent
ARQUIVO_MESTRE = BASE_PATH
ARQUIVO_AUDITORIA_RECEITA = (
    BASE_DIR / "data" / "processed" / "AUDITORIA_RECEITA_GAP_INDUSTRIA.csv"
)
ARQUIVO_CORRECAO_UNIVERSO = (
    BASE_DIR / "data" / "raw" / "CORRECAO_UNIVERSO_CONFIRMADA.csv"
)


# ============================================================
# ESTILO CSS
# ============================================================

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    .kpi {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 16px;
        background: #ffffff;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        min-height: 110px;
    }
    .kpi-title { font-size: 13px; color: #666666; margin-bottom: 6px; font-weight: 600; }
    .kpi-value { font-size: 26px; font-weight: 700; color: #111111; }
    .kpi-sub { font-size: 12px; color: #888888; margin-top: 4px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# FUNÇÕES DE TRATAMENTO DE DADOS
# ============================================================

def normalizar_cnpj(valor):
    if pd.isna(valor):
        return ""
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    texto = "".join(c for c in texto if c.isdigit())
    return texto.zfill(14) if texto else ""


def converter_para_booleano(df, col_tem):
    if col_tem not in df.columns:
        return pd.Series(False, index=df.index)

    val = df[col_tem].fillna("").astype(str).str.strip().str.upper()
    return val.isin(["TRUE", "1", "SIM", "S", "VERDADEIRO", "T", "YES"])


def numero(valor):
    try:
        return f"{int(valor):,}".replace(",", ".")
    except Exception:
        return "0"


def percentual(valor):
    try:
        return f"{float(valor):.2f}%".replace(".", ",")
    except Exception:
        return "0,00%"


def kpi(titulo, valor, subtitulo=""):
    st.markdown(
        f"""
        <div class="kpi">
            <div class="kpi-title">{titulo}</div>
            <div class="kpi-value">{valor}</div>
            <div class="kpi-sub">{subtitulo}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# CARREGAMENTO DOS DADOS (VISÃO DE MERCADO)
# ============================================================

@st.cache_data
def carregar_base() -> pd.DataFrame:
    if not ARQUIVO_MESTRE.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {ARQUIVO_MESTRE}")

    try:
        df = pd.read_csv(
            ARQUIVO_MESTRE, encoding="utf-8-sig", low_memory=False, dtype=str
        )
    except UnicodeDecodeError:
        df = pd.read_csv(
            ARQUIVO_MESTRE, encoding="latin1", low_memory=False, dtype=str
        )

    if "cnpj" in df.columns:
        df["cnpj"] = df["cnpj"].apply(normalizar_cnpj)

    df["POSSUI_SESI"] = converter_para_booleano(df, "TEM_SESI")
    df["POSSUI_SENAI"] = converter_para_booleano(df, "TEM_SENAI")
    df["POSSUI_SESI_SENAI"] = df["POSSUI_SESI"] & df["POSSUI_SENAI"]

    colunas_sebrae = [c for c in df.columns if c.startswith("SEBRAE_")]
    if colunas_sebrae:
        df["POSSUI_SEBRAE"] = df[colunas_sebrae].notna().any(axis=1) & (
            df[colunas_sebrae]
            .apply(lambda s: s.astype(str).str.strip().str.upper())
            .ne("")
            .any(axis=1)
        )
    else:
        df["POSSUI_SEBRAE"] = False

    df["STATUS_RELACIONAMENTO_REAL"] = "Sem relacionamento"
    df.loc[
        df["POSSUI_SESI"] & ~df["POSSUI_SENAI"], "STATUS_RELACIONAMENTO_REAL"
    ] = "Somente SESI"
    df.loc[
        ~df["POSSUI_SESI"] & df["POSSUI_SENAI"], "STATUS_RELACIONAMENTO_REAL"
    ] = "Somente SENAI"
    df.loc[df["POSSUI_SESI_SENAI"], "STATUS_RELACIONAMENTO_REAL"] = (
        "SESI + SENAI"
    )

    if "STATUS_SEBRAE" in df.columns:
        df["STATUS_SEBRAE"] = df["STATUS_SEBRAE"].fillna(
            "SEM INFORMAÇÃO"
        ).replace("", "SEM INFORMAÇÃO")
    else:
        df["STATUS_SEBRAE"] = "SEM INFORMAÇÃO"

    if "Municipio" in df.columns:
        df["Municipio"] = df["Municipio"].fillna("NÃO INFORMADO")
    if "Porte" in df.columns:
        df["Porte"] = df["Porte"].fillna("NÃO INFORMADO")
    if "razao_social" in df.columns:
        df["razao_social"] = df["razao_social"].fillna("SEM RAZÃO SOCIAL")
    if "CNAE PRIMARIO" in df.columns:
        df["CNAE PRIMARIO"] = df["CNAE PRIMARIO"].fillna("NÃO INFORMADO")

    return df


@st.cache_data
def carregar_auditoria_cobertura():
    if not ARQUIVO_AUDITORIA_RECEITA.exists():
        return None

    auditoria = pd.read_csv(ARQUIVO_AUDITORIA_RECEITA, encoding="utf-8-sig")

    auditoria["divisao_cnae"] = (
        pd.to_numeric(auditoria["cnae_fiscal_codigo"], errors="coerce")
        .fillna(0)
        .astype(int)
        .astype(str)
        .str.zfill(7)
        .str[:2]
        .astype(int)
    )
    auditoria["e_industria_hoje"] = auditoria["divisao_cnae"].between(10, 33)

    def classificar(linha):
        if linha["situacao_cadastral"] != "ATIVA":
            return "Baixada / inapta / suspensa"
        if linha["uf_receita"] != "AL":
            return "Ativa, mas fora de Alagoas"
        if not linha["e_industria_hoje"]:
            return "Ativa em AL, mudou de atividade"
        return "Confirmada e incluída no universo"

    auditoria["MOTIVO"] = auditoria.apply(classificar, axis=1)

    correcao = None
    if ARQUIVO_CORRECAO_UNIVERSO.exists():
        correcao = pd.read_csv(ARQUIVO_CORRECAO_UNIVERSO, encoding="utf-8-sig")

    return auditoria, correcao


@st.cache_resource
def carregar_pipeline() -> CommercialPipeline:
    return CommercialPipeline()


@st.cache_data
def consolidar_empresas(df: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por CNPJ raiz — matriz e filiais deixam de contar em dobro."""
    return consolidar_por_cnpj_raiz(df)


try:
    df = carregar_base()
except Exception as erro:
    st.error("❌ Erro ao carregar o arquivo CSV Mestre.")
    st.code(str(erro))
    st.stop()

df_empresas = consolidar_empresas(df)
resumo_consolidacao = resumir_consolidacao(df, df_empresas)

pipeline = carregar_pipeline()


# ============================================================
# BARRA LATERAL — FILTROS & NAVEGAÇÃO
# ============================================================

st.sidebar.title("Navegação")
# Páginas do time comercial x páginas técnicas (auditoria, arquitetura, visões
# antigas). As técnicas continuam no código e testadas: só ficam atrás do
# "Modo técnico" para o menu do consultor ficar enxuto.
PAGINAS_COMERCIAIS = [
    "📊 Visão Geral",
    "📈 Share & Relacionamento",
    "🏛️ SESI | SENAI",
    "🔗 Canais e Conexões",
    "🔎 Explorador de Empresas",
    "🎯 Base Qualificada (CRM)",
]
PAGINAS_TECNICAS = [
    "🗓️ Rotina de Dados",
    "🏢 Empresas (CNPJ raiz)",
    "🏭 Mercado",
    "🔵 Visão SESI",
    "🟠 Visão SENAI",
    "🟢 Visão SEBRAE",
    "🔥 Visão Integrada",
    "🎯 Diagnóstico & Recomendação IA",
    "✅ Auditoria de Cobertura",
    "🏗️ Arquitetura & Fluxo",
]
modo_tecnico = st.sidebar.toggle(
    "Modo técnico",
    value=False,
    help="Mostra também as páginas de auditoria, arquitetura e as visões detalhadas por entidade.",
)
pagina = st.sidebar.radio(
    "Visões Disponíveis",
    PAGINAS_COMERCIAIS + (PAGINAS_TECNICAS if modo_tecnico else []),
)

st.sidebar.divider()
if modo_tecnico:
    st.sidebar.subheader("Visão")
    visao_estabelecimento = st.sidebar.toggle(
        "Ver por estabelecimento (matriz + filiais)",
        value=False,
        help=(
            "Por padrão, cada empresa conta uma única vez pelo CNPJ raiz "
            "(matriz e filiais consolidadas). Ative esta opção para ver "
            "cada estabelecimento separadamente — útil para auditoria, "
            "mas não reflete o tamanho real do mercado (uma empresa com "
            "5 filiais apareceria como 6 empresas)."
        ),
    )
else:
    visao_estabelecimento = False
base_ativa = df if visao_estabelecimento else df_empresas

st.sidebar.divider()
st.sidebar.subheader("Filtros Globais")

municipios = sorted(
    [m for m in base_ativa["Municipio"].unique() if m and m != "NÃO INFORMADO"]
)
municipio_filtro = st.sidebar.multiselect("Município", municipios)

portes = sorted(
    [p for p in base_ativa["Porte"].unique() if p and p != "NÃO INFORMADO"]
)
porte_filtro = st.sidebar.multiselect("Porte", portes)

df_view = base_ativa.copy()
if municipio_filtro:
    df_view = df_view[df_view["Municipio"].isin(municipio_filtro)]
if porte_filtro:
    df_view = df_view[df_view["Porte"].isin(porte_filtro)]

# Independente do toggle acima, a página "Empresas (CNPJ raiz)" sempre
# consolida por conta própria — precisa da base por estabelecimento.
df_estabelecimentos_view = df.copy()
if municipio_filtro:
    df_estabelecimentos_view = df_estabelecimentos_view[
        df_estabelecimentos_view["Municipio"].isin(municipio_filtro)
    ]
if porte_filtro:
    df_estabelecimentos_view = df_estabelecimentos_view[
        df_estabelecimentos_view["Porte"].isin(porte_filtro)
    ]

subtitulo_universo = "estabelecimentos" if visao_estabelecimento else "empresas (CNPJ raiz)"
mercado = len(df_view)
sesi = int(df_view["POSSUI_SESI"].sum())
senai = int(df_view["POSSUI_SENAI"].sum())
sebrae = int(df_view["POSSUI_SEBRAE"].sum())
ambos_sesi_senai = int(df_view["POSSUI_SESI_SENAI"].sum())
clientes_totais = int((df_view["POSSUI_SESI"] | df_view["POSSUI_SENAI"]).sum())
prospects = mercado - clientes_totais


# ============================================================
# CONTEÚDO PRINCIPAL
# ============================================================

st.title("📊 Inteligência Comercial + IA — SESI | SENAI")
st.caption(
    "Ecossistema de Negócios e Diagnóstico do Mercado Industrial de "
    "Alagoas — com recomendação de produto real por IA."
)
st.caption(
    f"🏢 {numero(resumo_consolidacao['total_empresas'])} empresas (CNPJ raiz) "
    f"a partir de {numero(resumo_consolidacao['total_estabelecimentos'])} "
    f"estabelecimentos cadastrados — "
    f"{numero(resumo_consolidacao['empresas_com_filial'])} empresas têm mais "
    f"de uma unidade ({numero(resumo_consolidacao['total_filiais'])} filiais "
    "consolidadas para não inflar a contagem). "
    + (
        "Exibindo por estabelecimento (matriz + filiais separados)."
        if visao_estabelecimento
        else "Exibindo por empresa — uma linha por CNPJ raiz."
    )
)
st.divider()

# ------------------------------------------------------------
# 1. VISÃO GERAL
# ------------------------------------------------------------
if pagina == "📊 Visão Geral":
    st.header("Visão Geral do Mercado")

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        kpi("Mercado Total", numero(mercado), subtitulo_universo)
    with c2:
        kpi(
            "Clientes SESI",
            numero(sesi),
            percentual(sesi / mercado * 100) if mercado else "0%",
        )
    with c3:
        kpi(
            "Clientes SENAI",
            numero(senai),
            percentual(senai / mercado * 100) if mercado else "0%",
        )
    with c4:
        kpi(
            "SESI + SENAI",
            numero(ambos_sesi_senai),
            percentual(ambos_sesi_senai / mercado * 100) if mercado else "0%",
        )
    with c5:
        kpi(
            "Sem Relacionamento",
            numero(prospects),
            percentual(prospects / mercado * 100) if mercado else "0%",
        )

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Distribuição do Relacionamento Institucional")
        cobertura = pd.DataFrame(
            {
                "Status": [
                    "Somente SESI",
                    "Somente SENAI",
                    "SESI + SENAI",
                    "Sem Relacionamento",
                ],
                "Quantidade": [
                    int((df_view["POSSUI_SESI"] & ~df_view["POSSUI_SENAI"]).sum()),
                    int((df_view["POSSUI_SENAI"] & ~df_view["POSSUI_SESI"]).sum()),
                    ambos_sesi_senai,
                    prospects,
                ],
            }
        )
        st.bar_chart(cobertura.set_index("Status"))

    with col2:
        st.subheader("Distribuição por Porte")
        st.bar_chart(df_view["Porte"].value_counts())


# ------------------------------------------------------------
# 1A. VISÃO EMPRESARIAL — CNPJ RAIZ
# ------------------------------------------------------------
elif pagina == "🏢 Empresas (CNPJ raiz)":
    render_visao_raiz(df_estabelecimentos_view)


# ------------------------------------------------------------
# 1B. MERCADO
# ------------------------------------------------------------
elif pagina == "🏭 Mercado":
    st.header("🏭 Mercado Industrial")
    st.write("Universo de empresas utilizado como base-mãe para as análises comerciais.")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi("Empresas", numero(len(df_view)), subtitulo_universo)
    with c2:
        kpi("Municípios", numero(df_view["Municipio"].nunique()))
    with c3:
        kpi(
            "CNAEs",
            numero(df_view["CNAE PRIMARIO"].nunique())
            if "CNAE PRIMARIO" in df_view.columns
            else "0",
        )
    with c4:
        kpi("Relacionadas", numero(clientes_totais))

    if not visao_estabelecimento:
        st.caption(
            f"{numero(resumo_consolidacao['empresas_com_filial'])} dessas empresas "
            f"têm mais de um estabelecimento (matriz + filiais). Ative \"Ver por "
            "estabelecimento\" na barra lateral para auditar unidade por unidade."
        )

    st.divider()
    st.subheader("Distribuição por município")
    st.bar_chart(df_view["Municipio"].value_counts().head(30))

    if "CNAE PRIMARIO" in df_view.columns:
        st.subheader("Principais atividades econômicas")
        cnae = (
            df_view["CNAE PRIMARIO"]
            .value_counts()
            .head(30)
            .rename_axis("CNAE")
            .to_frame("Empresas")
        )
        st.dataframe(cnae, use_container_width=True)


# ------------------------------------------------------------
# 2. VISÃO SESI
# ------------------------------------------------------------
elif pagina == "🔗 Canais e Conexões":
    from src.paginas.canais import render as render_canais
    render_canais()


elif pagina == "🏛️ SESI | SENAI":
    from src.paginas.casas import render as render_casas
    render_casas(df_view)


elif pagina == "🗓️ Rotina de Dados":
    from src.paginas.rotina_dados import render as render_rotina
    render_rotina()


elif pagina == "📈 Share & Relacionamento":
    from src.paginas.share_relacionamento import render as render_share
    render_share(df_view, df_estabelecimentos_view)


elif pagina == "🔵 Visão SESI":
    st.header("🔵 Visão Estratégica SESI")
    sem_sesi = mercado - sesi

    c1, c2, c3 = st.columns(3)
    with c1:
        kpi("Clientes SESI", numero(sesi), "empresas ativas")
    with c2:
        kpi("Taxa de Penetração", percentual(sesi / mercado * 100) if mercado else "0%")
    with c3:
        kpi("Oportunidades (Sem SESI)", numero(sem_sesi), "empresas a prospectar")

    st.divider()
    st.subheader("Base de Empresas sem SESI")
    cols = [
        c
        for c in ["cnpj", "razao_social", "Municipio", "Porte", "CNAE PRIMARIO"]
        if c in df_view.columns
    ]
    st.dataframe(
        df_view[~df_view["POSSUI_SESI"]][cols].head(1000),
        use_container_width=True,
        hide_index=True,
    )


# ------------------------------------------------------------
# 3. VISÃO SENAI
# ------------------------------------------------------------
elif pagina == "🟠 Visão SENAI":
    st.header("🟠 Visão Estratégica SENAI")
    sem_senai = mercado - senai

    c1, c2, c3 = st.columns(3)
    with c1:
        kpi("Clientes SENAI", numero(senai), "empresas ativas")
    with c2:
        kpi("Taxa de Penetração", percentual(senai / mercado * 100) if mercado else "0%")
    with c3:
        kpi("Oportunidades (Sem SENAI)", numero(sem_senai), "empresas a prospectar")

    st.divider()
    st.subheader("Base de Empresas sem SENAI")
    cols = [
        c
        for c in ["cnpj", "razao_social", "Municipio", "Porte", "CNAE PRIMARIO"]
        if c in df_view.columns
    ]
    st.dataframe(
        df_view[~df_view["POSSUI_SENAI"]][cols].head(1000),
        use_container_width=True,
        hide_index=True,
    )


# ------------------------------------------------------------
# 4. VISÃO SEBRAE
# ------------------------------------------------------------
elif pagina == "🟢 Visão SEBRAE":
    st.header("🟢 Visão Estratégica SEBRAE")
    st.caption("Inteligência de mercado do SEBRAE dentro do universo industrial de Alagoas.")

    distribuicao = df_view["STATUS_SEBRAE"].value_counts()
    nao_atendida = int(distribuicao.get("NÃO ATENDIDA", 0))
    fora_escopo = int(distribuicao.get("FORA DO ESCOPO SEBRAE", 0))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi("Mercado", numero(mercado), "empresas")
    with c2:
        kpi("Não atendidas", numero(nao_atendida), "oportunidade SEBRAE")
    with c3:
        kpi("Fora do escopo", numero(fora_escopo), "não elegíveis")
    with c4:
        kpi(
            "% não atendidas",
            percentual(nao_atendida / mercado * 100) if mercado else "0%",
            "do mercado",
        )

    st.divider()
    st.subheader("Situação SEBRAE")
    st.bar_chart(distribuicao)

    st.divider()
    st.subheader("Empresas classificadas como NÃO ATENDIDA")
    df_oportunidade = df_view[df_view["STATUS_SEBRAE"] == "NÃO ATENDIDA"]
    cols = [
        c
        for c in [
            "cnpj",
            "razao_social",
            "Municipio",
            "Porte",
            "CNAE PRIMARIO",
            "POSSUI_SESI",
            "POSSUI_SENAI",
        ]
        if c in df_oportunidade.columns
    ]
    st.dataframe(
        df_oportunidade[cols].head(3000), use_container_width=True, hide_index=True
    )


# ------------------------------------------------------------
# 4B. VISÃO INTEGRADA
# ------------------------------------------------------------
elif pagina == "🔥 Visão Integrada":
    st.header("🔥 Visão Integrada")
    st.caption("Uma mesma empresa observada pelas três perspectivas: SESI, SENAI e SEBRAE.")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi("SESI", numero(sesi))
    with c2:
        kpi("SENAI", numero(senai))
    with c3:
        kpi("SESI + SENAI", numero(ambos_sesi_senai))
    with c4:
        kpi("Sem SESI/SENAI", numero(prospects))

    st.divider()
    st.subheader("Cobertura SESI/SENAI")
    st.bar_chart(df_view["STATUS_RELACIONAMENTO_REAL"].value_counts())

    st.divider()
    st.subheader("SESI/SENAI × SEBRAE")
    cruzamento = pd.crosstab(df_view["STATUS_RELACIONAMENTO_REAL"], df_view["STATUS_SEBRAE"])
    st.dataframe(cruzamento, use_container_width=True)

    st.divider()
    st.subheader("Sem SESI/SENAI e não atendidas pelo SEBRAE")
    oportunidade_integrada = df_view[
        (df_view["STATUS_RELACIONAMENTO_REAL"] == "Sem relacionamento")
        & (df_view["STATUS_SEBRAE"] == "NÃO ATENDIDA")
    ]
    st.metric("Empresas nesse grupo", numero(len(oportunidade_integrada)))
    cols = [
        c
        for c in ["cnpj", "razao_social", "Municipio", "Porte", "CNAE PRIMARIO", "STATUS_SEBRAE"]
        if c in oportunidade_integrada.columns
    ]
    st.dataframe(
        oportunidade_integrada[cols].head(3000), use_container_width=True, hide_index=True
    )
    st.caption(
        "Importante: este grupo representa uma lacuna de cobertura institucional. "
        "Não significa, por si só, propensão de compra."
    )


# ------------------------------------------------------------
# 5. CROSS-SELL
# ------------------------------------------------------------
elif pagina == "🔎 Explorador de Empresas":
    st.header("🔎 Explorador de Empresas")
    st.caption(f"{numero(len(df_view))} {subtitulo_universo} no contexto atual.")

    # ---- universo: indústrias (Base Mestre) e/ou não indústrias (Base Ampliada da Receita)
    from src.tools.universo_ampliado import anotar_industrias, carregar_ampliada, opcoes_faixa, porte_fiea

    @st.cache_data(show_spinner=False)
    def _ampliada():
        return carregar_ampliada()

    @st.cache_data(show_spinner=False)
    def _porte_fiea():
        return porte_fiea()

    nao_ind = _ampliada()
    u1, u2 = st.columns([1, 2])
    universo_exp = u1.radio("Universo", ["Indústrias", "Não indústrias", "Todas"], horizontal=True,
                            disabled=nao_ind.empty,
                            help="Indústria = CNAE principal na Tabela DN da CNI. Não indústrias = médias e "
                                 "grandes de AL com CNAE fora dela (Receita).")
    if nao_ind.empty:
        u1.caption("Base de não indústrias ainda não carregada (jobs/carregar_base_ampliada.py).")
    industrias = anotar_industrias(df_view, _porte_fiea())
    lacunas = nao_ind[nao_ind["Tipo"] == "Indústria fora da Base Mestre"] if not nao_ind.empty else nao_ind
    if universo_exp == "Indústrias" or nao_ind.empty:
        resultado = pd.concat([industrias, lacunas], ignore_index=True) if not lacunas.empty else industrias
        if not lacunas.empty:
            st.caption(f"Inclui {numero(len(lacunas))} empresas com CNAE da Tabela DN (CNI) que ainda "
                       "não estão na Base Mestre — Tipo \"Indústria fora da Base Mestre\".")
    elif universo_exp == "Não indústrias":
        resultado = nao_ind[nao_ind["Tipo"] == "Não indústria"].copy()
        st.caption("Os filtros da barra lateral valem só para as indústrias.")
    else:
        resultado = pd.concat([industrias, nao_ind], ignore_index=True)
    busca = st.text_input(
        "Pesquisar por CNPJ ou razão social",
        placeholder="Digite parte do CNPJ ou nome da empresa",
    )

    if busca:
        busca = busca.strip()
        mascara = pd.Series(False, index=resultado.index)
        if "cnpj" in resultado.columns:
            mascara |= resultado["cnpj"].astype(str).str.contains(busca, case=False, na=False, regex=False)
        if "razao_social" in resultado.columns:
            mascara |= resultado["razao_social"].astype(str).str.contains(busca, case=False, na=False, regex=False)
        resultado = resultado[mascara]

    # ---- contatos (data/contatos/CONTATOS_EMPRESAS.csv, preenchido por jobs/enriquecer_contatos.py)
    from src.tools.contatos import carregar_contatos, juntar_contatos
    contatos = carregar_contatos()
    resultado = resultado.assign(cnpj_basico=resultado["cnpj"].astype(str).str[:8])
    resultado = juntar_contatos(resultado, contatos)
    for c in ("telefone_1", "email", "decisor", "confianca"):
        resultado[c] = resultado[c].fillna("")
    fc1, fc2 = st.columns([1, 2])
    so_contato = fc1.toggle("Só empresas com contato")
    conf = fc2.multiselect("Confiança do contato", ["alta", "media", "baixa"])
    if so_contato:
        resultado = resultado[resultado["confianca"].isin(["alta", "media"])]
    if conf:
        resultado = resultado[resultado["confianca"].isin(conf)]

    m1, m2 = st.columns(2)
    m1.metric("Empresas encontradas", numero(len(resultado)))
    m2.metric("Com contato utilizável", numero(int(resultado["confianca"].isin(["alta", "media"]).sum())),
              help="Confiança alta = decisor + contato que não é de contador; média = contato sem decisor.")
    if contatos.empty:
        st.info("Nenhum contato carregado ainda. Rode `python jobs/enriquecer_contatos.py` "
                "para preencher a base (as empresas com sinal vêm primeiro).")

    tabela = resultado.copy()
    tabela["Possui SESI"] = tabela["POSSUI_SESI"].map({True: "SIM", False: "NÃO"})
    tabela["Possui SENAI"] = tabela["POSSUI_SENAI"].map({True: "SIM", False: "NÃO"})
    tabela["Possui SESI + SENAI"] = tabela["POSSUI_SESI_SENAI"].map({True: "SIM", False: "NÃO"})
    tabela["Status Relacionamento"] = tabela["STATUS_RELACIONAMENTO_REAL"]
    tabela["Status SEBRAE"] = tabela["STATUS_SEBRAE"]
    if "QTD_ESTABELECIMENTOS" in tabela.columns:
        tabela["Estabelecimentos"] = tabela["QTD_ESTABELECIMENTOS"]

    from src.paginas.visao360 import carregar_360
    _v360 = carregar_360()
    if not _v360.empty:
        _raiz360 = tabela["cnpj"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(14).str[:8]
        _i = _v360.set_index("cnpj_basico")
        tabela["Linhas ativas"] = _raiz360.map(_i["linhas_ativas"]).fillna("")
        tabela["Para prospectar"] = _raiz360.map(_i["oportunidades_360"]).fillna("")
        tabela["Para reativar"] = _raiz360.map(_i["retomar_360"]).fillna("")
    tabela["Situação cliente"] = tabela.get("SITUACAO_CLIENTE", pd.Series("", index=tabela.index)).fillna("")
    tabela["Última compra"] = tabela.get("ULTIMA_COMPRA", pd.Series("", index=tabela.index)).fillna("")
    _priv = Path(__file__).resolve().parent / "data" / "privado" / "RELACIONAMENTO_POR_EMPRESA.csv"
    if _priv.exists():   # confidencial: só aparece onde o arquivo existir (fora do Git)
        _r = pd.read_csv(_priv, dtype=str).set_index("cnpj_basico")
        _raiz = tabela["cnpj"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(14).str[:8]
        tabela["Linhas compradas"] = _raiz.map(_r["LINHAS_COMPRADAS"]).fillna("")
        tabela["Valor aceito (R$)"] = pd.to_numeric(_raiz.map(_r["VALOR_ACEITO_TOTAL"]), errors="coerce")
    tabela["Telefone"] = tabela["telefone_1"]
    tabela["WhatsApp"] = tabela.get("whatsapp_provavel", "")
    tabela["E-mail"] = tabela["email"]
    tabela["E-mail (site)"] = tabela.get("email_site", "")
    tabela["Instagram"] = tabela.get("instagram", "")
    tabela["Site"] = tabela.get("site", "")
    tabela["WhatsApp (site)"] = tabela.get("whatsapp_site", "")
    tabela["Responsável"] = (tabela["decisor"] + tabela.get("decisor_cargo", "").fillna("")
                             .map(lambda c: f" ({c})" if c else "")).str.strip()
    tabela["Confiança"] = tabela["confianca"]
    tabela["CNAEs secundários"] = tabela.get("cnaes_secundarios", "")
    tabela["Endereço"] = tabela.get("endereco", "")

    colunas_finais = [
        c
        for c in [
            "cnpj",
            "razao_social",
            "Municipio",
            "Endereço",
            "Telefone",
            "WhatsApp",
            "E-mail",
            "E-mail (site)",
            "Instagram",
            "Site",
            "WhatsApp (site)",
            "Responsável",
            "Confiança",
            "Tipo",
            "Situação cliente",
            "Última compra",
            "Linhas ativas",
            "Para reativar",
            "Para prospectar",
            "Linhas compradas",
            "Valor aceito (R$)",
            "Porte",
            "Porte FIEA",
            "CNAE PRIMARIO",
            "CNAEs secundários",
            "Estabelecimentos",
            "Possui SESI",
            "Possui SENAI",
            "Possui SESI + SENAI",
            "Status Relacionamento",
            "Status SEBRAE",
        ]
        if c in tabela.columns
    ]
    tabela_final = tabela[colunas_finais]
    vista = tabela_final.copy()
    for c in ("Instagram", "Site"):
        if c in vista:
            vista[c] = vista[c].where(vista[c].astype(str).str.startswith("http"), None)

    st.subheader("🎯 Visão 360")
    if len(tabela_final):
        _ops = tabela_final.head(3000)
        _rot = (_ops["razao_social"].astype(str) + " · " + _ops["cnpj"].astype(str)).tolist()
        _esc = st.selectbox("Escolha uma empresa (use a busca acima para filtrar a lista)", range(len(_rot)),
                            format_func=lambda i: _rot[i])
        _lin = _ops.iloc[_esc]
        from src.paginas.visao360 import cartao
        cartao(str(_lin["cnpj"]).replace(".", "").replace("/", "").replace("-", "").zfill(14)[:8],
               str(_lin["razao_social"]),
               " · ".join(str(_lin.get(c, "")) for c in ("Municipio", "Porte", "CNAE PRIMARIO") if str(_lin.get(c, ""))))
    st.subheader("Lista de empresas")
    st.dataframe(vista, use_container_width=True, height=600, hide_index=True, column_config={
        "Instagram": st.column_config.LinkColumn("Instagram", display_text=r"instagram\.com/(.+)"),
        "Site": st.column_config.LinkColumn("Site"),
    })

    st.download_button(
        "⬇️ Baixar resultado",
        data=tabela_final.to_csv(index=False).encode("utf-8-sig"),  # BOM: Excel lê os acentos
        file_name="empresas_filtradas.csv",
        mime="text/csv",
    )

    st.caption(
        "Quer a recomendação de produtos por IA para uma dessas empresas? "
        "Ative o \"Modo técnico\" na barra lateral e vá em \"🎯 Diagnóstico & Recomendação IA\" "
        "busque pelo mesmo CNPJ ou razão social."
    )


# ------------------------------------------------------------
# BASE QUALIFICADA (CRM) — cliente => cross-sell; não-cliente => inferência
# Reusa df_view (base já carregada) e pipeline (já carregado). Sem arquivo novo.
# ------------------------------------------------------------
elif pagina == "🎯 Base Qualificada (CRM)":
    st.header("🎯 Base Qualificada para o CRM")
    st.info(
        "🧭 **Leitura direcional.** Prioriza por CNAE + porte — ponto de partida "
        "para o consultor, **não previsão validada**. O produto sugerido é "
        "hipótese até o contato confirmar."
    )

    # ---- filtros (colunas que a base já tem) ----
    col1, col2, col3 = st.columns(3)
    with col1:
        f_trat = st.multiselect(
            "Tratamento",
            ["CROSS-SELL (já cliente)", "AQUISIÇÃO (sem vínculo)"],
        )
    with col2:
        f_porte = st.multiselect(
            "Porte", sorted(df_view["Porte"].dropna().unique())
        )
    with col3:
        limite = st.slider("Quantas empresas processar", 50, 1000, 200, step=50,
                           help="O diagnóstico roda o pipeline por empresa; comece pequeno.")

    # ---- seleciona o recorte a processar ----
    recorte = df_view.copy()
    if f_porte:
        recorte = recorte[recorte["Porte"].isin(f_porte)]
    if "CROSS-SELL (já cliente)" in f_trat and "AQUISIÇÃO (sem vínculo)" not in f_trat:
        recorte = recorte[recorte["POSSUI_SESI"] | recorte["POSSUI_SENAI"]]
    elif "AQUISIÇÃO (sem vínculo)" in f_trat and "CROSS-SELL (já cliente)" not in f_trat:
        recorte = recorte[~(recorte["POSSUI_SESI"] | recorte["POSSUI_SENAI"])]

    recorte = recorte.head(limite)
    st.caption(f"Processando {len(recorte)} empresas (de {len(df_view)} no contexto atual).")

    if st.button("▶️ Qualificar recorte"):
        linhas = []
        barra = st.progress(0.0)
        total = max(len(recorte), 1)
        for i, (_, emp) in enumerate(recorte.iterrows()):
            resultado = pipeline.executar(str(emp["cnpj"]))
            barra.progress((i + 1) / total)
            if resultado is None:
                continue
            lead = resultado["lead"]
            ops = resultado["oportunidades"]  # lista de Opportunity
            tratamento = "CROSS-SELL" if (lead.tem_sesi or lead.tem_senai) else "AQUISIÇÃO"
            top = ops[:3]
            linhas.append({
                "cnpj": lead.cnpj,
                "razao_social": lead.razao_social,
                "municipio": lead.municipio,
                "porte": lead.porte,
                "setor": lead.setor,
                "tratamento": tratamento,
                "prioridade": resultado["qualificacao"]["score"],
                "top_produtos": " | ".join(
                    f"{o.solucao} [{o.area}, fit {o.score_fit:.0f}]" for o in top
                ) or "(sem recomendação aprovada)",
                "leitura": "DIRECIONAL — CNAE+porte, não validada por consumo",
            })
        barra.empty()

        if not linhas:
            st.warning("Nenhuma empresa qualificada no recorte.")
        else:
            qualificada = pd.DataFrame(linhas).sort_values(
                ["tratamento", "prioridade"], ascending=[True, False]
            )
            c1, c2, c3 = st.columns(3)
            c1.metric("Qualificadas", numero(len(qualificada)))
            c2.metric("Cross-sell", numero(int((qualificada["tratamento"] == "CROSS-SELL").sum())))
            c3.metric("Aquisição", numero(int((qualificada["tratamento"] == "AQUISIÇÃO").sum())))
            st.dataframe(qualificada, use_container_width=True, height=520, hide_index=True)
            st.download_button(
                "⬇️ Baixar base qualificada (CSV)",
                data=qualificada.to_csv(index=False).encode("utf-8-sig"),  # BOM: Excel lê os acentos
                file_name="base_qualificada_crm.csv",
                mime="text/csv",
            )
    else:
        st.caption("Ajuste os filtros e clique em **Qualificar recorte** para gerar.")


# ------------------------------------------------------------
# 6. DIAGNÓSTICO & RECOMENDAÇÃO IA
# ------------------------------------------------------------
elif pagina == "🎯 Diagnóstico & Recomendação IA":
    st.header("🎯 Diagnóstico & Recomendação IA")
    st.caption(
        "Busca de lead → afinidade setorial → produtos reais do catálogo "
        "SESI/SENAI, filtrados por um Supervisor de qualidade."
    )

    mostrar_filtros = st.toggle(
        "Ver critérios de filtro e opções descartadas pelo sistema",
        value=False,
        help=(
            "As oportunidades recomendadas já passam por um filtro "
            "automático de qualidade antes de chegar até você. Ative "
            "esta opção para ver o que foi descartado e por quê — a "
            "decisão final sobre o que faz sentido oferecer ao cliente "
            "é sempre da equipe comercial, não do sistema."
        ),
    )

    busca_diag = st.text_input(
        "Buscar por CNPJ ou razão social",
        placeholder="Digite parte do CNPJ ou do nome pra filtrar a lista abaixo",
        key="busca_diagnostico",
    )

    candidatos = df_view
    if busca_diag:
        termo = busca_diag.strip()
        mascara_diag = pd.Series(False, index=candidatos.index)
        if "cnpj" in candidatos.columns:
            mascara_diag |= candidatos["cnpj"].astype(str).str.contains(termo, case=False, na=False, regex=False)
        if "razao_social" in candidatos.columns:
            mascara_diag |= candidatos["razao_social"].astype(str).str.contains(termo, case=False, na=False, regex=False)
        candidatos = candidatos[mascara_diag]

    opcoes = {}
    for linha in candidatos.itertuples():
        if not (linha.razao_social and linha.cnpj):
            continue
        rotulo = f"{linha.razao_social} — {linha.Municipio} (CNPJ {linha.cnpj})"
        qtd_filiais = getattr(linha, "QTD_FILIAIS", 0)
        if qtd_filiais:
            rotulo += f" · +{int(qtd_filiais)} filial(is)"
        opcoes[rotulo] = linha.cnpj

    if not opcoes:
        st.warning("Nenhuma empresa encontrada com esse filtro.")
        st.stop()

    st.caption(f"{len(opcoes)} empresa(s) na lista abaixo.")
    escolha = st.selectbox("Selecione a Empresa para Diagnóstico:", options=sorted(opcoes.keys()))
    cnpj_selecionado = opcoes[escolha]

    lead = pipeline.research.pesquisar(cnpj_selecionado)

    if lead is None:
        st.error("Empresa não encontrada na base de leads.")
        st.stop()

    qualidade = pipeline.data_quality.avaliar(lead)
    qualificacao = pipeline.sdr.qualificar(lead)
    auditoria = pipeline.opportunity.identificar_com_auditoria(lead)

    oportunidades = auditoria["aprovadas"]
    rejeitadas = auditoria["rejeitadas"]

    st.markdown("---")

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

    st.divider()
    st.subheader("🤖 Abordagem comercial gerada por IA")
    st.caption(
        "Usa a Claude API para transformar os dados acima em hipótese de "
        "dor, perguntas de qualificação, argumentação e próxima ação — "
        "em linguagem de SDR. Nunca inventa produto: só usa as "
        "oportunidades já aprovadas acima. Cada clique é uma chamada "
        "paga (~1-2 centavos de dólar) — por isso não é automático."
    )

    chave_estado = f"abordagem_ia_{lead.cnpj}"

    if st.button("Gerar abordagem comercial com IA"):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            st.error(
                "ANTHROPIC_API_KEY não configurada nesta sessão. Defina "
                "a variável de ambiente antes de iniciar o Streamlit."
            )
        else:
            with st.spinner("Consultando a IA..."):
                try:
                    agente_llm = SDRLLMAgent()
                    st.session_state[chave_estado] = agente_llm.gerar_abordagem(
                        lead, qualidade, qualificacao, oportunidades
                    )
                except Exception as erro:
                    st.error(f"Não foi possível gerar a abordagem: {erro}")

    if chave_estado in st.session_state:
        abordagem = st.session_state[chave_estado]

        st.markdown(f"**Hipótese de dor:** {abordagem.hipotese_dor}")

        st.markdown("**Perguntas de qualificação:**")
        for pergunta in abordagem.perguntas_qualificacao:
            st.markdown(f"- {pergunta}")

        st.markdown(f"**Argumentação:** {abordagem.argumentacao}")
        st.markdown(f"**Próxima ação:** {abordagem.proxima_acao}")


# ------------------------------------------------------------
# 8. ARQUITETURA & FLUXO (material de passagem ao Observatório)
# ------------------------------------------------------------
elif pagina == "🏗️ Arquitetura & Fluxo":
    render_arquitetura(resumo_consolidacao)


# ------------------------------------------------------------
# 7. AUDITORIA DE COBERTURA
# ------------------------------------------------------------
elif pagina == "✅ Auditoria de Cobertura":
    st.header("✅ Auditoria de Cobertura SESI/SENAI")
    st.caption(
        "Por que o número de clientes SESI/SENAI no dashboard não é igual "
        "ao total bruto do cadastro de relacionamento — e por que agora "
        "dá para confiar nele."
    )

    resultado_auditoria = carregar_auditoria_cobertura()
    if resultado_auditoria is None:
        st.info("Auditoria ainda não foi gerada para esta base.")
        st.stop()

    auditoria, correcao = resultado_auditoria
    total_bruto = len(auditoria)
    total_confirmado = auditoria["MOTIVO"].eq("Confirmada e incluída no universo").sum()

    st.markdown(
        "O cadastro de relacionamento do SESI/SENAI aponta um total de "
        "empresas maior do que o que aparece no mercado industrial de "
        "Alagoas. Auditamos **cada uma** dessas empresas direto na "
        "Receita Federal para separar o que é exclusão correta do que é "
        "lacuna real de cobertura."
    )
    st.divider()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi("Empresas auditadas", numero(total_bruto), "cadastradas como indústria, fora do mercado")
    with c2:
        kpi(
            "Fora de Alagoas / baixadas",
            numero(auditoria["MOTIVO"].isin(["Ativa, mas fora de Alagoas", "Baixada / inapta / suspensa"]).sum()),
            "exclusão correta, confirmada",
        )
    with c3:
        kpi(
            "Mudou de atividade",
            numero(auditoria["MOTIVO"].eq("Ativa em AL, mudou de atividade").sum()),
            "não é mais indústria hoje",
        )
    with c4:
        kpi("Gap real confirmado", numero(total_confirmado), "recuperadas para o universo")

    st.divider()
    st.subheader("Como se explica a diferença")
    st.bar_chart(auditoria["MOTIVO"].value_counts())
    st.caption(
        "Cada empresa foi checada individualmente na Receita Federal: "
        "situação cadastral, município/UF de registro e CNAE em vigor."
    )

    st.divider()
    st.subheader("Impacto por carteira")
    impacto = auditoria.groupby(["COBERTURA", "MOTIVO"]).size().unstack(fill_value=0)
    st.dataframe(impacto, use_container_width=True)

    st.divider()
    st.subheader("Empresas recuperadas para o seu radar comercial")
    st.caption(
        "Já são clientes SESI e/ou SENAI, estão ativas em Alagoas com "
        "CNAE de indústria — agora aparecem nas demais páginas do dashboard."
    )

    if correcao is not None and not correcao.empty:
        tabela_recuperadas = correcao[["razao_social", "Municipio", "Porte", "CNAE PRIMARIO"]].rename(
            columns={"razao_social": "Empresa", "Municipio": "Município", "CNAE PRIMARIO": "Atividade"}
        )
        st.dataframe(tabela_recuperadas, use_container_width=True, height=350, hide_index=True)
    else:
        st.info("Nenhuma empresa recuperada nesta versão da base.")

    st.caption(
        "Metodologia: cruzamento de CNPJ contra consulta pública de dados "
        "da Receita Federal (situação cadastral, município/UF e CNAE "
        "fiscal principal). Considerado indústria de transformação quando "
        "o CNAE em vigor está nas divisões 10 a 33."
    )
