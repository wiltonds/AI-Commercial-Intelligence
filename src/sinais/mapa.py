"""Mapa de Alagoas: municípios, indústrias e oportunidades do radar.

Duas camadas:
  municípios  pintados por um indicador (sem relacionamento, penetração, sinais,
              VAB da indústria, produção de uma cadeia)
  indústrias  um ponto por empresa, colorido pelo relacionamento e destacado
              quando há oportunidade ativa no radar

A base não tem endereço geocodificado, só o município. Por isso o ponto de cada
empresa é sorteado DENTRO do polígono do seu município, sempre no mesmo lugar
(semente = CNPJ). Mostra a densidade real por município, não o endereço.

Malha municipal: config/geo/al_municipios.geojson (IBGE, via github.com/tbrugz/geodata-br).
"""
from __future__ import annotations

import json
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
ARQ_MALHA = RAIZ / "config" / "geo" / "al_municipios.geojson"

# cores (RGB) — status da empresa
COR_CLIENTE = [30, 122, 70]          # verde
COR_SEM_REL = [138, 143, 152]        # cinza
COR_OPORTUNIDADE = [232, 89, 12]     # laranja
# escala sequencial (claro -> escuro) para os municípios
ESCALA = [[239, 243, 255], [198, 219, 239], [158, 202, 225], [107, 174, 214], [49, 130, 189], [8, 81, 156]]


def carregar_malha(arq: Path = ARQ_MALHA) -> dict:
    return json.loads(arq.read_text(encoding="utf-8"))


def _anel(feature: dict) -> np.ndarray:
    """Anel externo do polígono (o maior, se for MultiPolygon)."""
    g = feature["geometry"]
    if g["type"] == "Polygon":
        return np.asarray(g["coordinates"][0], dtype=float)
    aneis = [np.asarray(p[0], dtype=float) for p in g["coordinates"]]
    return max(aneis, key=len)


def _area_centroide(anel: np.ndarray) -> tuple[float, float, float]:
    x, y = anel[:, 0], anel[:, 1]
    x1, y1 = np.roll(x, -1), np.roll(y, -1)
    cruz = x * y1 - x1 * y
    a = cruz.sum() / 2
    if abs(a) < 1e-12:
        return 0.0, float(x.mean()), float(y.mean())
    return abs(a), float(((x + x1) * cruz).sum() / (6 * a)), float(((y + y1) * cruz).sum() / (6 * a))


def centroides(malha: dict) -> pd.DataFrame:
    linhas = []
    for f in malha["features"]:
        _, lon, lat = _area_centroide(_anel(f))
        linhas.append({"municipio": f["properties"]["municipio"], "lon": lon, "lat": lat})
    return pd.DataFrame(linhas)


def _dentro(px: np.ndarray, py: np.ndarray, anel: np.ndarray) -> np.ndarray:
    """Ray casting vetorizado: quais pontos estão dentro do anel."""
    x0, y0 = anel[:-1, 0], anel[:-1, 1]
    x1, y1 = anel[1:, 0], anel[1:, 1]
    px, py = px[:, None], py[:, None]
    cruza = ((y0 > py) != (y1 > py))
    with np.errstate(divide="ignore", invalid="ignore"):
        xc = (x1 - x0) * (py - y0) / (y1 - y0) + x0
    return (cruza & (px < xc)).sum(axis=1) % 2 == 1


def pontos_no_municipio(chaves: list[str], anel: np.ndarray) -> np.ndarray:
    """Um ponto (lon, lat) dentro do anel para cada chave, sempre o mesmo para a mesma chave."""
    xmin, ymin = anel.min(axis=0)
    xmax, ymax = anel.max(axis=0)
    out = np.empty((len(chaves), 2))
    for i, chave in enumerate(chaves):
        rng = np.random.default_rng(zlib.crc32(str(chave).encode()))
        for _ in range(20):  # 20 lotes de 32 tentativas: sobra para qualquer formato de município
            cx = rng.uniform(xmin, xmax, 32)
            cy = rng.uniform(ymin, ymax, 32)
            ok = _dentro(cx, cy, anel)
            if ok.any():
                j = int(np.argmax(ok))
                out[i] = cx[j], cy[j]
                break
        else:
            _, lon, lat = _area_centroide(anel)
            out[i] = lon, lat
    return out


def posicionar(emp: pd.DataFrame, malha: dict) -> pd.DataFrame:
    """Acrescenta lon/lat a cada empresa (coluna 'municipio' com grafia oficial; chave 'cnpj_basico')."""
    aneis = {f["properties"]["municipio"]: _anel(f) for f in malha["features"]}
    emp = emp[emp["municipio"].isin(aneis)].copy()
    emp["lon"], emp["lat"] = np.nan, np.nan
    for mun, idx in emp.groupby("municipio").groups.items():
        xy = pontos_no_municipio(emp.loc[idx, "cnpj_basico"].astype(str).tolist(), aneis[mun])
        emp.loc[idx, "lon"], emp.loc[idx, "lat"] = xy[:, 0], xy[:, 1]
    return emp


def empresas_do_mapa(ind: pd.DataFrame, sinais: pd.DataFrame) -> pd.DataFrame:
    """Indústrias da base + empresas de fora da base que aparecem nos sinais, com status e oportunidade."""
    emp = ind[["cnpj_basico", "razao_social", "municipio", "porte", "setor_cni", "cliente"]].copy()
    emp["origem"] = "Base Mestre"
    ops = pd.DataFrame(columns=["cnpj_basico", "n_sinais", "oportunidade", "negocios_sinal", "score"])
    if not sinais.empty and "cnpj_basico" in sinais:
        s = sinais.dropna(subset=["cnpj_basico"]).sort_values("score_momento", ascending=False)
        if not s.empty:
            g = s.groupby("cnpj_basico")
            ops = pd.DataFrame({
                "n_sinais": g.size(),
                "oportunidade": g["descricao"].first().astype(str).str[:160],
                "negocios_sinal": g["negocios"].agg(lambda x: " · ".join(sorted({n.strip() for v in x.fillna("")
                                                                                  for n in str(v).split("·") if n.strip()}))),
                "score": g["score_momento"].max(),
            }).reset_index()
            fora = s[~s["cnpj_basico"].isin(emp["cnpj_basico"])].drop_duplicates("cnpj_basico")
            if not fora.empty:
                emp = pd.concat([emp, pd.DataFrame({
                    "cnpj_basico": fora["cnpj_basico"], "razao_social": fora["razao_social"],
                    "municipio": fora["municipio"], "porte": fora.get("Porte", ""),
                    "setor_cni": fora.get("segmento", pd.Series("Fora da base", index=fora.index)).fillna("Fora da base"),
                    "cliente": fora["STATUS_RELACIONAMENTO_REAL"].isin(["SESI + SENAI", "Somente SESI", "Somente SENAI"]),
                    "origem": "Sinal do radar (fora da Base Mestre)"})], ignore_index=True)
    emp = emp.merge(ops, on="cnpj_basico", how="left")
    emp["n_sinais"] = emp["n_sinais"].fillna(0).astype(int)
    emp["status"] = np.where(emp["n_sinais"] > 0, "Com oportunidade no radar",
                             np.where(emp["cliente"], "Cliente", "Sem relacionamento"))
    return emp


def cor_status(status: pd.Series) -> list:
    m = {"Cliente": COR_CLIENTE, "Sem relacionamento": COR_SEM_REL, "Com oportunidade no radar": COR_OPORTUNIDADE}
    return [m.get(s, COR_SEM_REL) for s in status]


def cor_escala(valores: pd.Series) -> list:
    """Cor sequencial por quantis (5 faixas + zero/vazio no tom mais claro)."""
    v = pd.to_numeric(valores, errors="coerce")
    positivos = v[v > 0]
    if positivos.empty:
        return [ESCALA[0]] * len(v)
    cortes = np.unique(np.quantile(positivos, [0.2, 0.4, 0.6, 0.8]))
    return [ESCALA[0] if (pd.isna(x) or x <= 0) else ESCALA[1 + int(np.searchsorted(cortes, x, side="left"))]
            for x in v]


def malha_com_indicadores(malha: dict, tabela: pd.DataFrame, coluna: str, rotulo: str, fmt) -> dict:
    """Copia a malha com cor e texto do tooltip em cada município."""
    t = tabela.set_index("municipio")
    cores = dict(zip(t.index, cor_escala(t[coluna]))) if coluna in t else {}
    out = {"type": "FeatureCollection", "features": []}
    for f in malha["features"]:
        mun = f["properties"]["municipio"]
        r = t.loc[mun] if mun in t.index else None
        val = r[coluna] if r is not None and coluna in t else None

        def g(c, r=r):
            return int(r[c]) if r is not None and c in r and pd.notna(r[c]) else 0

        detalhe = (f"{rotulo}: {fmt(val) if val is not None and pd.notna(val) else '—'}<br/>"
                   f"Indústrias: {g('industrias')} · Clientes: {g('clientes')} · "
                   f"Sem relacionamento: {g('sem_relacionamento')}<br/>Sinais (90 dias): {g('sinais_90d')}")
        out["features"].append({"type": "Feature", "geometry": f["geometry"], "properties": {
            "municipio": mun, "titulo": mun, "detalhe": detalhe,
            "cor": cores.get(mun, ESCALA[0]) + [170]}})
    return out
