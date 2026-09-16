import json

import anthropic
from pydantic import BaseModel

from src.domain.lead import LeadProfile
from src.domain.opportunity import Opportunity


MODEL = "claude-opus-5"

SYSTEM_PROMPT = """Você é um SDR (Sales Development Representative) sênior \
do SESI/SENAI.

Você recebe dados JÁ CALCULADOS e AUDITADOS sobre um lead e sobre as \
oportunidades comerciais aprovadas por um filtro automático de \
qualidade (Supervisor). A sua função é só transformar esses dados em \
linguagem de abordagem comercial — nunca invente produto, código, \
score ou dado que não tenha sido fornecido no prompt.

Se nenhuma oportunidade for informada, diga isso explicitamente na \
próxima ação (ex: "aguardar nova análise de portfólio") em vez de \
sugerir um produto genérico.

Responda SOMENTE com um JSON válido, sem texto antes ou depois, no \
formato exato:
{
  "hipotese_dor": "string",
  "perguntas_qualificacao": ["string", "string", ...],
  "argumentacao": "string",
  "proxima_acao": "string"
}"""


class AbordagemComercial(BaseModel):
    hipotese_dor: str
    perguntas_qualificacao: list[str]
    argumentacao: str
    proxima_acao: str


class SDRLLMAgent:
    """
    Agente SDR generativo: transforma sinais já calculados (lead,
    qualidade dos dados, score SDR determinístico, oportunidades já
    aprovadas pelo Supervisor) em hipótese de dor, perguntas de
    qualificação, argumentação de venda e próxima ação.

    Não decide qual produto recomendar nem recalcula score — isso já
    vem pronto e auditado do OpportunityEngine/Supervisor. Esta é a
    primeira peça do pipeline que usa um LLM; todo o resto do projeto
    é determinístico de propósito, para manter as decisões de negócio
    auditáveis.
    """

    def __init__(self, client: anthropic.Anthropic | None = None):
        self.client = client or anthropic.Anthropic()

    def _montar_prompt(
        self,
        lead: LeadProfile,
        qualidade: dict,
        qualificacao: dict,
        oportunidades: list[Opportunity],
    ) -> str:
        if oportunidades:
            oportunidades_texto = "\n".join(
                f"- {oportunidade.solucao} ({oportunidade.area}, "
                f"código {oportunidade.produto_codigo}, "
                f"fit {oportunidade.score_fit}): {oportunidade.motivo}"
                for oportunidade in oportunidades
            )
        else:
            oportunidades_texto = (
                "Nenhuma oportunidade aprovada pelo Supervisor para este lead."
            )

        return f"""Dados do lead:
- Empresa: {lead.razao_social or "não identificada"}
- Setor: {lead.setor or "não identificado"}
- Porte: {lead.porte or "não identificado"}
- Município: {lead.municipio or "não identificado"}
- Relacionamento atual: {lead.status_relacionamento or "não identificado"}

Qualidade dos dados: score {qualidade["score"]}, confiança {qualidade["confianca"]}
Qualificação SDR (determinística): score {qualificacao["score"]}, \
prioridade {qualificacao["prioridade"]}

Oportunidades aprovadas pelo Supervisor (produtos reais do catálogo \
SESI/SENAI):
{oportunidades_texto}"""

    def gerar_abordagem(
        self,
        lead: LeadProfile,
        qualidade: dict,
        qualificacao: dict,
        oportunidades: list[Opportunity],
    ) -> AbordagemComercial:
        prompt = self._montar_prompt(lead, qualidade, qualificacao, oportunidades)

        try:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=2000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.AuthenticationError as erro:
            raise RuntimeError(
                "Falha de autenticação na Claude API — verifique "
                "ANTHROPIC_API_KEY."
            ) from erro
        except anthropic.RateLimitError as erro:
            raise RuntimeError(
                "Limite de requisições da Claude API atingido."
            ) from erro
        except anthropic.APIConnectionError as erro:
            raise RuntimeError(
                "Falha de conexão com a Claude API."
            ) from erro
        except anthropic.APIStatusError as erro:
            raise RuntimeError(
                f"Erro da Claude API ({erro.status_code}): {erro.message}"
            ) from erro

        texto = next(
            (bloco.text for bloco in response.content if bloco.type == "text"),
            "",
        )

        try:
            dados = json.loads(texto)
        except json.JSONDecodeError as erro:
            raise ValueError(
                f"Resposta do LLM não é um JSON válido: {texto!r}"
            ) from erro

        return AbordagemComercial(**dados)
