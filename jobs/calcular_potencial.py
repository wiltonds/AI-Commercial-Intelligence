"""Calcula o potencial das empresas sem relacionamento e grava data/processed/POTENCIAL_MERCADO.csv.

    python jobs/calcular_potencial.py

Lê a Base Mestre (indústrias), a Base Ampliada (não indústrias) e, se existir,
data/contatos/ENDERECOS_AL.csv (capital, natureza e bairro das indústrias). Rodar
depois de atualizar o relacionamento (propostas), porque o alvo do modelo é "já comprou".

Saída pública (só dado de empresa): cnpj_basico, bairro (endereço em AL: matriz, ou a filial quando a matriz é de fora), nota, potencial, motivo, alerta.
O bairro só sai para empresa que não é Empresário Individual (endereço de pessoa física fica fora).
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src.tools.potencial import grupo_natureza, numero_br, pontuar, segmento_cnae  # noqa: E402

ARQ_MESTRE = RAIZ / "data" / "processed" / "BASE_MESTRE_COMERCIAL.csv"
ARQ_AMPLIADA = RAIZ / "data" / "processed" / "BASE_AMPLIADA_AL.csv"
ARQ_ENDERECOS = RAIZ / "data" / "contatos" / "ENDERECOS_AL.csv"
ARQ_SAIDA = RAIZ / "data" / "processed" / "POTENCIAL_MERCADO.csv"


def ler_enderecos(caminho: Path = ARQ_ENDERECOS) -> pd.DataFrame:
    """Por CNPJ raiz: capital, natureza, se há matriz em AL e o bairro da matriz."""
    if not caminho.exists():
        return pd.DataFrame(columns=["cnpj_basico", "capital_e", "natureza_e", "matriz_al", "bairro"])
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        amostra = f.read(4096)
    sep = ";" if amostra.count(";") > amostra.count(",") else ","
    e = pd.read_csv(caminho, dtype=str, sep=sep, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL,
                    on_bad_lines="skip").fillna("")
    e["cnpj_basico"] = e.get("cnpj_basico", e["cnpj"].str[:8]).str.zfill(8)
    e["_matriz"] = e.get("matriz", pd.Series("", index=e.index)).str.upper().isin(["S", "1", "MATRIZ", "TRUE"]) \
        | e["cnpj"].str.zfill(14).str[8:12].eq("0001")
    e = e.sort_values("_matriz", ascending=False)
    g = e.groupby("cnpj_basico")
    out = pd.DataFrame({
        "capital_e": g["capital_social"].first().map(numero_br) if "capital_social" in e else None,
        "natureza_e": g["natureza_juridica"].first() if "natureza_juridica" in e else "",
        "matriz_al": g["_matriz"].any(),
        "bairro": g["bairro"].first().str.strip().str.title() if "bairro" in e else "",
    }).reset_index()
    return out


def universo() -> pd.DataFrame:
    m = pd.read_csv(ARQ_MESTRE, dtype=str, encoding="utf-8-sig", low_memory=False).fillna("")
    m["cnpj"] = m["cnpj"].str.replace(r"\D", "", regex=True).str.zfill(14)
    m["_cli"] = m["SITUACAO_CLIENTE"].isin(["Ativo", "Inativo"])
    m["_matriz"] = m["cnpj"].str[8:12].eq("0001")
    # código CNAE: a coluna CNAE_DIVISAO da Base Mestre vem errada em parte das linhas
    # (ex.: 4520-0/01 com divisão 10); o código recuperado é o confiável.
    m["_cnae"] = (pd.to_numeric(m.get("SEBRAE_cnae_norm", ""), errors="coerce")
                  .map(lambda v: f"{int(v):07d}" if pd.notna(v) else ""))
    g = m.sort_values("_matriz", ascending=False).groupby("CNPJ_BASICO")
    ind = pd.DataFrame({
        "razao_social": g["razao_social"].first(),
        "cnae": g["_cnae"].first(),
        "Porte Receita": g["Porte"].first(),
        "Município": g["Municipio"].first(),
        "n_estab": g.size(),
        "cliente": g["_cli"].any(),
        "matriz_base": g["_matriz"].any(),
    }).reset_index().rename(columns={"CNPJ_BASICO": "cnpj_basico"})
    ind["divisao"] = ind["cnae"].str[:2]
    ind["Categoria"] = "Indústria"
    ind["capital"], ind["natureza"], ind["data_abertura"] = float("nan"), "", ""

    a = pd.read_csv(ARQ_AMPLIADA, dtype=str, encoding="utf-8-sig").fillna("")
    nao = pd.DataFrame({
        "cnpj_basico": a["cnpj_basico"].str.zfill(8),
        "razao_social": a["razao_social"],
        "divisao": a["cnae_principal"].str.zfill(7).str[:2],
        "cnae": a["cnae_principal"].str.zfill(7),
        "Porte Receita": a["Porte"],
        "Município": a["Municipio"],
        "n_estab": pd.to_numeric(a["QTD_ESTABELECIMENTOS"], errors="coerce"),
        "cliente": a["SITUACAO_CLIENTE"].isin(["Ativo", "Inativo"]),
        "matriz_base": a["cnpj"].str.zfill(14).str[8:12].eq("0001"),
        "capital": a["capital_social"].map(numero_br),
        "natureza": a["natureza"],
        "data_abertura": a["data_inicio_atividade"],
    })
    nao["Categoria"] = "Não indústria"
    u = pd.concat([ind, nao], ignore_index=True).drop_duplicates("cnpj_basico")

    e = ler_enderecos()
    u = u.merge(e, on="cnpj_basico", how="left")
    u["capital"] = u["capital"].fillna(u["capital_e"])
    u["natureza"] = u["natureza"].where(u["natureza"] != "", u["natureza_e"].fillna(""))
    u["sede_em_al"] = u["matriz_base"] | u["matriz_al"].fillna(False).astype(bool)
    u["natureza_grupo"] = u["natureza"].map(grupo_natureza)
    u["Segmento"] = u["divisao"].map(segmento_cnae)
    individual = u["natureza"].str.contains("Individual", na=False)
    u["bairro"] = u["bairro"].fillna("").where(~individual, "")
    return u


def main() -> None:
    u = universo()
    out, auc = pontuar(u)
    out = out.merge(u[["cnpj_basico", "bairro"]], on="cnpj_basico", how="left")
    out = out[["cnpj_basico", "bairro", "nota", "potencial", "motivo", "alerta"]]
    ARQ_SAIDA.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(ARQ_SAIDA, index=False, encoding="utf-8-sig")
    sem = out[out["potencial"] != ""]
    print(f"Empresas: {len(out):,} · sem relacionamento: {len(sem):,} · AUC (validação): {auc:.3f}")
    print(sem["potencial"].value_counts().reindex(["Muito alto", "Alto", "Médio", "Baixo"]).to_string())
    print(f"Com alerta: {(sem['alerta'] != '').sum():,}  ·  com bairro: {(out['bairro'] != '').sum():,}")
    print(f"Gravado: {ARQ_SAIDA}")


if __name__ == "__main__":
    main()
