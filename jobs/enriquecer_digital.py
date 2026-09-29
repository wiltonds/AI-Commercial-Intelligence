"""
enriquecer_digital.py — Site, Instagram, e-mail e WhatsApp publicados pela empresa.

Complementa data/contatos/CONTATOS_EMPRESAS.csv (colunas site, instagram,
email_site, whatsapp_site). Busca no Google via API Serper (serper.dev) e
abre só a página inicial do site oficial. Não acessa o Instagram.

Custo: cerca de 1 a 2 buscas por empresa. O Serper dá 2.500 buscas grátis e
cobra por mil depois disso — por isso roda em lotes, começando pelas
empresas que mais importam (com sinal, maiores portes) e pulando quem já
foi pesquisado.

Uso (PowerShell):
    $env:SERPER_API_KEY="sua_chave"
    python jobs/enriquecer_digital.py --limite 20        # teste
    python jobs/enriquecer_digital.py --limite 500
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from time import sleep
from urllib.parse import urlparse

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.contatos import ARQ_CONTATOS, COLUNAS, avaliar_qualidade, carregar_contatos  # noqa: E402
from src.tools.presenca_digital import (  # noqa: E402
    PAGINAS_CONTATO,
    deve_buscar,
    escolher_resultados,
    extrair_do_site,
    montar_consulta,
    nome_de_busca,
)

URL_SERPER = "https://google.serper.dev/search"
HEADERS_SITE = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36"}
RAIZ = Path(__file__).resolve().parent.parent
PORTE_ORDEM = {"DEMAIS": 0, "PEQUENO PORTE": 1, "MICRO EMPRESA": 2}


def buscar(consulta: str, chave: str) -> list[dict]:
    r = requests.post(URL_SERPER, timeout=30, headers={"X-API-KEY": chave, "Content-Type": "application/json"},
                      json={"q": consulta, "gl": "br", "hl": "pt-br", "num": 10})
    r.raise_for_status()
    return r.json().get("organic", [])


def ler_site(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS_SITE, timeout=10)
        if r.ok and "html" in r.headers.get("content-type", ""):
            return r.text[:500_000]
    except requests.RequestException:
        pass
    return ""


def pesquisar(linha: dict, chave: str, busca=buscar, site=ler_site) -> dict:
    agora = datetime.now().isoformat(timespec="seconds")
    if not deve_buscar(linha.get("razao_social", "")):
        return {"site": "", "instagram": "", "email_site": "", "whatsapp_site": "", "digital_em": agora}
    nome = nome_de_busca(linha.get("razao_social", ""), linha.get("nome_fantasia", ""))
    res = escolher_resultados(busca(montar_consulta(linha.get("razao_social", ""),
                                                    linha.get("nome_fantasia", ""),
                                                    linha.get("municipio", "")), chave), nome)
    if not res["instagram"]:
        res.update({k: v for k, v in escolher_resultados(busca(f"{nome} instagram", chave), nome).items()
                    if k == "instagram" and v})
    extra = {"email_site": "", "whatsapp_site": ""}
    if res["site"]:
        dominio = urlparse(res["site"]).netloc
        extra = extrair_do_site(site(res["site"]), dominio)
        for pagina in PAGINAS_CONTATO:                      # e-mail costuma estar na página de contato
            if extra["email_site"] and extra["whatsapp_site"]:
                break
            mais = extrair_do_site(site(res["site"] + pagina), dominio)
            extra = {k: extra[k] or mais[k] for k in extra}
        res["instagram"] = res["instagram"] or extra["instagram"]
    return {"site": res["site"], "instagram": res["instagram"], "email_site": extra["email_site"],
            "whatsapp_site": extra["whatsapp_site"], "digital_em": agora}


def revalidar(contatos: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """Aplica as regras atuais ao que JÁ foi coletado, sem nenhuma busca nova.

    Apaga site/Instagram que não passam (diretórios, homônimos, perfis
    genéricos...). E-mail e WhatsApp do site só ficam se o site ficar.
    """
    df = contatos.copy()
    sites_fora = igs_fora = 0
    for i, x in df[df["digital_em"].fillna("") != ""].iterrows():
        nome = nome_de_busca(x.get("razao_social", ""), x.get("nome_fantasia", ""))
        pode = deve_buscar(x.get("razao_social", ""))
        site_ok = bool(x["site"]) and pode and bool(escolher_resultados([{"link": x["site"]}], nome)["site"])
        ig_ok = bool(x["instagram"]) and pode and bool(escolher_resultados([{"link": x["instagram"]}], nome)["instagram"])
        if x["site"] and not site_ok:
            df.loc[i, ["site", "email_site", "whatsapp_site"]] = ""
            sites_fora += 1
        if x["instagram"] and not ig_ok:
            df.loc[i, "instagram"] = ""
            igs_fora += 1
    return df, sites_fora, igs_fora


def montar_fila(contatos: pd.DataFrame, com_sinal: set[str], porte: dict[str, str]) -> pd.DataFrame:
    fila = contatos[contatos["digital_em"].fillna("").eq("")].copy()
    fila["_sinal"] = fila["cnpj_basico"].isin(com_sinal)
    fila["_porte"] = fila["cnpj_basico"].map(porte).map(PORTE_ORDEM).fillna(3)
    return fila.sort_values(["_sinal", "_porte"], ascending=[False, True]).drop(columns=["_sinal", "_porte"])


def _porte_por_raiz() -> dict[str, str]:
    from src.tools.company_data import BASE_PATH
    b = pd.read_csv(BASE_PATH, dtype=str, usecols=["CNPJ_BASICO", "Porte"], encoding="utf-8-sig")
    return dict(zip(b["CNPJ_BASICO"].str.zfill(8), b["Porte"]))


def _com_sinal() -> set[str]:
    raizes = set()
    for arq in (RAIZ / "data" / "processed").glob("SINAIS_*.csv"):
        try:
            raizes |= set(pd.read_csv(arq, dtype=str, usecols=["cnpj_basico"])["cnpj_basico"].dropna())
        except (ValueError, KeyError):
            continue
    return raizes


def salvar(df: pd.DataFrame) -> None:
    avaliar_qualidade(df).reindex(columns=COLUNAS).fillna("").to_csv(ARQ_CONTATOS, index=False, encoding="utf-8-sig")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limite", type=int, default=200)
    parser.add_argument("--revalidar", action="store_true",
                        help="só aplica as regras atuais ao que já foi coletado (sem busca, sem custo)")
    parser.add_argument("--refazer", action="store_true",
                        help="apaga os resultados digitais já gravados e pesquisa de novo (usa créditos)")
    args = parser.parse_args()
    if args.revalidar:
        contatos, sf, igf = revalidar(carregar_contatos(receita=None))
        salvar(contatos)
        feitos = contatos[contatos["digital_em"] != ""]
        print(f"Revalidado sem busca: {sf} sites e {igf} Instagrams removidos.")
        print(f"Ficaram: {(feitos['site'] != '').sum():,} sites e {(feitos['instagram'] != '').sum():,} Instagrams "
              f"em {len(feitos):,} empresas pesquisadas.")
        return
    chave = os.getenv("SERPER_API_KEY", "")
    if not chave:
        sys.exit('Defina a chave antes: $env:SERPER_API_KEY="sua_chave"')

    contatos = carregar_contatos(receita=None)
    if args.refazer:
        for c in ("site", "instagram", "email_site", "whatsapp_site", "digital_em"):
            contatos[c] = ""
    fila = montar_fila(contatos, _com_sinal(), _porte_por_raiz()).head(args.limite)
    print(f"Pesquisando presença digital de {len(fila)} empresas ...")
    idx = contatos.set_index("cnpj_basico").index
    for i, linha in enumerate(fila.to_dict("records"), 1):
        try:
            achado = pesquisar(linha, chave)
        except requests.HTTPError as erro:
            print(f"  Serper recusou ({erro}). Créditos acabaram? Parando e salvando.")
            break
        pos = idx.get_loc(linha["cnpj_basico"])
        for k, v in achado.items():
            contatos.iat[pos, contatos.columns.get_loc(k)] = v
        print(f"  {i}/{len(fila)} {linha['razao_social'][:40]:40} "
              f"ig: {achado['instagram'].split('/')[-1] or '-':20} site: {achado['site'] or '-'}")
        if i % 25 == 0:
            salvar(contatos)
        sleep(0.5)
    salvar(contatos)
    feitos = contatos[contatos["digital_em"] != ""]
    print(f"\nPesquisadas até agora: {len(feitos):,} | com Instagram: {(feitos['instagram'] != '').sum():,} | "
          f"com site: {(feitos['site'] != '').sum():,} | com e-mail do site: {(feitos['email_site'] != '').sum():,}")


if __name__ == "__main__":
    main()
