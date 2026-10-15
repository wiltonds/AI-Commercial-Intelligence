"""Dado pessoal fora dos arquivos públicos (o repositório é público).

A Receita grava a razão social do Empresário Individual como "NOME DA PESSOA 12345678900":
o CPF vai junto. Os jobs que gravam arquivos em data/processed/ passam por limpar_cpf()
antes do to_csv. O nome fica (é o nome da empresa); o número sai.
"""
from __future__ import annotations

import re

import pandas as pd

RE_CPF = re.compile(r"\s*(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
COLUNAS_NOME = ("razao_social", "nome_fantasia", "SEBRAE_razao_social", "Razão social", "Razão Social")


def sem_cpf(texto) -> str:
    """'ABEL SERAFIM DA SILVA 02265288470' -> 'ABEL SERAFIM DA SILVA'. CNPJ (14 dígitos) não é tocado."""
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return texto
    return RE_CPF.sub("", str(texto)).strip()


def limpar_cpf(df: pd.DataFrame) -> pd.DataFrame:
    """Tira CPF das colunas de nome que existirem no DataFrame (devolve uma cópia)."""
    out = df.copy()
    for c in COLUNAS_NOME:
        if c in out.columns:
            out[c] = out[c].map(sem_cpf)
    return out
