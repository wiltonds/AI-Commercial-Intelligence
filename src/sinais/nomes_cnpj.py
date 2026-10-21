"""Nome e dados cadastrais de CNPJs que chegam aos sinais sem nome (ex.: CNO).

O CNO traz só o CNPJ do responsável pela obra. Quando ele não está na Base
Mestre nem na Ampliada (construtora de fora, SPE, holding...), o sinal fica
"(sem nome no CNO)". Este módulo consulta APIs públicas e gratuitas do cadastro
da Receita (BrasilAPI e, se falhar, Minha Receita) e guarda o resultado em
data/processed/CNPJ_NOMES.csv, para não consultar de novo.

O painel aplica o nome na hora de carregar os sinais (consolidar.py), sem
reescrever os arquivos de sinais.
"""
from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
ARQ_NOMES = RAIZ / "data" / "processed" / "CNPJ_NOMES.csv"
APIS = ["https://brasilapi.com.br/api/cnpj/v1/{cnpj}", "https://minhareceita.org/{cnpj}"]
COLS = ["cnpj", "razao_social", "nome_fantasia", "municipio_sede", "uf_sede", "cnae", "porte", "situacao",
        "consultado_em", "fonte_nome"]
SEM_NOME = "(sem nome"


def carregar_nomes(arq: Path = ARQ_NOMES) -> pd.DataFrame:
    if not arq.exists():
        return pd.DataFrame(columns=COLS)
    return pd.read_csv(arq, dtype=str, encoding="utf-8-sig", keep_default_na=False)


def cnpjs_sem_nome(sinais: pd.DataFrame) -> list[str]:
    if sinais.empty or "cnpj" not in sinais:
        return []
    nome = sinais.get("razao_social", pd.Series("", index=sinais.index)).fillna("").astype(str)
    cnpj = sinais["cnpj"].fillna("").astype(str).str.replace(r"\D", "", regex=True)
    alvo = cnpj[(nome.str.startswith(SEM_NOME) | nome.str.strip().eq("")) & cnpj.str.fullmatch(r"\d{14}")]
    return sorted(set(alvo) - {"0" * 14})


def _ler_resposta(js: dict) -> dict:
    cnae = js.get("cnae_fiscal") or ""
    return {
        "razao_social": str(js.get("razao_social") or "").strip(),
        "nome_fantasia": str(js.get("nome_fantasia") or "").strip(),
        "municipio_sede": str(js.get("municipio") or "").strip().title(),
        "uf_sede": str(js.get("uf") or "").strip().upper(),
        "cnae": str(cnae).zfill(7) if cnae else "",
        "porte": str(js.get("porte") or js.get("descricao_porte") or "").strip(),
        "situacao": str(js.get("descricao_situacao_cadastral") or "").strip(),
    }


def consultar(cnpj: str, sessao) -> dict | None:
    """Dados do CNPJ; None se nenhuma API respondeu (tenta de novo na próxima vez)."""
    for i, url in enumerate(APIS):
        try:
            r = sessao.get(url.format(cnpj=cnpj), timeout=20)
        except Exception:
            continue
        if r.status_code == 200:
            d = _ler_resposta(r.json())
            d["fonte_nome"] = ["BrasilAPI", "Minha Receita"][i]
            return d
        if r.status_code == 404:
            return {"razao_social": "", "fonte_nome": "não encontrado"}
        if r.status_code == 429:
            time.sleep(5)
    return None


def enriquecer(cnpjs: list[str], cache: pd.DataFrame, sessao, hoje: date, limite: int = 400,
               pausa: float = 0.4) -> pd.DataFrame:
    """Consulta os CNPJs ainda não conhecidos (até `limite` por execução) e devolve o cache atualizado."""
    conhecidos = set(cache["cnpj"]) if not cache.empty else set()
    novos = [c for c in cnpjs if c not in conhecidos][:limite]
    linhas = []
    for c in novos:
        d = consultar(c, sessao)
        if d is not None:
            linhas.append({**{k: "" for k in COLS}, **d, "cnpj": c, "consultado_em": hoje.isoformat()})
        time.sleep(pausa)
    if not linhas:
        return cache
    return pd.concat([cache, pd.DataFrame(linhas, columns=COLS)], ignore_index=True)


def aplicar_nomes(sinais: pd.DataFrame, nomes: pd.DataFrame) -> pd.DataFrame:
    """Troca '(sem nome ...)' pela razão social do cadastro, quando conhecida."""
    if sinais.empty or nomes.empty or "cnpj" not in sinais:
        return sinais
    ok = nomes[nomes["razao_social"].astype(str).str.strip().ne("")].drop_duplicates("cnpj", keep="last")
    mapa = ok.set_index("cnpj")
    cnpj = sinais["cnpj"].fillna("").astype(str).str.replace(r"\D", "", regex=True)
    nome = sinais.get("razao_social", pd.Series("", index=sinais.index)).fillna("").astype(str)
    trocar = (nome.str.startswith(SEM_NOME) | nome.str.strip().eq("")) & cnpj.isin(mapa.index)
    if not trocar.any():
        return sinais
    sinais = sinais.copy()
    sinais.loc[trocar, "razao_social"] = cnpj[trocar].map(mapa["razao_social"])
    if "Porte" in sinais:
        vazio = trocar & sinais["Porte"].fillna("").astype(str).str.strip().eq("")
        sinais.loc[vazio, "Porte"] = cnpj[vazio].map(mapa["porte"]).str.upper()
    sinais["uf_sede"] = cnpj.map(mapa["uf_sede"]).where(trocar, sinais.get("uf_sede"))
    return sinais
