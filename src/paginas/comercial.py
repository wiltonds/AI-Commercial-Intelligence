"""Páginas "👥 Clientes" e "🎯 Mercado — Potencial", feitas para o consultor comercial.

Primeira escolha, no topo: Indústria ou Não indústria (são públicos e conversas diferentes).
Depois, os mesmos filtros nas duas páginas, na lateral: unidade SESI e SENAI (Minuta de
Carteirização), município, bairro, porte, atividade e busca por nome/CNPJ.

* Clientes (já compraram): reter e expandir. Porte FIEA do cadastro.
* Mercado (nunca compraram): conquistar. Prioridade = quão parecida a empresa é com quem
  já compra (jobs/calcular_potencial.py), com o motivo escrito ao lado.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.tools.universo_comercial import CLIENTE, MERCADO, ORDEM_FAIXAS, ORDEM_PORTE, filtrar, opcoes

UNIDADES_SESI = ["Farol", "Tabuleiro", "Agreste/Sertão"]
UNIDADES_SENAI = ["Poço", "Agreste/Sertão"]
INDUSTRIA, NAO_INDUSTRIA = "Indústria", "Não indústria"
ROTULO_PUBLICO = {INDUSTRIA: "🏭 Indústria", NAO_INDUSTRIA: "🏪 Não indústria"}
EXPLICA_PUBLICO = {
    INDUSTRIA: "Empresas com atividade industrial (tabela da CNI): fábricas, construção, extração, energia…",
    NAO_INDUSTRIA: "Comércio, serviços, saúde, educação, alimentação… O SESI também atende essas empresas.",
}


def _n(x) -> str:
    return f"{int(x):,}".replace(",", ".")


def _pct(a, b) -> str:
    return f"{a / b * 100:.0f}%" if b else "–"


def _cartao(col, rotulo: str, valor, nota: str = "", ajuda: str | None = None) -> None:
    """Número grande + legenda neutra embaixo. O delta do st.metric põe seta (↑) e corta o texto."""
    col.metric(rotulo, valor, help=ajuda)
    if nota:
        col.caption(nota)


def escolher_publico(base: pd.DataFrame, chave: str) -> tuple[str, pd.DataFrame]:
    """Indústria ou Não indústria, com o tamanho de cada uma no botão."""
    tamanho = base["Categoria"].value_counts()
    escolha = st.segmented_control(
        "Público", [INDUSTRIA, NAO_INDUSTRIA], default=INDUSTRIA, key=f"{chave}_publico",
        format_func=lambda p: f"{ROTULO_PUBLICO[p]}  ·  {_n(tamanho.get(p, 0))}", label_visibility="collapsed",
    ) or INDUSTRIA
    st.caption(EXPLICA_PUBLICO[escolha])
    return escolha, base[base["Categoria"] == escolha]


def filtros(u: pd.DataFrame, chave: str, regua_padrao: str) -> tuple[pd.DataFrame, str]:
    """Filtros na lateral. Devolve a base filtrada e a régua de porte em uso."""
    sb = st.sidebar
    sb.subheader("Filtros")
    k = lambda nome: f"{chave}_{nome}"  # noqa: E731
    busca = sb.text_input("🔍 Procurar empresa", placeholder="nome ou CNPJ", key=k("busca"))
    sesi = sb.multiselect("Unidade SESI", opcoes(u["Unidade SESI"], UNIDADES_SESI), key=k("sesi"),
                          help="Unidade responsável pela empresa (Minuta de Carteirização). Cliente fica na "
                               "unidade onde já compra; empresa nova vai pelo endereço da sede.")
    senai = sb.multiselect("Unidade SENAI", opcoes(u["Unidade SENAI"], UNIDADES_SENAI), key=k("senai"),
                           help="Benedito Bentes foi desativado: as empresas dele estão no Poço.")
    municipios = sb.multiselect("Município", opcoes(u["Município"]), key=k("mun"))
    base_bairro = u[u["Município"].isin(municipios)] if municipios else u
    bairros = sb.multiselect("Bairro", opcoes(base_bairro["Bairro"]), key=k("bairro"))
    segmentos = sb.multiselect("Atividade", opcoes(u["Segmento"]), key=k("seg"),
                               help="Grande grupo da atividade principal (CNAE).")
    regua = "Porte"
    portes = sb.multiselect("Porte", opcoes(u["Porte"], ORDEM_PORTE), key=k("porte4"),
                            help="Micro até 19 colaboradores, Pequena 20–99, Média 100–499, Grande 500+. "
                                 "Vem do cadastro FIEA; sem cadastro, do nº de colaboradores (real ou estimado). "
                                 "Sem nenhum dado, porte 'DEMAIS' da Receita conta como Média.")
    df = filtrar(u, unidades_sesi=sesi, unidades_senai=senai, segmentos=segmentos, regua=regua, portes=portes,
                 municipios=municipios, bairros=bairros, busca=busca)
    return df, regua


def _contagem(df: pd.DataFrame, coluna: str, ordem: list[str] | None = None) -> pd.DataFrame:
    c = df[coluna].replace("", "Sem unidade").value_counts()
    if ordem:
        c = c.reindex([o for o in ordem if o in c.index] + [i for i in c.index if i not in ordem])
    return c.rename("Empresas").to_frame()


def _por_unidade(df: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([df["Unidade SESI"].replace("", "Sem unidade").value_counts().rename("SESI"),
                      df["Unidade SENAI"].replace("", "Sem unidade").value_counts().rename("SENAI")],
                     axis=1).fillna(0)


def _atividade(df: pd.DataFrame) -> pd.Series:
    """'1091-1/00 · Fabricação de produtos de panificação' -> 'Fabricação de produtos de panificação'."""
    return df["CNAE"].astype(str).str.split(" · ", n=1).str[-1]


def render_clientes(universo: pd.DataFrame) -> None:
    st.header("👥 Clientes")
    st.caption("Empresas que **já compraram** de SESI ou SENAI. O trabalho aqui é **não perder** quem parou de "
               "comprar e **vender mais** para quem já é cliente.")
    publico, base = escolher_publico(universo[universo["Relacionamento"] == CLIENTE], "cli")
    df, regua = filtros(base, "cli", "FIEA")

    ativos = int((df["Situação"] == "Ativo").sum())
    inativos = int((df["Situação"] == "Inativo").sum())
    uma_casa = int(df["Entidade"].isin(["SESI", "SENAI"]).sum())
    c = st.columns(4)
    _cartao(c[0], "Clientes", _n(len(df)), f"{publico.lower()} · com os filtros")
    _cartao(c[1], "Compram hoje", _n(ativos), f"{_pct(ativos, len(df))} · compraram nos últimos 2 anos")
    _cartao(c[2], "Pararam de comprar", _n(inativos), f"{_pct(inativos, len(df))} · ligar para recuperar")
    _cartao(c[3], "Compram de uma casa só", _n(uma_casa), "só SESI ou só SENAI · oferecer a outra")

    a, b = st.columns(2)
    a.markdown("**Clientes por porte**")
    a.bar_chart(_contagem(df, "Porte", ORDEM_PORTE), sort=False)
    b.markdown("**Clientes por unidade**")
    b.bar_chart(_por_unidade(df), stack=False, color=["#0b3d91", "#e8792b"])

    st.subheader("Lista de clientes")
    tabela = pd.DataFrame({
        "Empresa": df["Razão social"], "CNPJ raiz": df["cnpj_basico"], "Situação": df["Situação"],
        "Compra de": df["Entidade"], "Última compra": df["Última compra"],
        "Porte": df["Porte"], "Atividade": _atividade(df),
        "Município": df["Município"], "Bairro": df["Bairro"],
        "Unidade SESI": df["Unidade SESI"], "Unidade SENAI": df["Unidade SENAI"],
    }).sort_values(["Situação", "Última compra"], ascending=[False, False])
    st.caption("Primeiro quem parou de comprar (Inativo), do mais recente para o mais antigo.")
    st.dataframe(tabela, width="stretch", hide_index=True)
    st.download_button("⬇️ Baixar esta lista", tabela.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"clientes_{publico.lower().replace(' ', '_')}.csv", mime="text/csv")


def render_mercado(universo: pd.DataFrame) -> None:
    st.header("🎯 Mercado — quem procurar")
    st.caption("Empresas que **nunca compraram**. A prioridade diz o quanto cada uma se parece com quem já é "
               "nosso cliente (atividade, porte, cidade, tamanho, idade). Quando fechar a primeira proposta, "
               "ela passa sozinha para a página de Clientes.")
    base = universo[universo["Relacionamento"] == MERCADO]
    if base["Potencial"].eq("").all():
        st.warning("Prioridade ainda não calculada. Rode `python jobs/calcular_potencial.py` e publique "
                   "`data/processed/POTENCIAL_MERCADO.csv`.")
    publico, base = escolher_publico(base, "mer")
    df, regua = filtros(base, "mer", "Receita")

    f1, f2 = st.columns([3, 2])
    faixas = f1.multiselect("Prioridade", ORDEM_FAIXAS, default=["Muito alto", "Alto"], key="mer_faixa",
                            help="Muito alto: em perfis assim, 30% ou mais das empresas já compram. "
                                 "Alto: 15 a 30%. Médio: 5 a 15%. Baixo: menos de 5%.")
    esconder = f2.toggle("Esconder empresas com problema", value=True, key="mer_alerta",
                         help="Falência ou recuperação judicial, e empresas com sede fora de Alagoas "
                              "(atendidas pela unidade do 1º serviço).")
    vis = df[df["Potencial"].isin(faixas)] if faixas else df
    if esconder:
        vis = vis[vis["Alerta"] == ""]

    c = st.columns(4)
    _cartao(c[0], "Nunca compraram", _n(len(df)), f"{publico.lower()} · com os filtros")
    _cartao(c[1], "Prioridade muito alta", _n((df["Potencial"] == "Muito alto").sum()),
            "muito parecidas com nossos clientes")
    _cartao(c[2], "Prioridade alta", _n((df["Potencial"] == "Alto").sum()), "parecidas com nossos clientes")
    _cartao(c[3], "Na sua lista", _n(len(vis)), "prioridade escolhida, abaixo")

    a, b = st.columns(2)
    # tabela com barra em vez de gráfico: nome de atividade é longo e o eixo do gráfico corta
    grupo = _atividade(vis).str.capitalize() if publico == INDUSTRIA else vis["Segmento"]
    a.markdown("**Na sua lista, por atividade**" if publico == INDUSTRIA else "**Na sua lista, por tipo de negócio**")
    top = grupo.value_counts().head(10).rename_axis("Atividade").rename("Empresas").reset_index()
    a.dataframe(top, hide_index=True, width="stretch", height=387, column_config={
        "Atividade": st.column_config.TextColumn(width="large"),
        "Empresas": st.column_config.ProgressColumn("Empresas", format="%d", min_value=0,
                                                    max_value=int(top["Empresas"].max()) if len(top) else 1),
    })
    b.markdown("**Na sua lista, por unidade**")
    b.bar_chart(_por_unidade(vis), stack=False, color=["#0b3d91", "#e8792b"])

    st.subheader("Lista para procurar")
    tabela = pd.DataFrame({
        "Empresa": vis["Razão social"], "CNPJ raiz": vis["cnpj_basico"], "Nota": vis["Nota"],
        "Prioridade": vis["Potencial"], "Por quê": vis["Motivo"], "Atividade": _atividade(vis),
        "Porte": vis["Porte"],
        "Município": vis["Município"], "Bairro": vis["Bairro"],
        "Unidade SESI": vis["Unidade SESI"], "Unidade SENAI": vis["Unidade SENAI"], "Atenção": vis["Alerta"],
    }).sort_values("Nota", ascending=False)
    if esconder:
        tabela = tabela.drop(columns=["Atenção"])
    st.caption("Da mais parecida com nossos clientes para a menos. A nota vai de 0 a 10.")
    st.dataframe(tabela, width="stretch", hide_index=True, column_config={
        "Nota": st.column_config.ProgressColumn("Nota", min_value=0, max_value=10, format="%.1f"),
        "Por quê": st.column_config.TextColumn(width="large"),
    })
    st.download_button("⬇️ Baixar esta lista", tabela.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"procurar_{publico.lower().replace(' ', '_')}.csv", mime="text/csv")
    with st.expander("Como a prioridade é calculada?"):
        st.markdown(
            "- Olhamos as empresas que **já compram** e as que **nunca compraram**, só com dado público "
            "(atividade, porte, cidade, capital, nº de filiais e idade).\n"
            "- Cada empresa recebe uma nota de 0 a 10: quanto **mais parecida com nossos clientes**, maior.\n"
            "- Na validação, as 10% de maior nota tinham cerca de **4 vezes mais clientes** que uma lista "
            "aleatória.\n"
            "- **Não é garantia de venda** — é a ordem sugerida para procurar.\n"
            "- O porte aqui é o da **Receita** (faturamento): empresa nova ainda não tem o nº de colaboradores "
            "no nosso cadastro. Pergunte na primeira conversa.")
