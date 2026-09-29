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
    "prospectei", "perfill", "empresaqui", "cnpjs.rocks", "diariooficial", "portaldatransparencia",
)
# palavras comuns a muitas empresas: não servem para provar que um site/perfil é DELA
GENERICAS = {
    "engenharia", "construcoes", "construcao", "construtora", "empreendimentos", "imobiliarios", "imobiliaria",
    "servicos", "industria", "industrial", "comercio", "comercial", "alagoas", "maceio", "consorcio", "grupo",
    "infraestrutura", "ambiental", "saneamento", "materiais", "solucao", "solucoes", "regiao", "metropolitana",
    "distribuidora", "energia", "locacoes", "terraplenagem", "brasil", "nordeste", "empresa", "participacoes",
    "incorporacoes", "incorporadora", "projetos", "transportes", "alimentos", "tecnologia", "sistemas", "cia",
    "arapiraca", "nacional", "geral", "obras", "agro", "agropecuaria", "cooperativa", "associacao", "spe",
    "recuperacao", "judicial", "produtores", "derivados", "plasticos", "pavimentos", "agroindustrial",
}
NAO_BUSCAR = re.compile(r"\bconsorcio\b", re.I)
IG_RESERVADOS = {"p", "reel", "reels", "explore", "stories", "tv", "accounts", "about", "direct", "legal",
                 "popular", "developer", "web", "prospectei", "instagram"}
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
    nome = re.sub(r"\s*-?\s*em recupera[cç][aã]o judicial.*$", "", nome, flags=re.I)
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
    """Palavras distintivas do nome (3+ letras, fora da lista de genéricas).

    Siglas soltas ("F . P .", "LC") viram um token só ("fp", "lc"), desde
    que venham junto de outra palavra do nome no site/perfil — ver _bate.
    """
    partes = _norm(nome).split()
    tokens = {t for t in partes if len(t) >= 3 and t not in GENERICAS and not t.isdigit()}
    sigla = "".join(t for t in partes if len(t) <= 2 and t.isalpha() and t not in {"de", "da", "do", "e"})
    if 2 <= len(sigla) <= 4:
        tokens.add("#" + sigla)
    return tokens


PALAVRAS_DE_EMPRESA = re.compile(
    r"\b(ltda|s ?a|eireli|epp|cia|comercio|industria|servicos|constru\w*|engenharia|distribuidora|"
    r"transportes|associacao|cooperativa|consultoria|solucoes|empreendimentos|incorporadora|alimentos|"
    r"agroindustrial|grupo|usina|posto|farmacia|hotel|restaurante)\b")


def _parece_pessoa(nome: str) -> bool:
    """Firma individual com nome de pessoa (ex.: 'jairo lyra de andrade')."""
    n = _norm(nome)
    return 2 <= len(n.split()) <= 6 and not PALAVRAS_DE_EMPRESA.search(n)


def _compacto(texto: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _norm(texto))


def _bate(alvo: set[str], texto: str) -> bool:
    """Alguma palavra distintiva do nome aparece no texto (domínio ou @perfil, sem pontuação).

    Sigla sozinha é fraca (2 letras aparecem em muita coisa): só vale se o
    texto COMEÇAR pela sigla ("fpconstrutora", "lcengenharia").
    """
    t = _compacto(texto)
    for tok in alvo:
        if tok.startswith("#"):
            if t.startswith(tok[1:]):
                return True
        elif tok in t or (len(tok) > 4 and tok.endswith("s") and tok[:-1] in t):   # "alamedas" ~ "alameda"
            return True
    return False


def deve_buscar(razao_social: str) -> bool:
    """Não gasta busca com consórcio (quase nunca tem site/perfil próprio) nem
    com firma individual com nome de pessoa (o que aparece é perfil pessoal,
    muitas vezes de homônimo — não é canal da empresa)."""
    nome = re.sub(r"^[\d./-]+\s*", "", _norm(razao_social))
    return not NAO_BUSCAR.search(nome) and not _parece_pessoa(nome)


def escolher_resultados(organicos: list[dict], nome: str) -> dict:
    """Primeiro Instagram e primeiro site oficial plausíveis dos resultados.

    Regra rigorosa (precisão antes de cobertura): o DOMÍNIO do site e o
    @ do perfil precisam conter uma palavra distintiva do nome da empresa.
    Título não basta — diretórios de empresas repetem o nome no título.
    """
    alvo = _tokens(nome)
    achado = {"site": "", "instagram": ""}
    if not alvo or _parece_pessoa(nome):
        return achado
    for r in organicos or []:
        link = r.get("link", "")
        if not achado["instagram"] and "instagram.com" in link:
            perfil = perfil_instagram(link)
            if perfil and _bate(alvo, perfil.rsplit("/", 1)[-1]):
                achado["instagram"] = perfil
            continue
        dominio = urlparse(link).netloc.lower()
        if achado["site"] or not dominio or any(d in dominio for d in DIRETORIOS):
            continue
        if _bate(alvo, dominio.replace("www.", "")):
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


PAGINAS_CONTATO = ("/contato", "/fale-conosco", "/contact", "/contatos")
