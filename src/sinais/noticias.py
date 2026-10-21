"""Sinais de notícia: o que a imprensa e os sites oficiais dizem sobre a indústria de AL.

Fluxo (tudo com regra transparente, sem custo de IA):
  1. consultas do config/radar.yaml no Google News (RSS público, sem chave)
  2. só fica a notícia que cita Alagoas ou um município de AL, com contexto empresarial
  3. tema pelo primeiro grupo de palavras que aparecer (incentivo, expansão, ...)
  4. procura no título/resumo o nome de uma empresa da Base Mestre ou da Ampliada
  5. devolve no formato padrão de sinais (o mesmo do CNO), com o link da notícia

Nome citado nunca vira CNPJ "no chute": quando mais de uma empresa da base tem o
mesmo nome, o sinal sai com casamento "a revisar" e sem CNPJ.
"""
from __future__ import annotations

import email.utils
import html
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
import yaml

from src.tools.municipios import MUNICIPIOS_AL

RAIZ = Path(__file__).resolve().parents[2]
ARQ_RADAR = RAIZ / "config" / "radar.yaml"
URL_RSS = "https://news.google.com/rss/search?q={q}&hl=pt-BR&gl=BR&ceid=BR:pt-419"

SUFIXOS = r"\b(ltda|s\/?a|eireli|me|epp|cia|companhia|sociedade anonima|limitada|e filhos|filial)\b"
CONECTIVOS = {"de", "da", "do", "das", "dos", "e", "em", "a", "o"}


# ------------------------------------------------------------------ texto
def normalizar(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9\-/ ]", " ", t).split())


def carregar_config(caminho: Path = ARQ_RADAR) -> dict:
    with open(caminho, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ------------------------------------------------------------------ coleta
def montar_urls(cfg: dict, dias: int) -> list[tuple[str, str]]:
    return [(q, URL_RSS.format(q=quote_plus(f"{q} when:{dias}d"))) for q in cfg["consultas"]]


def ler_rss(conteudo: bytes, consulta: str = "") -> list[dict]:
    """Converte o XML do Google News em uma lista de notícias."""
    itens = []
    raiz = ET.fromstring(conteudo)
    for item in raiz.iter("item"):
        titulo = (item.findtext("title") or "").strip()
        fonte_el = item.find("source")
        fonte = (fonte_el.text or "").strip() if fonte_el is not None else ""
        if fonte and titulo.endswith(f" - {fonte}"):
            titulo = titulo[: -len(fonte) - 3].strip()
        resumo = re.sub(r"<[^>]+>", " ", html.unescape(item.findtext("description") or ""))
        try:
            publicado = email.utils.parsedate_to_datetime(item.findtext("pubDate") or "")
            publicado = publicado.astimezone().replace(tzinfo=None) if publicado.tzinfo else publicado
        except (TypeError, ValueError):
            publicado = None
        itens.append({
            "titulo": titulo,
            "resumo": " ".join(resumo.split()),
            "url_fonte": (item.findtext("link") or "").strip(),
            "veiculo": fonte,
            "url_veiculo": fonte_el.get("url", "") if fonte_el is not None else "",
            "data_publicacao": publicado,
            "consulta": consulta,
        })
    return itens


def baixar(cfg: dict, dias: int, sessao=None, avisar=print) -> list[dict]:
    import requests

    sessao = sessao or requests.Session()
    sessao.headers.setdefault("User-Agent", "Mozilla/5.0 (Radar de Oportunidades SENAI-AL)")
    todos, falhas = [], 0
    for consulta, url in montar_urls(cfg, dias):
        try:
            r = sessao.get(url, timeout=30)
            r.raise_for_status()
            todos += ler_rss(r.content, consulta)
        except Exception as erro:  # uma consulta com erro não derruba as outras
            falhas += 1
            avisar(f"  aviso: consulta '{consulta}' falhou ({type(erro).__name__})")
    if falhas == len(cfg["consultas"]):
        raise RuntimeError("todas as consultas falharam (sem acesso ao Google News?)")
    return todos


# ------------------------------------------------------------------ classificação
def _contem(texto_norm: str, termo: str) -> bool:
    termo = normalizar(termo)
    return re.search(rf"(?<![a-z0-9]){re.escape(termo)}", texto_norm) is not None


_MUNS = sorted(((normalizar(m), m) for m in MUNICIPIOS_AL), key=lambda x: -len(x[0]))


def achar_municipio(texto_norm: str) -> str:
    """Primeiro município de AL citado (nomes mais longos primeiro: 'Barra de São Miguel' antes de 'São Miguel')."""
    for chave, nome in _MUNS:
        if re.search(rf"(?<![a-z]){re.escape(chave)}(?![a-z])", texto_norm):
            return nome
    return ""


def cita_alagoas(texto_norm: str) -> bool:
    return bool(re.search(r"\balagoas\b|\balagoan[oa]s?\b|\b- al\b|\b/al\b", texto_norm)) or bool(achar_municipio(texto_norm))


def classificar(texto_norm: str, cfg: dict) -> dict | None:
    for tema in cfg["temas"]:
        achadas = [p for p in tema["palavras"] if _contem(texto_norm, p)]
        if achadas:
            return {**{k: tema[k] for k in ("id", "tipo_sinal", "rotulo", "peso", "validade_dias")},
                    "palavras": ", ".join(achadas[:4])}
    return None


def relevante(texto_norm: str, cfg: dict) -> bool:
    return cita_alagoas(texto_norm) and any(_contem(texto_norm, p) for p in cfg["contexto_empresarial"])


# ------------------------------------------------------------------ empresas
def _tokens(razao: str, genericos: set[str]) -> tuple[list[str], list[str]]:
    """(todas as palavras, palavras distintivas) do nome, sem sufixo societário."""
    t = re.sub(SUFIXOS, " ", normalizar(razao))
    tokens = [w for w in re.sub(r"[^a-z0-9 ]", " ", t).split() if w not in CONECTIVOS]
    return tokens, [w for w in tokens if w not in genericos and not w.isdigit()]


def indice_empresas(empresas: pd.DataFrame, genericos: set[str]) -> dict[str, list[dict]]:
    """Nome -> empresas. Três formas de citar a mesma empresa numa notícia:
      'sococo industrias alimenticias' (nome completo, sem LTDA/S.A.)
      'sococo industrias'              (duas primeiras palavras distintivas)
      'sococo'                         (só a primeira, se for longa e rara)
    Ficam de fora: MEI (nome de pessoa) e microempresas que não são indústria
    (quase nunca saem no jornal e geram falso positivo). Nome usado por mais de 3
    empresas, ou primeira palavra comum (nome próprio, palavra do dia a dia), não entra.
    """
    reg = empresas.to_dict("records")
    # frequência da primeira palavra distintiva no universo todo: nomes de pessoa são frequentes
    freq: dict[str, int] = {}
    for e in reg:
        _, d = _tokens(e.get("razao_social"), genericos)
        if d:
            freq[d[0]] = freq.get(d[0], 0) + 1

    indice: dict[str, list[dict]] = {}
    for e in reg:
        razao = str(e.get("razao_social") or "")
        if re.match(r"^\s*\d", razao):
            continue
        if e.get("tipo_empresa") != "Indústria" and str(e.get("Porte", "")).upper() == "MICRO EMPRESA":
            continue
        chaves = set()
        for nome in (razao, e.get("nome_fantasia")):
            if not isinstance(nome, str) or not nome.strip():
                continue
            tokens, d = _tokens(nome, genericos)
            if len(d) >= 2:
                chaves.add(" ".join(tokens))
                chaves.add(f"{d[0]} {d[1]}")
            if d and len(d[0]) >= 6 and freq.get(d[0], 0) <= 3:
                chaves.add(d[0])
        for ch in chaves:
            if len(ch) >= 6 and len(ch.split()) <= 6:
                lista = indice.setdefault(ch, [])
                if e["cnpj_basico"] not in {x["cnpj_basico"] for x in lista}:
                    lista.append(e)
    return {k: v for k, v in indice.items() if len(v) <= 3}


def casar_empresa(texto_norm: str, municipio: str, indice: dict[str, list[dict]]) -> dict:
    """Procura o nome de empresa mais longo citado no texto.

    Nome de uma palavra só ('sococo') vale como casamento só se o município da
    notícia for o da empresa; senão vai para revisão.
    """
    texto = " " + re.sub(r"[^a-z0-9 ]", " ", texto_norm) + " "
    achados = [ch for ch in indice if f" {ch} " in texto]
    if not achados:
        return {"casamento": "sem empresa"}
    ch = max(achados, key=lambda k: (len(k.split()), len(k)))
    candidatos = indice[ch]
    if len(candidatos) > 1 and municipio:
        no_mun = [c for c in candidatos if c.get("municipio") == municipio]
        candidatos = no_mun or candidatos
    if len(candidatos) > 1 or (len(ch.split()) == 1 and candidatos[0].get("municipio") != municipio):
        return {"casamento": "a revisar", "nome_citado": ch,
                "candidatos": " | ".join(f"{c['razao_social']} ({c.get('municipio', '')})" for c in candidatos[:4])}
    c = candidatos[0]
    return {"casamento": "por nome", "nome_citado": ch, **{k: c.get(k) for k in
            ("cnpj_basico", "cnpj", "razao_social", "STATUS_RELACIONAMENTO_REAL", "Porte", "tipo_empresa")}}


# ------------------------------------------------------------------ sinais
def processar(noticias: list[dict], empresas: pd.DataFrame, cfg: dict, hoje: date) -> pd.DataFrame:
    genericos = {normalizar(g) for g in cfg.get("nomes_genericos", [])}
    indice = indice_empresas(empresas, genericos)
    linhas, vistos = [], set()
    for n in noticias:
        chave_titulo = normalizar(n["titulo"])[:90]
        if not chave_titulo or chave_titulo in vistos:
            continue
        texto = normalizar(f"{n['titulo']} {n['resumo']}")
        if not relevante(texto, cfg):
            continue
        tema = classificar(texto, cfg)
        if not tema:
            continue
        vistos.add(chave_titulo)
        mun = achar_municipio(texto)
        emp = casar_empresa(texto, mun, indice)
        linhas.append({
            "tipo_sinal": tema["tipo_sinal"], "tema": tema["rotulo"], "palavras_chave": tema["palavras"],
            "descricao": n["titulo"], "resumo": n["resumo"][:400],
            "cnpj_basico": emp.get("cnpj_basico"), "cnpj": emp.get("cnpj"),
            "razao_social": emp.get("razao_social") or "",
            "STATUS_RELACIONAMENTO_REAL": emp.get("STATUS_RELACIONAMENTO_REAL"),
            "Porte": emp.get("Porte"), "na_base_mestre": emp.get("tipo_empresa") == "Indústria",
            "casamento": emp["casamento"], "nome_citado": emp.get("nome_citado", ""),
            "candidatos": emp.get("candidatos", ""),
            "municipio": mun, "data_publicacao": n["data_publicacao"], "data_evento": n["data_publicacao"],
            "veiculo": n["veiculo"], "url_fonte": n["url_fonte"], "consulta": n["consulta"],
            "peso": tema["peso"], "validade_dias": tema["validade_dias"],
            "fonte": f"Notícia · {n['veiculo']}" if n["veiculo"] else "Notícia",
        })
    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    df["data_publicacao"] = pd.to_datetime(df["data_publicacao"], errors="coerce")
    idade = (pd.Timestamp(hoje) - df["data_publicacao"]).dt.days.clip(lower=0)
    bonus = df["casamento"].map({"por nome": 1.0, "a revisar": 0.5}).fillna(0)
    fator = (1 - idade / df["validade_dias"]).clip(lower=0)
    df["idade_dias"] = idade
    df["score_momento"] = ((df["peso"] + bonus) * fator).round(2)
    return df.sort_values("score_momento", ascending=False).reset_index(drop=True)


def juntar_historico(novos: pd.DataFrame, anterior: pd.DataFrame, hoje: date, historico_dias: int) -> pd.DataFrame:
    """Acumula as coletas diárias (o RSS só mostra os últimos dias) e descarta o que venceu."""
    if anterior is not None and not anterior.empty:
        anterior = anterior.copy()
        anterior["data_publicacao"] = pd.to_datetime(anterior["data_publicacao"], errors="coerce")
        base = pd.concat([novos, anterior], ignore_index=True)
    else:
        base = novos
    if base.empty:
        return base
    base["_k"] = base["descricao"].map(lambda t: normalizar(t)[:90])
    base = base.drop_duplicates("_k", keep="first").drop(columns="_k")
    limite = pd.Timestamp(hoje) - pd.Timedelta(days=historico_dias)
    base = base[pd.to_datetime(base["data_publicacao"], errors="coerce") >= limite]
    return base.sort_values("data_publicacao", ascending=False).reset_index(drop=True)


def carregar_empresas(raiz: Path = RAIZ) -> pd.DataFrame:
    """Base Mestre + Base Ampliada, uma linha por CNPJ raiz, com relacionamento."""
    from src.tools.municipios import padronizar

    rel = {"SEM RELACIONAMENTO": "Sem relacionamento", "SESI + SENAI": "SESI + SENAI",
           "SOMENTE SENAI": "Somente SENAI", "SOMENTE SESI": "Somente SESI"}
    p = raiz / "data" / "processed"
    m = pd.read_csv(p / "BASE_MESTRE_COMERCIAL.csv", dtype=str, low_memory=False, encoding="utf-8-sig")
    m = pd.DataFrame({
        "cnpj": m["cnpj"].str.replace(r"\D", "", regex=True).str.zfill(14),
        "razao_social": m["razao_social"], "nome_fantasia": "",
        "municipio": padronizar(m["Municipio"]), "Porte": m["Porte"],
        "STATUS_RELACIONAMENTO_REAL": m["STATUS_RELACIONAMENTO"].map(rel).fillna("Sem relacionamento"),
        "tipo_empresa": "Indústria",
    })
    partes = [m]
    if (p / "BASE_AMPLIADA_AL.csv").exists():
        a = pd.read_csv(p / "BASE_AMPLIADA_AL.csv", dtype=str, encoding="utf-8-sig").fillna("")
        sesi, senai = a["POSSUI_SESI"].str.upper().eq("TRUE"), a["POSSUI_SENAI"].str.upper().eq("TRUE")
        status = pd.Series("Sem relacionamento", index=a.index)
        status[sesi & ~senai], status[senai & ~sesi], status[sesi & senai] = "Somente SESI", "Somente SENAI", "SESI + SENAI"
        partes.append(pd.DataFrame({
            "cnpj": a["cnpj"].str.replace(r"\D", "", regex=True).str.zfill(14),
            "razao_social": a["razao_social"], "nome_fantasia": a.get("nome_fantasia", ""),
            "municipio": padronizar(a["Municipio"]), "Porte": a["Porte"],
            "STATUS_RELACIONAMENTO_REAL": status, "tipo_empresa": a.get("Tipo", "Não indústria"),
        }))
    e = pd.concat(partes, ignore_index=True)
    e["cnpj_basico"] = e["cnpj"].str[:8]
    e["_matriz"] = e["cnpj"].str[8:12] == "0001"
    return e.sort_values("_matriz", ascending=False).drop_duplicates("cnpj_basico").drop(columns="_matriz")
