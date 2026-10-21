"""Porte em 4 classes para exibição: MICRO, PEQUENA, MÉDIA, GRANDE.

A Receita só tem 3 portes (MICRO EMPRESA, PEQUENO PORTE, DEMAIS) e "DEMAIS"
mistura média e grande. A FIEA classifica por número de colaboradores
(critério SEBRAE/IBGE para indústria). Ordem de prioridade:

1. Porte FIEA do cadastro (PORTE_FIEA.csv), quando a empresa já tem relacionamento;
2. colaboradores (real da Solução 360 ou faixa estimada por ML, COLABORADORES.csv);
3. rótulo de porte que já vem no dado (BNDES traz GRANDE/MÉDIA/PEQUENA/MICRO);
4. "DEMAIS" sem nenhuma informação acima → MÉDIA (menor classe possível para DEMAIS).

Só muda a exibição. Os coletores e o modelo continuam usando o porte da Receita.
"""
from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
P = RAIZ / "data" / "processed"

MICRO, PEQUENA, MEDIA, GRANDE = "MICRO", "PEQUENA", "MÉDIA", "GRANDE"
ORDEM = [MICRO, PEQUENA, MEDIA, GRANDE]
# Indústria (SEBRAE/IBGE): micro até 19, pequena 20–99, média 100–499, grande 500+.
LIMITES = [(19, MICRO), (99, PEQUENA), (499, MEDIA)]


def _norm(v) -> str:
    s = "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper().strip()
    return s.lstrip("1234567890. ").strip()


_TEXTO = {
    "MICRO": MICRO, "MICRO EMPRESA": MICRO, "MICROEMPRESA": MICRO, "ME": MICRO,
    "PEQUENA": PEQUENA, "PEQUENO": PEQUENA, "PEQUENO PORTE": PEQUENA, "EPP": PEQUENA,
    "EMPRESA DE PEQUENO PORTE": PEQUENA, "PEQUENA EMPRESA": PEQUENA,
    "MEDIA": MEDIA, "MEDIO": MEDIA, "MEDIA EMPRESA": MEDIA,
    "GRANDE": GRANDE, "GRANDE EMPRESA": GRANDE,
}


def de_texto(v) -> str:
    """Rótulo conhecido → classe. 'DEMAIS' e vazio → '' (não dá para saber)."""
    return _TEXTO.get(_norm(v), "")


def de_colaboradores(n) -> str:
    if n is None or pd.isna(n):
        return ""
    for teto, nome in LIMITES:
        if n <= teto:
            return nome
    return GRANDE


@lru_cache(maxsize=1)
def _referencias() -> tuple[dict, dict]:
    fiea, colab = {}, {}
    arq = P / "PORTE_FIEA.csv"
    if arq.exists():
        f = pd.read_csv(arq, dtype={"cnpj_basico": str}, encoding="utf-8-sig")
        f["cnpj_basico"] = f["cnpj_basico"].str.zfill(8)
        fiea = dict(zip(f["cnpj_basico"], f["porte_fiea"].map(de_texto)))
    arq = P / "COLABORADORES.csv"
    if arq.exists():
        c = pd.read_csv(arq, dtype={"cnpj_basico": str}, encoding="utf-8-sig")
        c["cnpj_basico"] = c["cnpj_basico"].str.zfill(8)
        meio = (pd.to_numeric(c["colab_min"], errors="coerce") + pd.to_numeric(c["colab_max"], errors="coerce")) / 2
        n = pd.to_numeric(c["colaboradores"], errors="coerce").fillna(meio)
        colab = dict(zip(c["cnpj_basico"], n.map(de_colaboradores)))
    return fiea, colab


def padronizar(cnpj_basico: pd.Series, porte: pd.Series) -> pd.Series:
    """Uma classe entre MICRO, PEQUENA, MÉDIA e GRANDE por empresa ('' só se não houver porte nenhum)."""
    fiea, colab = _referencias()
    raiz = cnpj_basico.fillna("").astype(str).str.replace(r"\D", "", regex=True).str[:8].str.zfill(8)
    out = []
    for r, p in zip(raiz, porte):
        c = fiea.get(r) or colab.get(r) or de_texto(p)
        if not c and _norm(p) == "DEMAIS":
            c = MEDIA
        out.append(c)
    return pd.Series(out, index=porte.index, dtype=object)


def opcoes(s: pd.Series) -> list[str]:
    """Classes presentes, na ordem MICRO → GRANDE (para filtros)."""
    tem = set(s.dropna().astype(str))
    return [p for p in ORDEM if p in tem]
