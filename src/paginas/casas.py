"""Página "🏛️ SESI | SENAI" — cada casa com as suas linhas, já segmentada.

SESI: SSI e EB. SENAI: STI e EP. Para cada linha:
  * quantas empresas compram, pararam e têm oportunidade (Visão 360)
  * aderência estatística por segmento e porte, com intervalo de confiança
  * adesão por município e por natureza de produto
  * lista de oportunidades para trabalhar, filtrável por município
"""
from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from src.paginas.visao360 import carregar_360
from src.tools.visao360 import ARQ_NAT_MUN, carregar_linhas


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de confiança de 95% para uma proporção (funciona bem com grupos pequenos)."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, c - m), min(1.0, c + m)


def _n(x) -> str:
    return f"{int(x):,}".replace(",", ".")


def aderencia(df: pd.DataFrame, cod: str, por: list[str], minimo: int = 15) -> pd.DataFrame:
    comp = df[f"{cod}_status"].isin(["compra", "parou"])
    g = df.assign(_c=comp, _a=df[f"{cod}_status"].eq("compra"), _o=df[f"{cod}_status"].eq("oportunidade")) \
          .groupby(por).agg(Empresas=("_c", "size"), Ja_compraram=("_c", "sum"), Compram_hoje=("_a", "sum"),
                            Oportunidades=("_o", "sum"))
    g = g[g["Empresas"] >= minimo].copy()
    ic = [_wilson(int(k), int(n)) for k, n in zip(g["Ja_compraram"], g["Empresas"])]
    g["Aderência %"] = (g["Ja_compraram"] / g["Empresas"] * 100).round(1)
    g["IC 95%"] = [f"{lo*100:.0f}–{hi*100:.0f}%" for lo, hi in ic]
    return g.rename(columns={"Ja_compraram": "Já compraram", "Compram_hoje": "Compram hoje"}) \
            .sort_values("Oportunidades", ascending=False)


def render(df_empresas: pd.DataFrame) -> None:
    st.header("🏛️ SESI | SENAI")
    v = carregar_360()
    if v.empty:
        st.info("Rode `python jobs/atualizar_relacionamento.py --arquivo data/privado/propostas.xlsx` para gerar a Visão 360.")
        return
    cfg = carregar_linhas()
    casa = st.radio("Casa", ["SESI", "SENAI"], horizontal=True)
    linhas = {c: l for c, l in cfg["linhas"].items() if l["entidade"] == casa}

    base = df_empresas.copy()
    base["cnpj_basico"] = base["cnpj"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(14).str[:8]
    col_seg = "Segmento"
    base[col_seg] = base.get("SEBRAE_setor", base.get("SETOR", "")).fillna("Não classificado")
    partes = [base[["cnpj_basico", "razao_social", "Municipio", "Porte", col_seg]]]
    from src.tools.universo_ampliado import carregar_ampliada
    amp = carregar_ampliada()
    if not amp.empty:
        amp = amp.assign(**{col_seg: amp["CNAE PRIMARIO"].replace("", "Não classificado")})
        partes.append(amp[["cnpj_basico", "razao_social", "Municipio", "Porte", col_seg]])
    info = pd.concat(partes, ignore_index=True).drop_duplicates("cnpj_basico")
    df = info.merge(v, on="cnpj_basico", how="inner")
    if "tipo" not in df:
        df["tipo"] = "Indústria"
    universo = st.radio("Universo", ["Indústrias", "Não indústrias", "Todas"], horizontal=True, key="univ_casas")
    if universo == "Indústrias":
        df = df[df["tipo"].isin(["Indústria", "Indústria fora da Base Mestre"])]
    elif universo == "Não indústrias":
        df = df[df["tipo"] == "Não indústria"]
    muns = sorted(df["Municipio"].dropna().unique())
    mun = st.multiselect("Município", muns, placeholder="Todos os municípios")
    if mun:
        df = df[df["Municipio"].isin(mun)]
    st.caption(f"{_n(len(df))} empresas no recorte. ✅ compra = comprou nos últimos 24 meses · "
               "⏸️ parou = já comprou, mas antes · 🎯 oportunidade = empresas do mesmo CNAE e porte compram. "
               "Fonte: propostas aceitas desde 2018 (SESI no sistema a partir de 2024).")

    nat = pd.read_csv(ARQ_NAT_MUN, dtype={"municipio": str}) if ARQ_NAT_MUN.exists() else pd.DataFrame()
    for cod, aba in zip(linhas, st.tabs([f"{c} · {l['nome']}" for c, l in linhas.items()])):
        with aba:
            s = df[f"{cod}_status"]
            k = st.columns(4)
            k[0].metric("Compram hoje", _n((s == "compra").sum()))
            k[1].metric("Pararam", _n((s == "parou").sum()))
            k[2].metric("Oportunidades", _n((s == "oportunidade").sum()))
            k[3].metric("Penetração", f"{(s.isin(['compra', 'parou']).mean() * 100):.1f}%".replace(".", ","),
                        help="Empresas que já compraram a linha ÷ indústrias do recorte.")

            st.markdown("**Aderência por segmento e porte** — onde a linha já pega (e com que certeza)")
            st.dataframe(aderencia(df, cod, [col_seg, "Porte"]), use_container_width=True,
                         column_config={"Aderência %": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100)})

            a, b = st.columns(2)
            with a:
                st.markdown("**Por município**")
                st.dataframe(aderencia(df, cod, ["Municipio"], minimo=5).head(25), use_container_width=True)
            with b:
                st.markdown("**Natureza de produto × município** — quantas empresas aderiram")
                if nat.empty:
                    st.caption("Sem o agregado de naturezas (rode o atualizar_relacionamento).")
                else:
                    n = nat[nat["linha"] == cod]
                    if mun:
                        n = n[n["municipio"].isin(mun)]
                    piv = n.pivot_table(index="produto", columns="municipio", values="empresas", aggfunc="sum", fill_value=0)
                    top = piv.sum().sort_values(ascending=False).head(6).index
                    piv = piv[top].assign(Total=piv.sum(axis=1)).sort_values("Total", ascending=False)
                    st.dataframe(piv, use_container_width=True)

            st.markdown("**Para trabalhar:** oportunidades e quem parou")
            alvo = df[s.isin(["oportunidade", "parou"])].copy()
            alvo["Situação"] = alvo[f"{cod}_status"].map({"oportunidade": "🎯 oportunidade", "parou": "⏸️ parou"})
            alvo["% parecidas compram"] = pd.to_numeric(alvo[f"{cod}_pct"], errors="coerce")
            lista = alvo.sort_values("% parecidas compram", ascending=False)[
                ["Situação", "razao_social", "Municipio", "Porte", col_seg, "% parecidas compram", "linhas_ativas", f"{cod}_ultima"]] \
                .rename(columns={"razao_social": "Empresa", col_seg: "Segmento", "linhas_ativas": "Linhas ativas",
                                 f"{cod}_ultima": "Última compra da linha"})
            st.dataframe(lista, use_container_width=True, hide_index=True, height=380)
            st.download_button(f"⬇️ Baixar lista {cod}", lista.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"oportunidades_{cod}.csv", mime="text/csv", key=f"dl_{cod}")
