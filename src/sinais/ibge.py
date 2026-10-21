"""Indicadores econômicos dos municípios de AL (IBGE / SIDRA, API pública e grátis).

Dá o "tamanho do mercado" de cada município para cruzar com a nossa base:
onde a indústria pesa na economia e quanto dela já atendemos.

Tabelas usadas (https://apisidra.ibge.gov.br):
  5938  PIB dos municípios — v37 PIB, v517 VAB da indústria, v520 participação da indústria no VAB
  6579  Estimativa de população — v9324 população residente estimada
"""
from __future__ import annotations

import pandas as pd

from src.tools.municipios import padronizar

API = "https://apisidra.ibge.gov.br/values/t/{t}/n6/in%20n3%2027/v/{v}/p/last%203"
# últimos 3 anos: o IBGE publica o PIB total antes do detalhe por setor (VAB),
# então para cada indicador fica o ano mais recente que tem valor.
CONSULTAS = {
    "pib_mil": (5938, 37),
    "vab_industria_mil": (5938, 517),
    "part_industria_vab": (5938, 520),
    "populacao": (6579, 9324),
}


def ler_sidra(json_lista: list[dict], nome: str) -> pd.DataFrame:
    """A primeira linha da SIDRA é o cabeçalho; as demais, um município cada."""
    linhas = json_lista[1:]
    df = pd.DataFrame(linhas)
    if df.empty:
        return pd.DataFrame(columns=["cod_ibge", "municipio", nome, f"ano_{nome}"])
    valor = pd.to_numeric(df["V"].replace({"-": None, "...": None, "X": None}), errors="coerce")
    # a coluna do ano é a que o cabeçalho chama de "Ano" (com classificação, o produto vem depois)
    cab = json_lista[0] if json_lista else {}
    ano_col = next((k for k, v in cab.items() if k.startswith("D") and k.endswith("N")
                    and str(v).strip().lower().startswith("ano")), "D3N")
    out = pd.DataFrame({
        "cod_ibge": df["D1C"],
        "municipio": padronizar(df["D1N"].str.replace(r"\s*-\s*AL$", "", regex=True)),
        nome: valor,
        f"ano_{nome}": df[ano_col],
    })
    out = out.dropna(subset=[nome]).sort_values(f"ano_{nome}", ascending=False)
    return out.drop_duplicates("cod_ibge").reset_index(drop=True)


def baixar_indicadores(sessao=None) -> pd.DataFrame:
    import requests

    sessao = sessao or requests.Session()
    out = None
    for nome, (tabela, variavel) in CONSULTAS.items():
        r = sessao.get(API.format(t=tabela, v=variavel), timeout=60)
        r.raise_for_status()
        parte = ler_sidra(r.json(), nome)
        out = parte if out is None else out.merge(parte.drop(columns="municipio"), on="cod_ibge", how="outer")
    return out.sort_values("municipio").reset_index(drop=True)
