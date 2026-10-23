"""Editais de obra e serviço de engenharia em AL (PNCP) e quantos pedem BIM.

Fonte: API de consulta do PNCP (https://pncp.gov.br/api/consulta), contratações
publicadas por UF e modalidade. O BIM quase nunca está no objeto: costuma estar
no edital ou no termo de referência. Por isso o job lê também os PDFs anexados
(até 3 por contratação, os que parecem edital/TR/projeto básico).

Funções puras aqui; a coleta (rede) fica em jobs/coletar_pncp_bim.py.
"""
from __future__ import annotations

import re
import unicodedata

API_CONSULTA = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
API_ARQUIVOS = "https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos"
URL_EDITAL = "https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}"
# 4 concorrência eletrônica · 5 concorrência presencial · 6 pregão eletrônico · 8 dispensa
MODALIDADES = {4: "Concorrência eletrônica", 5: "Concorrência presencial", 6: "Pregão eletrônico", 8: "Dispensa"}
ESFERA = {"M": "Municipal", "E": "Estadual", "F": "Federal", "D": "Distrital"}

TERMOS_OBRA = ["obra", "obras", "construcao", "reforma", "ampliacao", "pavimentacao", "recapeamento", "drenagem",
               "esgotamento", "saneamento", "edificacao", "urbanizacao", "terraplenagem", "servicos de engenharia",
               "servico de engenharia", "recuperacao estrutural", "manutencao predial", "projeto executivo",
               "projeto basico", "elaboracao de projeto", "implantacao de"]
EXCLUIR = ["mao de obra", "mao-de-obra", "aquisicao de", "fornecimento de material", "locacao de veiculo",
           "material de expediente", "genero alimenticio", "medicamento"]
# BIM no texto: sigla em maiúscula (evita 'bim' dentro de palavras), nome por extenso ou arquivo IFC
_BIM = [re.compile(r"\bBIM\b"),
        re.compile(r"building\s+information\s+model", re.I),
        re.compile(r"modelagem\s+da\s+informa[cç][aã]o\s+da\s+constru", re.I),
        re.compile(r"\bformato\s+IFC\b|\.ifc\b|\bIFC\s*\d", re.I)]
DOC_PRIORIDADE = ["termo de referencia", "projeto basico", "edital", "caderno", "especificac", "memorial"]


def norm(t) -> str:
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t)


def eh_obra(objeto: str, complemento: str = "") -> bool:
    t = norm(f"{objeto} {complemento}")
    for x in EXCLUIR:
        t = t.replace(x, " ")
    return any(re.search(rf"\b{re.escape(k)}\b", t) for k in TERMOS_OBRA)


def termos_bim(texto: str) -> list[str]:
    """Trechos que indicam BIM (vazio = não cita)."""
    achados = []
    for r in _BIM:
        m = r.search(texto or "")
        if m:
            achados.append(m.group(0).strip())
    return achados


def trecho_bim(texto: str, largura: int = 120) -> str:
    for r in _BIM:
        m = r.search(texto or "")
        if m:
            a, b = max(0, m.start() - largura), min(len(texto), m.end() + largura)
            return re.sub(r"\s+", " ", texto[a:b]).strip()
    return ""


def escolher_documentos(arquivos: list[dict], limite: int = 3) -> list[dict]:
    """Os anexos que mais provavelmente falam de BIM: TR, projeto básico, edital."""
    def nota(a):
        t = norm(f"{a.get('titulo', '')} {a.get('tipoDocumentoNome', '')}")
        for i, k in enumerate(DOC_PRIORIDADE):
            if k in t:
                return i
        return len(DOC_PRIORIDADE)
    ativos = [a for a in arquivos if a.get("statusAtivo", True) is not False and a.get("url")]
    return sorted(ativos, key=nota)[:limite]


def linha(item: dict, modalidade: int) -> dict:
    org, un = item.get("orgaoEntidade") or {}, item.get("unidadeOrgao") or {}
    cnpj, ano, seq = org.get("cnpj", ""), item.get("anoCompra"), item.get("sequencialCompra")
    objeto, compl = item.get("objetoCompra") or "", item.get("informacaoComplementar") or ""
    return {
        "numero_controle": item.get("numeroControlePNCP", ""),
        "data_publicacao": str(item.get("dataPublicacaoPncp") or "")[:10],
        "modalidade": MODALIDADES.get(modalidade, str(modalidade)),
        "esfera": ESFERA.get(org.get("esferaId", ""), org.get("esferaId", "")),
        "orgao": org.get("razaoSocial", ""),
        "orgao_cnpj": cnpj,
        "municipio": un.get("municipioNome", ""),
        "objeto": re.sub(r"\s+", " ", objeto).strip()[:500],
        "valor_estimado": item.get("valorTotalEstimado"),
        "situacao": item.get("situacaoCompraNome", ""),
        "bim_no_objeto": bool(termos_bim(f"{objeto} {compl}")),
        "url_pncp": URL_EDITAL.format(cnpj=cnpj, ano=ano, seq=seq) if cnpj and ano and seq else "",
        "_cnpj": cnpj, "_ano": ano, "_seq": seq, "_compl": compl,
    }
