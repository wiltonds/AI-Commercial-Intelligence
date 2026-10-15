"""
Página de arquitetura e fluxo de dados — material de passagem para o
time do Observatório.

Mostra, em uma tela, de onde vem o universo industrial (Receita
Federal), quais regras são aplicadas em ordem, e como a Etapa 2 (Moskit
+ ML) se encaixa depois. As contagens das etapas finais são calculadas
ao vivo sobre a Base Mestre carregada; as etapas iniciais vêm do
relatório de auditoria da extração da Receita, que roda fora do app.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st


# Relatório de auditoria V4 da extração da Receita (Desktop/BI_Project,
# dataset_072026_v4/AUDITORIA). Atualizar a cada nova competência até o
# job de produção gravar esses números em ic.controle_lote.
COMPETENCIA_RECEITA = "2026-07"
FUNIL_RECEITA = {
    "ativos_al_estab": 232_017,
    "ativos_al_raiz": 224_298,
    "industria_estab": 58_100,
    "industria_raiz": 56_448,
    "industria_principal_estab": 36_874,
    "base_mae_com_correcoes": 32_935,
}

FLUXO_ETAPAS = """
digraph {
    rankdir=LR;
    node [shape=box, style="rounded,filled", fillcolor="#eef2f7", fontname="Helvetica", fontsize=11];
    edge [color="#888888"];

    subgraph cluster_e1 {
        label="Etapa 1 — produtizar o piloto"; fontname="Helvetica"; color="#1f77b4";
        receita [label="Receita Federal\\nAL + ATIVA (mensal)"];
        cnae    [label="CNAE × tabela DN\\n(principal e secundários)"];
        mei     [label="Exclusão MEI\\n(arquivo Simples)"];
        rel     [label="Relacionamento\\nSESI · SENAI · SEBRAE"];
        raiz    [label="Consolidação\\nCNPJ raiz"];
        painel  [label="Painel + regras\\nde recomendação"];
        receita -> cnae -> mei -> rel -> raiz -> painel;
    }

    subgraph cluster_e2 {
        label="Etapa 2 — inteligência comercial"; fontname="Helvetica"; color="#ff7f0e";
        moskit  [label="CRM Moskit\\n(no DW)"];
        ml      [label="Features + ML\\n(propensão, próximo produto)"];
        crm     [label="Tarefa para o\\nvendedor no Moskit"];
        moskit -> ml -> crm;
    }

    painel -> moskit [style=dashed, label=" CNPJ raiz"];
    crm -> moskit [style=dashed, label=" resultado da venda", constraint=false];
}
"""

CAMADAS_DW = """
digraph {
    rankdir=LR;
    node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11];
    fontes [label="Fontes\\nReceita · SESI/SENAI · SEBRAE\\nMoskit · catálogo · novas bases", fillcolor="#f5f5f5"];
    stg    [label="stg\\nbruto, por lote", fillcolor="#fde9d9"];
    dw     [label="dw\\ndim_empresa · fato_relacionamento\\ntabelas Moskit", fillcolor="#dbe9f6"];
    ic     [label="ic\\nfeatures · scores · recomendações", fillcolor="#e2f0d9"];
    app    [label="Painel Streamlit\\n(views ic.vw_*)", fillcolor="#f5f5f5"];
    fontes -> stg -> dw -> ic -> app;
}
"""

REGRAS = pd.DataFrame(
    [
        ("1", "Download da competência", "Estabelecimentos*.zip + Simples.zip, lidos em streaming", "BI_Project/baixar_cnpj_al.py"),
        ("2", "Recorte AL + ATIVA", "UF = AL e situação cadastral 02", "BI_Project/gerar_dataset_cnpj_al_v4.py"),
        ("3", "CNPJ padronizado", "14 dígitos; CNPJ raiz = 8 primeiros", "construir_base_mestre.py"),
        ("4", "Cruzamento de CNAE", "Principal e secundários × tabela DN (1.298 CNAEs)", "gerar_dataset_cnpj_al_v4.py"),
        ("5", "Correções auditadas", "CNPJs clientes conferidos na Receita", "CORRECAO_UNIVERSO_CONFIRMADA.csv"),
        ("6", "Exclusão MEI", "Raiz com opcao_mei = S sai do universo", "construir_base_mestre.py (bloco 1B)"),
        ("7", "Relacionamento", "SESI, SENAI, SEBRAE; status e cross-sell", "construir_base_mestre.py"),
        ("8", "Consolidação por raiz", "Uma linha por empresa; relacionamento herdado do grupo", "src/tools/cnpj_raiz.py"),
    ],
    columns=["#", "Regra", "O que faz", "Onde está hoje"],
)


def _fmt(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


def _funil(total_estabelecimentos: int, total_empresas: int) -> pd.DataFrame:
    f = FUNIL_RECEITA
    linhas = [
        ("Ativos em Alagoas", f["ativos_al_estab"], f["ativos_al_raiz"], "Receita (auditoria V4)"),
        ("Com atividade industrial (tabela DN)", f["industria_estab"], f["industria_raiz"], "Receita (auditoria V4)"),
        ("  dos quais pelo CNAE principal", f["industria_principal_estab"], None, "Receita (auditoria V4)"),
        ("Base-mãe comercial + correções", f["base_mae_com_correcoes"], None, "construir_base_mestre.py"),
        ("Após excluir optantes MEI", total_estabelecimentos, total_empresas, "Base Mestre (ao vivo)"),
    ]
    tabela = pd.DataFrame(
        linhas, columns=["Etapa", "Estabelecimentos", "Empresas (CNPJ raiz)", "Origem do número"]
    )
    for col in ("Estabelecimentos", "Empresas (CNPJ raiz)"):
        tabela[col] = tabela[col].map(lambda v: "—" if pd.isna(v) else _fmt(v))
    return tabela


def render_arquitetura(resumo_consolidacao: dict) -> None:
    st.header("🏗️ Arquitetura & Fluxo de Dados")
    st.caption(
        "Visão para o time do Observatório: de onde vem cada número do "
        "painel, quais regras são aplicadas e o que entra na Etapa 2."
    )

    st.subheader("Duas etapas")
    st.graphviz_chart(FLUXO_ETAPAS, width="stretch")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            "**Etapa 1 — produtizar o piloto.** Job mensal da Receita, "
            "regras de indústria e MEI, Base Mestre, CNPJ raiz e painel "
            "lendo do DW. Pronta quando uma nova competência reproduz o "
            "funil abaixo sem nenhum passo manual."
        )
    with c2:
        st.markdown(
            "**Etapa 2 — Moskit + ML.** Liga o CRM pelo CNPJ raiz, aprende "
            "com as negociações ganhas e perdidas, prioriza a carteira e "
            "devolve a recomendação ao vendedor."
        )

    st.divider()
    st.subheader(f"Funil do universo industrial — competência {COMPETENCIA_RECEITA}")
    st.dataframe(
        _funil(
            resumo_consolidacao["total_estabelecimentos"],
            resumo_consolidacao["total_empresas"],
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "As quatro primeiras linhas vêm da extração da Receita e da "
        "construção da Base Mestre, que rodam fora do app. A última é "
        "calculada agora sobre a Base Mestre carregada."
    )

    st.divider()
    st.subheader("Regras aplicadas, em ordem")
    st.dataframe(REGRAS, hide_index=True, width="stretch")

    st.divider()
    st.subheader("Camadas no DW (alvo)")
    st.graphviz_chart(CAMADAS_DW, width="stretch")
    st.caption(
        "Hoje o painel lê CSV local; em produção passa a ler as views "
        "ic.vw_* do SQL Server. A lógica em src/ não muda."
    )
