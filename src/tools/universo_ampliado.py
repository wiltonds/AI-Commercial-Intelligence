"""Junta, para o Explorador de Empresas, as indústrias da Base Mestre e as
não indústrias da Base Ampliada, com as mesmas colunas e a faixa de
colaboradores (quando conhecida pelo Porte FIEA)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.tools.receita_cnpj import ORDEM_FAIXA, carregar_porte_fiea, faixa_colaboradores

RAIZ = Path(__file__).resolve().parents[2]
ARQ_AMPLIADA = RAIZ / "data" / "processed" / "BASE_AMPLIADA_AL.csv"
ARQ_RELACIONAMENTO = RAIZ / "data" / "raw" / "BASE_CONSOLIDADA_SESI_SENAI.xlsx"
SEM_INFO = "Sem informação"


def _status(sesi: pd.Series, senai: pd.Series) -> pd.Series:
    s = pd.Series("Sem relacionamento", index=sesi.index)
    s[sesi & ~senai] = "Somente SESI"
    s[~sesi & senai] = "Somente SENAI"
    s[sesi & senai] = "SESI + SENAI"
    return s


def anotar_industrias(df: pd.DataFrame, fiea: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    raiz = out["cnpj"].astype(str).str.zfill(14).str[:8]
    porte = raiz.map(fiea.set_index("cnpj_basico")["porte_fiea"]) if not fiea.empty else pd.Series("", index=out.index)
    out["Tipo"] = "Indústria"
    out["Porte FIEA"] = porte.fillna("")
    out["Colaboradores (faixa)"] = [faixa_colaboradores("Indústria", p) or SEM_INFO for p in out["Porte FIEA"]]
    out["Origem colaboradores"] = out["Colaboradores (faixa)"].map(
        lambda f: SEM_INFO if f == SEM_INFO else "Porte FIEA (base de relacionamento)")
    return out


def carregar_ampliada(caminho: Path = ARQ_AMPLIADA) -> pd.DataFrame:
    if not Path(caminho).exists():
        return pd.DataFrame()
    df = pd.read_csv(caminho, dtype=str, encoding="utf-8-sig").fillna("")
    sesi = df["POSSUI_SESI"].str.upper().eq("TRUE")
    senai = df["POSSUI_SENAI"].str.upper().eq("TRUE")
    df["POSSUI_SESI"], df["POSSUI_SENAI"] = sesi, senai
    df["POSSUI_SESI_SENAI"] = sesi & senai
    df["STATUS_RELACIONAMENTO_REAL"] = _status(sesi, senai)
    df["STATUS_SEBRAE"] = ""
    df["Porte FIEA"] = df.pop("porte_fiea")
    df["Colaboradores (faixa)"] = df["Colaboradores (faixa)"].replace("", SEM_INFO)
    return df


def opcoes_faixa(serie: pd.Series) -> list[str]:
    presentes = set(serie.dropna())
    return [f for f in ORDEM_FAIXA if f in presentes] + ([SEM_INFO] if SEM_INFO in presentes else [])


ARQ_PORTE_PROPOSTAS = RAIZ / "data" / "processed" / "PORTE_FIEA.csv"


def porte_fiea(caminho: Path = ARQ_RELACIONAMENTO, propostas: Path = ARQ_PORTE_PROPOSTAS) -> pd.DataFrame:
    """Porte FIEA por CNPJ raiz: o das propostas (mais recente e mais amplo) tem
    prioridade; a planilha antiga de relacionamento completa o que faltar."""
    antigo = carregar_porte_fiea(caminho)
    if not Path(propostas).exists():
        return antigo
    novo = pd.read_csv(propostas, dtype=str).fillna("")
    novo = novo[novo["porte_fiea"] != ""]
    resto = antigo[~antigo["cnpj_basico"].isin(novo["cnpj_basico"])] if not antigo.empty else antigo
    return pd.concat([novo, resto[["cnpj_basico", "porte_fiea"]] if not resto.empty else resto], ignore_index=True)
