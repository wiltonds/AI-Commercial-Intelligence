"""
coletar_pncp_bim.py — Editais de obra/engenharia em AL no PNCP e quantos pedem BIM.

Roda no GitHub Actions (workflow "PNCP · BIM em editais de obra", manual):
o PNCP não é acessível de todo lugar. Uso:

    python jobs/coletar_pncp_bim.py --meses 12          # últimos 12 meses
    python jobs/coletar_pncp_bim.py --meses 12 --sem-docs  # só objeto (rápido)

Saídas (dados públicos):
    data/processed/PNCP_OBRAS_AL.csv     uma linha por contratação de obra/engenharia
    data/processed/PNCP_BIM_RESUMO.csv   por mês e esfera: editais, com BIM, % e valor
"""
from __future__ import annotations

import argparse
import io
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src.sinais.pncp_bim import (API_ARQUIVOS, API_CONSULTA, MODALIDADES, eh_obra,  # noqa: E402
                                 escolher_documentos, linha, termos_bim, trecho_bim)

SAIDA = RAIZ / "data" / "processed" / "PNCP_OBRAS_AL.csv"
RESUMO = RAIZ / "data" / "processed" / "PNCP_BIM_RESUMO.csv"
MAX_MB = 15


def _get(s: requests.Session, url: str, params=None, tentativas: int = 4, **kw):
    for i in range(tentativas):
        try:
            r = s.get(url, params=params, timeout=60, **kw)
            if r.status_code == 204:
                return None
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(5 * (i + 1))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            if i == tentativas - 1:
                print(f"  falhou {url}: {e}")
                return None
            time.sleep(3 * (i + 1))
    return None


def janelas(meses: int, hoje: date) -> list[tuple[str, str]]:
    fim = pd.Timestamp(hoje)
    out = []
    for k in range(meses):
        a = (fim - pd.DateOffset(months=k + 1)) + pd.Timedelta(days=1)
        b = fim - pd.DateOffset(months=k)
        out.append((a.strftime("%Y%m%d"), b.strftime("%Y%m%d")))
    return out


def listar(s, uf: str, meses: int) -> list[dict]:
    linhas = []
    for mod in MODALIDADES:
        for ini, fim in janelas(meses, date.today()):
            pagina = 1
            while True:
                r = _get(s, API_CONSULTA, {"dataInicial": ini, "dataFinal": fim, "codigoModalidadeContratacao": mod,
                                           "uf": uf, "pagina": pagina, "tamanhoPagina": 50})
                if r is None:
                    break
                j = r.json()
                for it in j.get("data") or []:
                    ln = linha(it, mod)
                    if eh_obra(ln["objeto"], ln["_compl"]):
                        linhas.append(ln)
                if not j.get("paginasRestantes"):
                    break
                pagina += 1
            print(f"{MODALIDADES[mod]} {ini}-{fim}: {len(linhas)} obras até aqui")
    return linhas


def texto_pdf(conteudo: bytes) -> str:
    from pypdf import PdfReader
    try:
        leitor = PdfReader(io.BytesIO(conteudo))
        return "\n".join((p.extract_text() or "") for p in leitor.pages[:200])
    except Exception:
        return ""


def texto_arquivo(conteudo: bytes) -> str:
    if conteudo[:4] == b"%PDF":
        return texto_pdf(conteudo)
    if conteudo[:2] == b"PK":  # zip: lê os PDFs de dentro
        import zipfile
        try:
            z = zipfile.ZipFile(io.BytesIO(conteudo))
            return "\n".join(texto_pdf(z.read(n)) for n in z.namelist()[:10] if n.lower().endswith(".pdf"))
        except Exception:
            return ""
    return ""


def ler_documentos(s, ln: dict) -> dict:
    r = _get(s, API_ARQUIVOS.format(cnpj=ln["_cnpj"], ano=ln["_ano"], seq=ln["_seq"]))
    if r is None:
        return {"docs_lidos": 0, "bim_no_documento": False, "termos_bim": "", "trecho_bim": "", "documentos": ""}
    docs = escolher_documentos(r.json() if isinstance(r.json(), list) else [])
    lidos, achados, trecho, nomes = 0, [], "", []
    for d in docs:
        a = _get(s, d["url"], stream=True)
        if a is None:
            continue
        conteudo = a.raw.read(MAX_MB * 1024 * 1024 + 1, decode_content=True)
        if len(conteudo) > MAX_MB * 1024 * 1024:
            continue
        t = texto_arquivo(conteudo)
        if not t.strip():
            continue
        lidos += 1
        nomes.append(str(d.get("titulo", ""))[:80])
        achados += termos_bim(t)
        trecho = trecho or trecho_bim(t)
    return {"docs_lidos": lidos, "bim_no_documento": bool(achados),
            "termos_bim": ", ".join(dict.fromkeys(achados)), "trecho_bim": trecho[:300], "documentos": " | ".join(nomes)}


def resumir(df: pd.DataFrame) -> pd.DataFrame:
    d = df.assign(mes=df["data_publicacao"].str[:7], cita_bim=df["bim_no_objeto"] | df["bim_no_documento"],
                  valor=pd.to_numeric(df["valor_estimado"], errors="coerce"))
    g = d.groupby(["mes", "esfera"]).agg(editais=("numero_controle", "nunique"), com_bim=("cita_bim", "sum"),
                                         lidos=("docs_lidos", lambda s: int((s > 0).sum())),
                                         valor_estimado=("valor", "sum")).reset_index()
    tot = d.groupby("mes").agg(editais=("numero_controle", "nunique"), com_bim=("cita_bim", "sum"),
                               lidos=("docs_lidos", lambda s: int((s > 0).sum())),
                               valor_estimado=("valor", "sum")).reset_index().assign(esfera="Todas")
    r = pd.concat([g, tot], ignore_index=True)
    r["pct_bim_lidos"] = (r["com_bim"] / r["lidos"].where(r["lidos"] > 0)).round(3)
    return r.sort_values(["mes", "esfera"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meses", type=int, default=12)
    ap.add_argument("--uf", default="AL")
    ap.add_argument("--sem-docs", action="store_true")
    a = ap.parse_args()
    s = requests.Session()
    s.headers["User-Agent"] = "Radar-Oportunidades-AL (dados abertos)"
    linhas = listar(s, a.uf, a.meses)
    df = pd.DataFrame(linhas).drop_duplicates("numero_controle") if linhas else pd.DataFrame()
    if df.empty:
        print("Nenhuma contratação de obra encontrada (ou API indisponível).")
        sys.exit(1)
    print(f"{len(df)} contratações de obra/engenharia em {a.uf}. Lendo documentos: {not a.sem_docs}")
    extra = []
    for i, ln in enumerate(df.to_dict("records"), 1):
        extra.append({"docs_lidos": 0, "bim_no_documento": False, "termos_bim": "", "trecho_bim": "", "documentos": ""}
                     if a.sem_docs else ler_documentos(s, ln))
        if i % 50 == 0:
            print(f"  {i}/{len(df)} lidos")
    df = pd.concat([df.reset_index(drop=True), pd.DataFrame(extra)], axis=1)
    df = df.drop(columns=[c for c in df.columns if c.startswith("_")]).sort_values("data_publicacao", ascending=False)
    df.to_csv(SAIDA, index=False, encoding="utf-8-sig")
    r = resumir(df)
    r.to_csv(RESUMO, index=False, encoding="utf-8-sig")
    cita = int((df["bim_no_objeto"] | df["bim_no_documento"]).sum())
    print(f"Pronto: {len(df)} editais de obra, {int((df['docs_lidos'] > 0).sum())} com documento lido, {cita} citam BIM.")


if __name__ == "__main__":
    main()
