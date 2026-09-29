"""Presença digital de uma empresa: site oficial, Instagram, e-mail e
WhatsApp que a PRÓPRIA empresa publica.

Caminho (funções puras aqui; rede em jobs/enriquecer_digital.py):
  1. busca no Google (API Serper) pelo nome + município
  2. dos resultados, separa o perfil de Instagram e o site oficial,
     descartando diretórios de CNPJ, redes sociais e marketplaces
  3. abre só a página inicial do site oficial e lê e-mail, link de
     Instagram e link de WhatsApp (wa.me / api.whatsapp.com)

Não acessa o Instagram: só registra o endereço do perfil que aparece na
busca ou no site. Tudo sai marcado para o consultor validar.
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

DIRETORIOS = (
    "cnpj", "econodata", "casadosdados", "solutudo", "empresasdobrasil", "consultasocio", "serasa",
    "telelistas", "guiamais", "apontador", "listamais", "cnpja", "receitaws", "infoplex", "speedio",
    "facebook.com", "linkedin.com", "youtube.com", "tiktok.com", "twitter.com", "x.com", "instagram.com",
    "mercadolivre", "olx.com", "google.com", "wikipedia", "reclameaqui", "jusbrasil", "escavador",
    "gov.br", "glassdoor", "indeed", "ifood", "tripadvisor", "booking.com", "waze", "maps.",
)
IG_RESERVADOS = {"p", "reel", "reels", "explore", "stories", "tv", "accounts", "about", "direct", "legal"}
RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
RE_IG = re.compile(r"instagram\.com/([A-Za-z0-9._]{2,30})", re.I)
RE_WA = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=)(\d{10,13})", re.I)
EMAIL_LIXO = re.compile(r"\.(png|jpe?g|gif|webp|svg)$|sentry|example\.|wixpress|@(sentry|domain|email)\.", re.I)
SUFIXOS = r"\b(ltda|s ?a|eireli|me|epp|cia)\b"


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", str(t or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def nome_de_busca(razao_social: str, nome_fantasia: str = "") -> str:
    nome = nome_fantasia if str(nome_fantasia or "").strip() else razao_social
    nome = re.sub(r"^[\d./-]+\s*", "", str(nome or ""))
    nome = re.sub(SUFIXOS, " ", _norm(nome))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 &]", " ", nome)).strip()


def montar_consulta(razao_social: str, nome_fantasia: str, municipio: str) -> str:
    return f"{nome_de_busca(razao_social, nome_fantasia)} {municipio or ''} Alagoas".strip()


def perfil_instagram(url: str) -> str:
    m = RE_IG.search(str(url or ""))
    if not m or m.group(1).lower().strip(".") in IG_RESERVADOS:
        return ""
    return f"https://www.instagram.com/{m.group(1).strip('.')}"


def _tokens(nome: str) -> set[str]:
    return {t for t in nome.split() if len(t) >= 4}


def escolher_resultados(organicos: list[dict], nome: str) -> dict:
    """Primeiro Instagram e primeiro site oficial plausíveis dos resultados.

    O site só vale se o domínio ou o título tiver alguma palavra do nome da
    empresa — evita pegar o site de outra empresa que apareceu na busca.
    """
    alvo = _tokens(nome)
    achado = {"site": "", "instagram": ""}
    for r in organicos or []:
        link, titulo = r.get("link", ""), _norm(r.get("title", ""))
        if not achado["instagram"] and "instagram.com" in link:
            perfil = perfil_instagram(link)
            if perfil and (not alvo or alvo & _tokens(_norm(titulo + " " + perfil.replace(".", " ").replace("_", " ")))):
                achado["instagram"] = perfil
            continue
        dominio = urlparse(link).netloc.lower()
        if achado["site"] or not dominio or any(d in dominio for d in DIRETORIOS):
            continue
        base = _norm(dominio.replace("www.", "").split(".")[0])
        if alvo and not (alvo & _tokens(titulo) or any(t in base for t in alvo)):
            continue
        achado["site"] = f"{urlparse(link).scheme or 'https'}://{dominio}"
    return achado


def extrair_do_site(html: str, dominio: str = "") -> dict:
    """E-mail, Instagram e WhatsApp publicados na página. Prefere e-mail do
    próprio domínio do site."""
    html = html or ""
    emails = [e.lower().strip(".") for e in RE_EMAIL.findall(html) if not EMAIL_LIXO.search(e)]
    dom = dominio.lower().replace("www.", "")
    proprio = [e for e in emails if dom and e.endswith("@" + dom)]
    email = (proprio or emails or [""])[0]
    ig = next((p for p in (perfil_instagram(m.group(0)) for m in RE_IG.finditer(html)) if p), "")
    wa = RE_WA.search(html)
    whats = ""
    if wa:
        d = wa.group(1)[-11:] if wa.group(1).startswith("55") else wa.group(1)
        whats = f"({d[:2]}) {d[2:7]}-{d[7:]}" if len(d) == 11 else ""
    return {"email_site": email, "instagram": ig, "whatsapp_site": whats}
