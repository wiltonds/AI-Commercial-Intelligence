"""Página "📈 Share & Relacionamento" — quem já atendemos, quem atendemos hoje,
onde temos share e quais produtos mais vendemos.

Lê as colunas que jobs/atualizar_relacionamento.py grava na Base Mestre
(SITUACAO_CLIENTE, ULTIMA_COMPRA, CNPJ_ATENDIDO...) e os agregados
PRODUTOS_RANKING.csv e ATENDIMENTO_POR_ANO.csv.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parents[2]
ARQ_RANKING = RAIZ / "data" / "processed" / "PRODUTOS_RANKING.csv"
ARQ_ANOS = RAIZ / "data" / "processed" / "ATENDIMENTO_POR_ANO.csv"


def _pct(parte: float, todo: float) -> str:
    return f"{(parte / todo * 100):.1f}%".replace(".", ",") if todo else "–"


def _n(x) -> str:
    return f"{int(x):,}".replace(",", ".")


def tabela_share(df: pd.DataFrame, coluna: str, minimo: int = 0) -> pd.DataFrame:
    g = df.groupby(coluna).agg(
        Empresas=("SITUACAO_CLIENTE", "size"),
        Ja_atendidas=("SITUACAO_CLIENTE", lambda s: s.isin(["Ativo", "Inativo"]).sum()),
        Ativas=("SITUACAO_CLIENTE", lambda s: (s == "Ativo").sum()),
    )
    g = g[g["Empresas"] >= minimo]
    g["Share (já atendidas)"] = (g["Ja_atendidas"] / g["Empresas"] * 100).round(1)
    g["Share (ativas)"] = (g["Ativas"] / g["Empresas"] * 100).round(1)
    g["Ainda sem compra"] = g["Empresas"] - g["Ja_atendidas"]
    return g.rename(columns={"Ja_atendidas": "Já atendidas"}).sort_values("Empresas", ascending=False)


def render(df_empresas: pd.DataFrame, df_estab: pd.DataFrame) -> None:
    st.header("📈 Share & Relacionamento")
    if "SITUACAO_CLIENTE" not in df_empresas.columns:
        st.info("Relacionamento ainda não atualizado. Rode `python jobs/atualizar_relacionamento.py "
                "--arquivo <exportação de propostas>`.")
        return
    st.caption("Cliente = pelo menos uma proposta **Aceita** de SESI ou SENAI. **Ativo** = última compra nos "
               "últimos 24 meses; **Inativo** = já comprou, mas antes disso. Fonte: exportação de propostas desde 2018. "
               "⚠️ O histórico do SESI nesse sistema começa em 2024: compras SESI anteriores não aparecem.")

    df = df_empresas.copy()
    df["SITUACAO_CLIENTE"] = df["SITUACAO_CLIENTE"].fillna("Sem compra").replace("", "Sem compra")
    total = len(df)
    ja = int(df["SITUACAO_CLIENTE"].isin(["Ativo", "Inativo"]).sum())
    ativos = int((df["SITUACAO_CLIENTE"] == "Ativo").sum())
    inativos = ja - ativos
    unidades = int((df_estab.get("CNPJ_ATENDIDO", pd.Series(dtype=str)) == "Sim").sum())

    c = st.columns(5)
    c[0].metric("Mercado industrial", _n(total), help="Empresas (CNPJ raiz) no contexto atual.")
    c[1].metric("Já atendidas", _n(ja), _pct(ja, total) + " de share", delta_color="off")
    c[2].metric("Ativas (24 meses)", _n(ativos), _pct(ativos, total) + " de share", delta_color="off")
    c[3].metric("Inativas", _n(inativos), "já compraram, esfriaram", delta_color="off")
    c[4].metric("Unidades atendidas", _n(unidades), f"de {_n(len(df_estab))} CNPJs", delta_color="off",
                help="CNPJs únicos (matriz ou filial) que tiveram proposta aceita.")

    st.divider()
    st.subheader("Share por segmento")
    st.caption("Segmentos grandes com share baixo são onde está o espaço para crescer; os de share alto mostram "
               "o perfil de cliente que já compra — o ponto de partida para buscar empresas parecidas.")
    col_seg = "SEBRAE_setor" if "SEBRAE_setor" in df.columns else "SETOR"
    seg = tabela_share(df.assign(**{col_seg: df[col_seg].fillna("Não classificado")}), col_seg, minimo=20)
    st.dataframe(seg, use_container_width=True, column_config={
        "Share (já atendidas)": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
        "Share (ativas)": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
    })

    a, b = st.columns(2)
    with a:
        st.subheader("Share por porte")
        st.dataframe(tabela_share(df, "Porte"), use_container_width=True)
    with b:
        st.subheader("Share por município (maiores)")
        st.dataframe(tabela_share(df, "Municipio").head(15), use_container_width=True)

    if ARQ_ANOS.exists():
        st.divider()
        st.subheader("Empresas industriais atendidas por ano")
        anos = pd.read_csv(ARQ_ANOS)
        anos = anos[anos["industria_base"]].pivot_table(index="ano", columns="Entidade", values="empresas",
                                                        aggfunc="sum").fillna(0)
        st.bar_chart(anos)

    if ARQ_RANKING.exists():
        st.divider()
        st.subheader("Produtos mais vendidos")
        rk = pd.read_csv(ARQ_RANKING)
        so_ind = st.toggle("Só empresas da base industrial", value=True)
        if so_ind:
            rk = rk[rk["industria_base"]]
        top = (rk.groupby(["produto", "Entidade"])[["empresas", "empresas_recentes", "propostas", "valor"]].sum()
               .sort_values("empresas", ascending=False).reset_index())
        st.dataframe(top.rename(columns={"produto": "Produto", "empresas": "Empresas que compraram",
                                         "empresas_recentes": "Empresas (24 meses)", "propostas": "Propostas aceitas",
                                         "valor": "Valor aceito (R$)"}),
                     use_container_width=True, hide_index=True,
                     column_config={"Valor aceito (R$)": st.column_config.NumberColumn(format="R$ %.0f")})

    st.divider()
    st.subheader("Para reativar: empresas que já compraram e esfriaram")
    cols = [c for c in ["razao_social", "Municipio", "Porte", col_seg, "STATUS_RELACIONAMENTO_REAL",
                        "ULTIMA_COMPRA", "ULTIMA_COMPRA_SESI", "ULTIMA_COMPRA_SENAI"] if c in df.columns]
    inat = df[df["SITUACAO_CLIENTE"] == "Inativo"][cols].sort_values("ULTIMA_COMPRA", ascending=False)
    st.dataframe(inat, use_container_width=True, hide_index=True)
    st.download_button("⬇️ Baixar lista de reativação", inat.to_csv(index=False).encode("utf-8-sig"),
                       file_name="empresas_para_reativar.csv", mime="text/csv")
