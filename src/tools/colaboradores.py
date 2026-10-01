"""Número de colaboradores por empresa.

Fonte real: exportação de empresas da Solução 360 (aba com CNPJ e contagem de
colaboradores por estabelecimento). Para a empresa (CNPJ raiz), soma as
unidades que aparecem na exportação.

Para quem não está na exportação: estimativa por regressão quantílica
(gradient boosting) treinada nas empresas com número real, a partir de porte
da Receita, CNAE, município e número de unidades. Mostra um INTERVALO (quantis
20%–80%), não um número: em validação cruzada, o real cai dentro dele em ~7 de
cada 10 empresas. Precisão menor que o dado real, e o painel deixa isso claro.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
ARQ_PUBLICO = RAIZ / "data" / "processed" / "COLABORADORES.csv"
ARQ_EXATO = RAIZ / "data" / "privado" / "COLABORADORES_EXATO.csv"
FAIXAS = [(0, 9, "até 9"), (10, 19, "10 a 19"), (20, 49, "20 a 49"), (50, 99, "50 a 99"),
          (100, 249, "100 a 249"), (250, 499, "250 a 499"), (500, 999, "500 a 999"), (1000, 10**9, "1.000 ou mais")]


def faixa(n: float) -> str:
    if pd.isna(n):
        return ""
    for lo, hi, nome in FAIXAS:
        if lo <= n <= hi:
            return nome
    return ""


def arredondar(v: float, para_cima: bool) -> int:
    """Números redondos, mais fáceis de ler: 3, 8, 25, 40, 150, 300."""
    v = max(v, 1)
    passo = 1 if v < 20 else 5 if v < 100 else 10 if v < 500 else 50
    f = math.ceil if para_cima else math.floor
    return max(1, int(f(v / passo) * passo))


def ler_exportacao(caminho: Path) -> pd.DataFrame:
    """Aba da Solução 360 com CNPJ e contagem de colaboradores (procura a aba certa)."""
    x = pd.ExcelFile(caminho)
    for aba in x.sheet_names:
        d = x.parse(aba, dtype=str)
        cols = {c.lower().strip(): c for c in d.columns}
        cnpj = cols.get("cnpj")
        num = cols.get("contagem") or cols.get("colaboradores")
        if cnpj and num and len(d.columns) <= 3:
            out = pd.DataFrame({"cnpj": d[cnpj].str.replace(r"\D", "", regex=True).str.zfill(14),
                                "colaboradores": pd.to_numeric(d[num], errors="coerce")})
            return out.dropna().drop_duplicates("cnpj")
    raise ValueError("Não achei uma aba com as colunas CNPJ e Contagem (ou Colaboradores).")


def _features(u: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "porte": u["porte"].map({"MICRO EMPRESA": 0, "PEQUENO PORTE": 1, "DEMAIS": 2}).fillna(0).values,
        "div": pd.to_numeric(u["div"], errors="coerce").fillna(0).values,
        "classe": pd.to_numeric(u["classe"], errors="coerce").fillna(0).values,
        "unidades": pd.to_numeric(u["unidades"], errors="coerce").fillna(1).values,
        "maceio": u["municipio"].astype(str).str.upper().str.startswith("MACEI").astype(int).values,
    })


def calcular(universo: pd.DataFrame, real_por_cnpj: pd.DataFrame) -> pd.DataFrame:
    """universo: uma linha por empresa (cnpj_basico, porte, div, classe, unidades, municipio)
    + lista de CNPJs (14) de cada empresa em 'cnpjs'. Devolve número real ou intervalo estimado."""
    from sklearn.ensemble import HistGradientBoostingRegressor as H
    r = real_por_cnpj.assign(cnpj_basico=real_por_cnpj["cnpj"].str[:8]).groupby("cnpj_basico")["colaboradores"].sum()
    u = universo.copy()
    u["real"] = u["cnpj_basico"].map(r)
    X = _features(u)
    tem = u["real"].notna().values
    out = pd.DataFrame({"cnpj_basico": u["cnpj_basico"].values})
    out["colaboradores"] = u["real"].values
    out["origem_colaboradores"] = np.where(tem, "Solução 360", "")
    out["colab_min"], out["colab_max"] = np.nan, np.nan
    if tem.sum() >= 50 and (~tem).any():
        y = np.log1p(u.loc[tem, "real"].values)
        prev = {}
        for q in (0.2, 0.8):
            m = H(loss="quantile", quantile=q, max_depth=4, max_iter=300, learning_rate=0.05, random_state=1)
            prev[q] = np.expm1(m.fit(X[tem], y).predict(X[~tem]))
        lo = [arredondar(v, False) for v in prev[0.2]]
        hi = [max(a + 1, arredondar(v, True)) for a, v in zip(lo, prev[0.8])]
        out.loc[~tem, "colab_min"], out.loc[~tem, "colab_max"] = lo, hi
        out.loc[~tem, "origem_colaboradores"] = "Estimado"
    out["faixa_colaboradores"] = [faixa(n) for n in out["colaboradores"]]
    est = out["origem_colaboradores"] == "Estimado"
    out.loc[est, "faixa_colaboradores"] = [f"entre {int(a)} e {int(b)}" for a, b in
                                           zip(out.loc[est, "colab_min"], out.loc[est, "colab_max"])]
    return out


def texto(linha: dict, exato: bool) -> str:
    """O que aparece na tela: '25' / '20 a 49' (real, sem o exato) / 'entre 4 e 30 (estimado)'."""
    origem = linha.get("origem_colaboradores", "")
    if origem == "Solução 360":
        n = linha.get("colaboradores")
        return f"{int(float(n))}" if exato and n not in ("", None) and not pd.isna(n) else str(linha.get("faixa_colaboradores", ""))
    if origem == "Estimado":
        return f"{linha.get('faixa_colaboradores', '')} (estimado)"
    return ""


def carregar_para_painel() -> pd.DataFrame:
    """Faixa pública + número exato quando o arquivo local existir. Coluna 'Colaboradores' pronta."""
    if not ARQ_PUBLICO.exists():
        return pd.DataFrame(columns=["cnpj_basico", "Colaboradores", "Origem colaboradores"])
    pub = pd.read_csv(ARQ_PUBLICO, dtype=str, encoding="utf-8-sig").fillna("")
    exato = ARQ_EXATO.exists()
    if exato:
        ex = pd.read_csv(ARQ_EXATO, dtype=str, encoding="utf-8-sig").fillna("").set_index("cnpj_basico")["colaboradores"]
        pub["colaboradores"] = pub["cnpj_basico"].map(ex).fillna(pub.get("colaboradores", ""))
    pub["Colaboradores"] = [texto(r, exato or "colaboradores" in pub.columns) for r in pub.to_dict("records")]
    pub["Origem colaboradores"] = pub["origem_colaboradores"].map(
        {"Solução 360": "Solução 360", "Estimado": "Estimado (7 em 10 acertam a faixa)"}).fillna("")
    return pub[["cnpj_basico", "Colaboradores", "Origem colaboradores"]]
