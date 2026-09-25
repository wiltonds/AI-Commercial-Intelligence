"""Camada genérica de sinais: junta todas as fontes, marca novidades e
sugere a oferta.

Cada job grava data/processed/SINAIS_<FONTE>.csv com o mesmo núcleo de
colunas (tipo_sinal, cnpj_basico, razao_social, descricao, municipio,
data_evento, data_publicacao, score_momento, ...). Esta camada não sabe
de onde veio cada sinal — por isso uma fonte nova aparece na tela sem
mexer na página.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import yaml

RAIZ = Path(__file__).resolve().parents[2]
PASTA_SINAIS = RAIZ / "data" / "processed"
ARQ_OFERTAS = RAIZ / "config" / "ofertas.yaml"

NOVIDADE_DIAS_PADRAO = 7


def carregar_ofertas(caminho: Path = ARQ_OFERTAS) -> dict:
    with open(caminho, encoding="utf-8") as f:
        return yaml.safe_load(f)


def carregar_todos_sinais(pasta: Path = PASTA_SINAIS) -> pd.DataFrame:
    partes = []
    for arquivo in sorted(pasta.glob("SINAIS_*.csv")):
        df = pd.read_csv(arquivo, dtype={"cnpj": str, "cnpj_basico": str, "cno": str,
                                         "qualificacao": str}, encoding="utf-8-sig")
        df["origem_arquivo"] = arquivo.name
        partes.append(df)
    if not partes:
        return pd.DataFrame()

    df = pd.concat(partes, ignore_index=True)
    df["na_base_mestre"] = df["na_base_mestre"].astype(str).str.upper().eq("TRUE")
    if "STATUS_RELACIONAMENTO_REAL" not in df:
        df["STATUS_RELACIONAMENTO_REAL"] = pd.NA
    df["STATUS_RELACIONAMENTO_REAL"] = df["STATUS_RELACIONAMENTO_REAL"].fillna("Fora da Base Mestre")
    for coluna in ("data_evento", "data_publicacao"):
        if coluna in df:
            df[coluna] = pd.to_datetime(df[coluna], errors="coerce")
    if "data_publicacao" not in df:
        df["data_publicacao"] = df.get("data_evento")
    df["data_publicacao"] = df["data_publicacao"].fillna(df.get("data_evento"))
    return df


def marcar_novidades(df: pd.DataFrame, hoje: date, dias: int = NOVIDADE_DIAS_PADRAO) -> pd.DataFrame:
    """Novo = fato tornado público (registro na fonte) nos últimos N dias.

    Usa a data da própria fonte, não "quando o job viu pela primeira vez":
    assim não depende de guardar histórico (o servidor em nuvem apaga
    arquivos ao reiniciar) e o selo é o mesmo em qualquer máquina.
    """
    df = df.copy()
    idade = (pd.Timestamp(hoje) - pd.to_datetime(df["data_publicacao"])).dt.days
    df["dias_desde_publicacao"] = idade
    df["novo"] = idade.between(0, dias)
    return df


# ------------------------------------------------------------
# Oferta sugerida
# ------------------------------------------------------------

def _bate(condicao: dict | None, linha) -> bool:
    if not condicao:
        return True
    if "qualificacao" in condicao:
        codigo = str(linha.get("qualificacao") or "").strip().zfill(4)
        if codigo not in {str(c).zfill(4) for c in condicao["qualificacao"]}:
            return False
    if "area_min" in condicao:
        area = pd.to_numeric(linha.get("area_total"), errors="coerce")
        if pd.isna(area) or area < float(condicao["area_min"]):
            return False
    return True


def sugerir(linha, ofertas: dict) -> dict:
    cfg = ofertas.get(linha.get("tipo_sinal"), {})
    perfil = next((p for p in cfg.get("perfis", []) if _bate(p.get("quando"), linha)), {})
    itens = {k: list(perfil.get(k, [])) for k in ("sesi", "senai", "outros")}
    extras = []
    for bloco in cfg.get("adicionais", []):
        if _bate(bloco.get("quando"), linha):
            extras.append(bloco.get("nome", ""))
            for k in itens:
                itens[k] += [i for i in bloco.get(k, []) if i not in itens[k]]
    return {
        "rotulo_tipo": cfg.get("rotulo", linha.get("tipo_sinal", "")),
        "icone": cfg.get("icone", "•"),
        "perfil": perfil.get("nome", ""),
        "perfil_extra": ", ".join(e for e in extras if e),
        "abordagem": " ".join(str(perfil.get("abordagem", "")).split()),
        "oferta_sesi": " · ".join(itens["sesi"]),
        "oferta_senai": " · ".join(itens["senai"]),
        "oferta_outros": " · ".join(itens["outros"]),
    }


def aplicar_ofertas(df: pd.DataFrame, ofertas: dict) -> pd.DataFrame:
    if df.empty:
        return df
    sugestoes = pd.DataFrame([sugerir(linha, ofertas) for _, linha in df.iterrows()],
                             index=df.index)
    return pd.concat([df, sugestoes], axis=1)
