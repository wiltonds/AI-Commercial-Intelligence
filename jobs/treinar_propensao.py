"""
treinar_propensao.py — Nota de propensão (lookalike) por negócio para todas as empresas de AL.

Roda na máquina LOCAL (lê data/privado/BASE_HISTORICA_SESI_SENAI.xlsx, que não vai
para o Git). Publica só números derivados:

  data/processed/PROPENSAO.csv            por CNPJ raiz: fit_SSI..fit_EB (0-100), se já compra,
                                          nº de clientes da mesma classe/grupo CNAE
  data/processed/PROPENSAO_VALIDACAO.csv  backtest (treina até o corte, mede compradores
                                          novos depois) e ticket médio por negócio

Uso:
    python jobs/treinar_propensao.py
    python jobs/treinar_propensao.py --corte 2026-07-01      # data do backtest
Depois: jobs/publicar_dados.ps1 (ou git add dos dois arquivos).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.sinais.propensao import (NEGOCIOS, ajustar_e_pontuar, avaliar_backtest, carregar_vendas,  # noqa: E402
                                  matriz, montar_universo)

P = RAIZ / "data" / "processed"
VENDAS = RAIZ / "data" / "privado" / "BASE_HISTORICA_SESI_SENAI.xlsx"


def compradores(vendas, v360, ate=None, desde=None) -> dict[str, set]:
    out = {}
    for n in NEGOCIOS:
        h = vendas[vendas["negocio"] == n]
        s = v360[v360[f"{n}_status"].isin(["compra", "parou"])]
        d = pd.to_datetime(s[f"{n}_ultima"], errors="coerce")
        if ate is not None:
            h, s = h[h["data"] < ate], s[d < ate]
        if desde is not None:
            h, s = h[h["data"] >= desde], s[d >= desde]
        out[n] = set(h["cnpj_basico"]) | set(s["cnpj_basico"])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corte", default="2026-07-01")
    a = ap.parse_args()
    if not VENDAS.exists():
        sys.exit(f"Falta {VENDAS.relative_to(RAIZ)} (export da Base Histórica SESI e SENAI).")

    vendas = carregar_vendas(VENDAS)
    v360 = pd.read_csv(P / "VISAO_360.csv", dtype=str, encoding="utf-8-sig")
    u = montar_universo(pd.read_csv(P / "BASE_MESTRE_COMERCIAL.csv", dtype=str, low_memory=False, encoding="utf-8-sig"),
                        pd.read_csv(P / "BASE_AMPLIADA_AL.csv", dtype=str, encoding="utf-8-sig"))
    print(f"Universo: {len(u):,} empresas".replace(",", "."))

    # 1) backtest honesto
    corte = pd.Timestamp(a.corte)
    antes, depois = compradores(vendas, v360, ate=corte), compradores(vendas, v360, desde=corte)
    x_corte = matriz(u, corte, antes)
    qualquer = set().union(*antes.values())
    val = []
    for n in NEGOCIOS:
        r = avaliar_backtest(u, x_corte, antes[n], depois[n], n)
        r["grupo"] = "compradores novos do negócio"
        val.append(r)
        r = avaliar_backtest(u, x_corte, antes[n], (depois[n] - qualquer) | antes[n], n)
        r["grupo"] = "sem compra anterior em nenhum negócio"
        val.append(r)
    val = pd.DataFrame(val)
    val["corte"] = a.corte
    # ticket médio por empresa compradora (propostas aceitas da Base Histórica)
    t = vendas.groupby(["negocio", "cnpj_basico"])["valor"].sum().groupby("negocio").agg(["mean", "median", "count"])
    val = val.merge(t.rename(columns={"mean": "ticket_medio", "median": "ticket_mediano", "count": "empresas_compradoras"}),
                    left_on="negocio", right_index=True, how="left")
    val.to_csv(P / "PROPENSAO_VALIDACAO.csv", index=False, encoding="utf-8-sig")
    print(val[["negocio", "grupo", "novos", "auc", "top5_captura", "top10_captura"]].to_string(index=False))

    # 2) modelo final com tudo o que se sabe até hoje
    hoje = pd.Timestamp.today().normalize()
    todos = compradores(vendas, v360)
    x = matriz(u, hoje, todos)
    out = pd.DataFrame({"cnpj_basico": u["cnpj_basico"]})
    for n in NEGOCIOS:
        p = ajustar_e_pontuar(u, x, todos[n], n)
        out[f"fit_{n}"] = np.floor(pd.Series(p).rank(pct=True) * 100).clip(0, 100).astype(int).to_numpy()
        out[f"compra_{n}"] = u["cnpj_basico"].isin(todos[n]).astype(int).to_numpy()
        comp = u[u["cnpj_basico"].isin(todos[n])]
        out[f"clientes_classe_{n}"] = u["cnae"].str[:5].map(comp["cnae"].str[:5].value_counts()).fillna(0).astype(int).to_numpy()
        out[f"clientes_grupo_{n}"] = u["cnae"].str[:3].map(comp["cnae"].str[:3].value_counts()).fillna(0).astype(int).to_numpy()
    out.to_csv(P / "PROPENSAO.csv", index=False, encoding="utf-8-sig")
    print(f"Pronto: PROPENSAO.csv ({len(out):,} empresas) e PROPENSAO_VALIDACAO.csv".replace(",", "."))


if __name__ == "__main__":
    main()
