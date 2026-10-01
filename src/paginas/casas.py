"""Página "🏛️ SESI | SENAI" — feita para o vendedor, na ordem em que ele pensa.

Cada aba (SSI, EB, STI, EP) responde, de cima para baixo:
  1. Como estamos?         frase-resumo escrita a partir dos números
  2. Por onde começo?      clientes ativos · para reativar · para prospectar
  3. Onde focar?           os segmentos com mais empresas para prospectar
  4. Em que cidade?        os municípios com mais espaço
  5. O que oferecer?       os produtos que mais vendemos nessa linha
  6. Me dá a lista         reativar e prospectar, prontas para baixar

Sem jargão estatístico: "1 em cada 13 empresas desse perfil compra".
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.paginas.visao360 import carregar_360
from src.tools.visao360 import ARQ_NAT_MUN, carregar_linhas

PORTE_CURTO = {"MICRO EMPRESA": "micro", "PEQUENO PORTE": "pequeno porte", "DEMAIS": "médio e grande porte"}
MINIMO_GRUPO = 30   # abaixo disso o percentual oscila demais para orientar decisão


ACENTOS = {"Industria": "Indústria", "transformacao": "transformação", "Construcao": "Construção",
           "Comercio": "Comércio", "reparacao": "reparação", "veiculos": "veículos", "Informacao": "Informação",
           "comunicacao": "comunicação", "tecnicas": "técnicas", "alimentacao": "alimentação", "Agua": "Água",
           "gestao": "gestão", "residuos": "resíduos", "Eletricidade e gas": "Eletricidade e gás",
           "Atividades administrativas e servicos": "Atividades administrativas e serviços"}


def acentuar(texto: str) -> str:
    """Os nomes de setor vêm sem acento da base; na tela, com acento."""
    t = str(texto)
    for sem, com in ACENTOS.items():
        t = t.replace(sem, com)
    return t


def _n(x) -> str:
    return f"{int(x):,}".replace(",", ".")


def _pct(x: float) -> str:
    return f"{x:.1f}%".replace(".", ",")


def um_em(taxa: float) -> str:
    """0,075 -> '1 em cada 13'. Mais fácil de ler que 7,5%."""
    if taxa <= 0:
        return "nenhuma"
    if taxa >= 0.5:
        return f"{round(taxa * 10)} em cada 10"
    return f"1 em cada {max(2, round(1 / taxa))}"


def chance(pct: float) -> str:
    """Pelo perfil: quantas empresas parecidas já compram a linha."""
    if pct >= 30:
        return "Alta"
    if pct >= 15:
        return "Média"
    if pct >= 7:
        return "Boa"
    return "Menor"


def resumo(cod: str, nome: str, df: pd.DataFrame, focos: pd.DataFrame) -> str:
    s = df[f"{cod}_status"]
    ativos, parou = int((s == "compra").sum()), int((s == "parou").sum())
    cross, prosp = int((s == "cross").sum()), int((s == "prospectar").sum())
    frase = f"De **{_n(len(df))} empresas**, **{_n(ativos)} compram {cod} hoje**."
    if parou:
        frase += f" **{_n(parou)} pararam de comprar** — o caminho mais curto: comece por elas."
    if cross:
        frase += f" **{_n(cross)} já são clientes do Sistema** em outra linha, mas não de {cod} (cross-sell)."
    if prosp:
        frase += f" **{_n(prosp)} nunca compraram nada** do SESI ou do SENAI e são alvo de {cod}."
    if not focos.empty:
        f = focos.iloc[0]
        frase += f" Onde há mais espaço: **{f['Perfil']}**."
    return frase


def focos(df: pd.DataFrame, cod: str, col_seg: str) -> pd.DataFrame:
    s = df[f"{cod}_status"]
    g = df.assign(_ja=s.isin(["compra", "parou"]), _a=s.eq("compra"), _r=s.eq("parou"), _c=s.eq("cross"),
                  _p=s.eq("prospectar")) \
          .groupby([col_seg, "Porte"]).agg(Empresas=("_ja", "size"), ja=("_ja", "sum"), Ativos=("_a", "sum"),
                                           Reativar=("_r", "sum"), Cross=("_c", "sum"), Prospectar=("_p", "sum")).reset_index()
    g = g[(g["Prospectar"] + g["Reativar"] + g["Cross"]) > 0]
    g["Perfil"] = g[col_seg].map(acentuar) + \
        " · " + g["Porte"].map(PORTE_CURTO).fillna(g["Porte"].str.lower())
    g["Quem já compra"] = [um_em(j / n) + (" (poucas empresas)" if n < MINIMO_GRUPO else "")
                           for j, n in zip(g["ja"], g["Empresas"])]
    g["_espaco"] = g["Prospectar"] + g["Cross"] + g["Reativar"]
    g = g.sort_values("_espaco", ascending=False)
    return g.rename(columns={"Ativos": "Clientes ativos", "Reativar": "Para reativar", "Cross": "Cross-sell",
                             "Prospectar": "Para prospectar"}) \
            [["Perfil", "Empresas", "Clientes ativos", "Para reativar", "Cross-sell", "Para prospectar", "Quem já compra"]]


def por_municipio(df: pd.DataFrame, cod: str) -> pd.DataFrame:
    s = df[f"{cod}_status"]
    g = df.assign(_a=s.eq("compra"), _r=s.eq("parou"), _c=s.eq("cross"), _p=s.eq("prospectar")) \
          .groupby("Municipio").agg(Empresas=("_a", "size"), **{"Clientes ativos": ("_a", "sum"),
                                                                 "Para reativar": ("_r", "sum"),
                                                                 "Cross-sell": ("_c", "sum"),
                                                                 "Para prospectar": ("_p", "sum")})
    return g.sort_values(["Para prospectar", "Cross-sell"], ascending=False).reset_index() \
            .rename(columns={"Municipio": "Município"})


def render(df_empresas: pd.DataFrame) -> None:
    st.header("🏛️ SESI | SENAI")
    v = carregar_360()
    if v.empty:
        st.info("Os dados desta tela ainda não foram gerados. Rode "
                "`python jobs/atualizar_relacionamento.py --arquivo data/privado/propostas.xlsx` e publique.")
        return
    cfg = carregar_linhas()

    # ---- dados: indústrias + não indústrias, com a Visão 360
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
    df = pd.concat(partes, ignore_index=True).drop_duplicates("cnpj_basico").merge(v, on="cnpj_basico", how="inner")
    df[col_seg] = df[col_seg].map(acentuar)
    if "tipo" not in df:
        df["tipo"] = "Indústria"

    # ---- filtros numa linha só
    f1, f2, f3 = st.columns([1, 1.3, 2])
    casa = f1.radio("Casa", ["SESI", "SENAI"], horizontal=True)
    universo = f2.radio("Empresas", ["Indústrias", "Não indústrias", "Todas"], horizontal=True, key="univ_casas")
    muns = f3.multiselect("Município", sorted(df["Municipio"].dropna().unique()), placeholder="Todos os municípios")
    if universo == "Indústrias":
        df = df[df["tipo"].isin(["Indústria", "Indústria fora da Base Mestre"])]
    elif universo == "Não indústrias":
        df = df[df["tipo"] == "Não indústria"]
    if muns:
        df = df[df["Municipio"].isin(muns)]

    with st.expander("Como ler esta tela"):
        st.markdown(
            "- **Cliente ativo:** comprou esta linha nos últimos 24 meses.\n"
            "- **Para reativar:** já comprou esta linha, mas não compra há mais de 24 meses.\n"
            "- **Cross-sell:** já compra outra coisa do SESI ou do SENAI, mas não esta linha.\n"
            "- **Para prospectar:** nunca comprou nada do SESI nem do SENAI.\n"
            "- **Quem entra como alvo:** SSI = todas as empresas (obrigação legal, NR-1 e NR-7); "
            "EP = médias e grandes (cota de aprendizagem) e as de perfil parecido; STI e EB = perfil parecido "
            "(pelo menos 1 em cada 10 empresas do mesmo ramo e porte compram).\n"
            "- **Chance:** quantas empresas parecidas já compram a linha. Alta = 3 ou mais em cada 10; "
            "Média = de 1,5 a 3 em 10; Boa = de 0,7 a 1,5 em 10; Menor = menos que isso (comum em SSI, "
            "que entra pela obrigação legal e não pelo perfil).\n\n"
            "Fonte: propostas aceitas desde 2018. O SESI entrou no sistema de propostas em 2024, então compras "
            "SESI anteriores não aparecem.")

    nat = pd.read_csv(ARQ_NAT_MUN, dtype={"municipio": str}) if ARQ_NAT_MUN.exists() else pd.DataFrame()
    linhas = {c: l for c, l in cfg["linhas"].items() if l["entidade"] == casa}
    for cod, aba in zip(linhas, st.tabs([f"{c} · {l['nome']}" for c, l in linhas.items()])):
        with aba:
            s = df[f"{cod}_status"]
            fx = focos(df, cod, col_seg)

            # 1. Como estamos?
            st.info(resumo(cod, linhas[cod]["nome"], df, fx), icon="💡")

            # 2. Por onde começo?
            k = st.columns(4)
            k[0].metric("✅ Clientes ativos", _n((s == "compra").sum()), help="Compraram esta linha nos últimos 24 meses.")
            k[1].metric("⏸️ Para reativar", _n((s == "parou").sum()), help="Já compraram, mas pararam há mais de 24 meses.")
            k[2].metric("🔄 Cross-sell", _n((s == "cross").sum()),
                        help="Já compram outra coisa do SESI ou do SENAI, mas não esta linha.")
            k[3].metric("🎯 Para prospectar", _n((s == "prospectar").sum()),
                        help="Nunca compraram nada do SESI nem do SENAI, e são alvo desta linha.")

            # 3. Onde focar?
            st.subheader("Onde focar")
            st.caption("Perfis de empresa com mais espaço para vender, do maior para o menor.")
            st.dataframe(fx.head(10), use_container_width=True, hide_index=True)

            # 4. Em que cidade? · 5. O que oferecer?
            a, b = st.columns(2)
            with a:
                st.subheader("Em que cidade")
                st.dataframe(por_municipio(df, cod).head(10), use_container_width=True, hide_index=True)
            with b:
                st.subheader("O que mais vendemos")
                if nat.empty:
                    st.caption("Sem dados de produtos ainda.")
                else:
                    n = nat[nat["linha"] == cod]
                    if muns:
                        n = n[n["municipio"].isin(muns)]
                    prod = n.groupby("produto")[["empresas", "empresas_24m"]].sum().sort_values("empresas", ascending=False)
                    st.dataframe(prod.reset_index().rename(columns={"produto": "Produto", "empresas": "Empresas que compraram",
                                                                    "empresas_24m": "Nos últimos 24 meses"}),
                                 use_container_width=True, hide_index=True)

            # 6. Me dá a lista
            st.subheader("Listas prontas")
            base_lista = df.assign(pct=pd.to_numeric(df[f"{cod}_pct"], errors="coerce").fillna(0))
            colunas = {"razao_social": "Empresa", "Municipio": "Município", "Porte": "Porte", col_seg: "Segmento"}
            t1, t2, t3 = st.tabs([f"⏸️ Para reativar ({_n((s == 'parou').sum())})",
                                  f"🔄 Cross-sell ({_n((s == 'cross').sum())})",
                                  f"🎯 Para prospectar ({_n((s == 'prospectar').sum())})"])
            with t1:
                r = base_lista[s == "parou"].sort_values(f"{cod}_ultima", ascending=False)
                r = r[list(colunas) + [f"{cod}_ultima"]].rename(columns={**colunas, f"{cod}_ultima": "Última compra"})
                st.dataframe(r, use_container_width=True, hide_index=True, height=320)
                st.download_button("⬇️ Baixar lista para reativar", r.to_csv(index=False).encode("utf-8-sig"),
                                   file_name=f"{cod}_reativar.csv", mime="text/csv", key=f"r_{cod}")
            for aba_, estado, rotulo in ((t2, "cross", "cross-sell"), (t3, "prospectar", "prospectar")):
                with aba_:
                    p = base_lista[s == estado].sort_values("pct", ascending=False)
                    p["Chance"] = p["pct"].map(chance)
                    p["Motivo"] = p[f"{cod}_motivo"].replace("", "Perfil parecido com quem compra")
                    p["Quem já compra"] = p["pct"].map(lambda x: f"{um_em(x / 100)} parecidas")
                    if estado == "cross":
                        p["Já compra"] = p["linhas_ativas"].astype(str) + " linha(s)"
                    cols_ = ["Chance"] + list(colunas) + ["Motivo", "Quem já compra"] + (["Já compra"] if estado == "cross" else [])
                    p = p[cols_].rename(columns=colunas)
                    st.dataframe(p, use_container_width=True, hide_index=True, height=320)
                    st.download_button(f"⬇️ Baixar lista de {rotulo}", p.to_csv(index=False).encode("utf-8-sig"),
                                       file_name=f"{cod}_{estado}.csv", mime="text/csv", key=f"{estado}_{cod}")
