"""Páginas "👥 Clientes" e "🎯 Mercado — Potencial".

Dois públicos, dois tratamentos:
* Clientes (já compraram): reter e expandir. Porte FIEA do cadastro.
* Mercado (nunca compraram): conquistar. Nota de potencial = quão parecida a empresa é
  com quem já compra (jobs/calcular_potencial.py), com o motivo escrito ao lado.

Os mesmos filtros nas duas: unidade SESI e SENAI (Minuta de Carteirização), categoria
(indústria ou não), segmento, porte (régua FIEA ou Receita, nunca misturadas),
município e bairro.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.tools.universo_comercial import (A_CONFIRMAR, CLIENTE, MERCADO, ORDEM_FAIXAS, ORDEM_PORTE_FIEA,
                                          ORDEM_PORTE_RECEITA, filtrar, opcoes)

UNIDADES_SESI = ["Farol", "Tabuleiro", "Agreste/Sertão"]
UNIDADES_SENAI = ["Poço", "Agreste/Sertão"]


def _n(x) -> str:
    return f"{int(x):,}".replace(",", ".")


def _pct(a, b) -> str:
    return f"{a / b * 100:.1f}%".replace(".", ",") if b else "–"


def filtros(u: pd.DataFrame, chave: str) -> pd.DataFrame:
    """Barra de filtros na lateral. `chave` separa o estado das duas páginas."""
    sb = st.sidebar
    sb.subheader("Filtros")
    k = lambda nome: f"{chave}_{nome}"  # noqa: E731
    sesi = sb.multiselect("Unidade SESI", opcoes(u["Unidade SESI"], UNIDADES_SESI), key=k("sesi"),
                          help="Pela Minuta de Carteirização: cliente fica na unidade do histórico; empresa nova "
                               "vai pelo endereço da sede (bairro em Maceió, município no interior).")
    senai = sb.multiselect("Unidade SENAI", opcoes(u["Unidade SENAI"], UNIDADES_SENAI), key=k("senai"),
                           help="Benedito Bentes foi desativado: as empresas dele estão no Poço.")
    categorias = sb.multiselect("Categoria", ["Indústria", "Não indústria"], key=k("cat"),
                                help="Indústria = CNAE na tabela da CNI. O SESI também atende não indústria.")
    segmentos = sb.multiselect("Segmento (CNAE)", opcoes(u["Segmento"]), key=k("seg"))
    regua = sb.radio("Régua de porte", ["FIEA", "Receita"], horizontal=True, key=k("regua"),
                     help="FIEA = colaboradores (Micro 0–19, EPP 20–99, Média 100–499, Demais 500+). "
                          "Receita = faturamento (ME/EPP/Demais). São réguas diferentes: uma empresa pode ser "
                          "Demais na Receita e Micro na FIEA. Empresa sem número de colaboradores fica "
                          f"'{A_CONFIRMAR}'.")
    ordem = ORDEM_PORTE_FIEA if regua == "FIEA" else ORDEM_PORTE_RECEITA
    col_porte = "Porte FIEA" if regua == "FIEA" else "Porte Receita"
    portes = sb.multiselect("Porte", opcoes(u[col_porte], ordem), key=k("porte"))
    municipios = sb.multiselect("Município", opcoes(u["Município"]), key=k("mun"))
    base_bairro = u[u["Município"].isin(municipios)] if municipios else u
    bairros = sb.multiselect("Bairro", opcoes(base_bairro["Bairro"]), key=k("bairro"))
    busca = sb.text_input("Razão social ou CNPJ", key=k("busca"))
    return filtrar(u, unidades_sesi=sesi, unidades_senai=senai, categorias=categorias, segmentos=segmentos,
                   regua=regua, portes=portes, municipios=municipios, bairros=bairros, busca=busca)


def _contagem(df: pd.DataFrame, coluna: str, ordem: list[str] | None = None) -> pd.DataFrame:
    c = df[coluna].replace("", "Sem unidade").value_counts()
    if ordem:
        c = c.reindex([o for o in ordem if o in c.index] + [i for i in c.index if i not in ordem])
    return c.rename("Empresas").to_frame()


def render_clientes(universo: pd.DataFrame) -> None:
    st.header("👥 Clientes — com relacionamento")
    st.caption("Empresas que já compraram de SESI ou SENAI (proposta aceita). Aqui o trabalho é **reter** "
               "(quem esfriou) e **expandir** (o que ainda não compraram). Porte FIEA vem do nosso cadastro.")
    base = universo[universo["Relacionamento"] == CLIENTE]
    df = filtros(base, "cli")
    ativos = int((df["Situação"] == "Ativo").sum())
    inativos = int((df["Situação"] == "Inativo").sum())
    c = st.columns(5)
    c[0].metric("Clientes", _n(len(df)))
    c[1].metric("Ativos (24 meses)", _n(ativos), _pct(ativos, len(df)), delta_color="off")
    c[2].metric("Inativos — reter", _n(inativos), _pct(inativos, len(df)), delta_color="off")
    c[3].metric("Só SESI ou só SENAI", _n(df["Entidade"].isin(["SESI", "SENAI"]).sum()),
                "espaço para a outra casa", delta_color="off")
    c[4].metric("Porte FIEA a confirmar", _n((df["Porte FIEA"] == A_CONFIRMAR).sum()),
                help="Cliente sem porte no cadastro: o comercial confirma o nº de colaboradores.")

    a, b, d = st.columns(3)
    a.markdown("**Por porte FIEA**")
    a.bar_chart(_contagem(df, "Porte FIEA", ORDEM_PORTE_FIEA), sort=False)
    b.markdown("**Por unidade SESI**")
    b.bar_chart(_contagem(df, "Unidade SESI", UNIDADES_SESI), sort=False)
    d.markdown("**Por unidade SENAI**")
    d.bar_chart(_contagem(df, "Unidade SENAI", UNIDADES_SENAI), sort=False)

    st.subheader("Carteira")
    cols = ["Razão social", "cnpj_basico", "Situação", "Entidade", "Última compra", "Porte FIEA", "Porte Receita",
            "Categoria", "Segmento", "Município", "Bairro", "Unidade SESI", "Unidade SENAI"]
    tabela = df[cols].sort_values(["Situação", "Última compra"], ascending=[True, False])
    st.dataframe(tabela, width="stretch", hide_index=True,
                 column_config={"cnpj_basico": "CNPJ raiz"})
    st.download_button("⬇️ Baixar carteira filtrada", tabela.to_csv(index=False).encode("utf-8-sig"),
                       file_name="clientes_filtrados.csv", mime="text/csv")
    st.info("Próximo passo: segmentação RFV (Alta Performance, Fidelizados, Risco de Inatividade…) alinhada à do "
            "Núcleo de Estratégia e Mercado, e o portfólio por cliente (o que comprou × o que falta oferecer).")


def render_mercado(universo: pd.DataFrame) -> None:
    st.header("🎯 Mercado — potencial (sem relacionamento)")
    st.caption("Empresas que **nunca compraram**. A nota mostra o quanto cada uma se parece com quem já é "
               "cliente — perfil de CNAE, porte, município, capital, filiais e idade, só com dado público. "
               "Ao fechar a primeira proposta, a empresa passa sozinha para a página de Clientes.")
    base = universo[universo["Relacionamento"] == MERCADO]
    if base["Potencial"].eq("").all():
        st.warning("Potencial ainda não calculado. Rode `python jobs/calcular_potencial.py` e publique "
                   "`data/processed/POTENCIAL_MERCADO.csv`.")
    df = filtros(base, "mer")
    f1, f2 = st.columns([3, 2])
    faixas = f1.multiselect("Potencial", ORDEM_FAIXAS, default=["Muito alto", "Alto"], key="mer_faixa")
    esconder = f2.toggle("Esconder empresas com alerta", value=True, key="mer_alerta",
                         help="Falência / recuperação judicial e sede fora de AL (conta nacional; pela minuta, "
                              "fica com a unidade do 1º atendimento).")
    vis = df[df["Potencial"].isin(faixas)] if faixas else df
    if esconder:
        vis = vis[vis["Alerta"] == ""]

    c = st.columns(5)
    c[0].metric("Sem relacionamento", _n(len(df)))
    c[1].metric("Muito alto", _n((df["Potencial"] == "Muito alto").sum()), help="Perfis em que ≥30% das parecidas já compram.")
    c[2].metric("Alto", _n((df["Potencial"] == "Alto").sum()), help="15–30% das parecidas já compram.")
    c[3].metric("Na fila (filtros atuais)", _n(len(vis)))
    c[4].metric("Porte FIEA a confirmar", _n((vis["Porte FIEA"] == A_CONFIRMAR).sum()),
                help="Na fila sem nº de colaboradores: a primeira pergunta da abordagem (ou Apollo).")

    a, b = st.columns(2)
    a.markdown("**Muito alto e alto, por segmento**")
    pv = df[df["Potencial"] != ""].pivot_table(index="Segmento", columns="Potencial", values="cnpj_basico",
                                                aggfunc="count", fill_value=0)
    pv = pv[[f for f in ["Muito alto", "Alto"] if f in pv.columns]]
    if not pv.empty:
        top = pv.loc[pv.sum(axis=1).sort_values(ascending=False).index[:12]]
        a.bar_chart(top, horizontal=True, sort=False, color=["#0b3d91", "#7fb2e5"][: len(top.columns)])
    b.markdown("**Fila por unidade SESI / SENAI**")
    uni = pd.concat([vis["Unidade SESI"].replace("", "Sem unidade").value_counts().rename("SESI"),
                     vis["Unidade SENAI"].replace("", "Sem unidade").value_counts().rename("SENAI")], axis=1).fillna(0)
    b.bar_chart(uni, stack=False, color=["#0b3d91", "#e8792b"])

    st.subheader("Fila — conquistar")
    cols = ["Razão social", "cnpj_basico", "Nota", "Potencial", "Motivo", "Categoria", "Segmento", "CNAE",
            "Município", "Bairro", "Porte Receita", "Porte FIEA", "Unidade SESI", "Unidade SENAI", "Alerta"]
    tabela = vis[cols].sort_values("Nota", ascending=False)
    st.dataframe(tabela, width="stretch", hide_index=True, column_config={
        "cnpj_basico": "CNPJ raiz",
        "Nota": st.column_config.ProgressColumn("Nota", min_value=0, max_value=10, format="%.1f"),
        "Motivo": st.column_config.TextColumn(width="large"),
    })
    st.download_button("⬇️ Baixar fila filtrada", tabela.to_csv(index=False).encode("utf-8-sig"),
                       file_name="fila_conquistar.csv", mime="text/csv")
    st.caption("Como ler a nota: 0–10, a chance de a empresa ser cliente se ela se comportasse como as parecidas "
               "(validação: os 10% de maior nota concentram ~4× mais clientes reais que uma lista aleatória). "
               "Não é previsão de venda — é a ordem de abordagem. Porte FIEA fica 'A confirmar' até termos o "
               "número de colaboradores; a régua da Receita é só peneira.")
