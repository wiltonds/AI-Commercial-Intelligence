import json

import anthropic
import pytest

from src.agents.sdr_llm import SDRLLMAgent, AbordagemComercial
from src.domain.lead import LeadProfile
from src.domain.opportunity import Opportunity


class _BlocoTexto:
    def __init__(self, texto: str):
        self.type = "text"
        self.text = texto


class _RespostaFalsa:
    def __init__(self, texto: str):
        self.content = [_BlocoTexto(texto)]


class _ClienteFalso:
    """Substitui o client da Anthropic nos testes — nunca chama a API de verdade."""

    def __init__(self, texto_resposta: str):
        self._texto_resposta = texto_resposta
        self.ultima_chamada = None

        class _Messages:
            def create(inner_self, **kwargs):
                self.ultima_chamada = kwargs
                return _RespostaFalsa(self._texto_resposta)

        self.messages = _Messages()


def _lead_exemplo() -> LeadProfile:
    return LeadProfile(
        cnpj="24470149000100",
        razao_social="Padaria Exemplo LTDA",
        municipio="Maceió",
        setor="ALIMENTOS",
        porte="MICRO EMPRESA",
        status_relacionamento="SEM RELACIONAMENTO",
    )


def _oportunidade_exemplo() -> Opportunity:
    return Opportunity(
        company_cnpj="24470149000100",
        origem="AQUISIÇÃO",
        area="SENAI",
        solucao="GESTÃO DA QUALIDADE",
        motivo="Aderência setorial identificada.",
        score_fit=67.5,
        confidence=0.82,
        evidencias=["Setor=ALIMENTOS"],
        fonte="Teste",
        tipo_evidencia="INDÍCIO SETORIAL",
        prioridade="MÉDIA",
        produto_codigo="APP-724",
        caminho_catalogo="SENAI > EDUCAÇÃO PROFISSIONAL > GESTÃO DA QUALIDADE",
    )


def test_gerar_abordagem_retorna_estrutura_esperada():
    resposta_json = json.dumps(
        {
            "hipotese_dor": "Empresa pode ter dificuldade em padronizar processos.",
            "perguntas_qualificacao": [
                "Vocês já têm um processo formal de controle de qualidade?",
                "Quem seria o responsável por avaliar esse tipo de capacitação?",
            ],
            "argumentacao": "O curso de Gestão da Qualidade do SENAI atende exatamente essa lacuna.",
            "proxima_acao": "Agendar ligação de apresentação do curso.",
        }
    )

    agente = SDRLLMAgent(client=_ClienteFalso(resposta_json))

    resultado = agente.gerar_abordagem(
        lead=_lead_exemplo(),
        qualidade={"score": 85, "confianca": "ALTA"},
        qualificacao={"score": 60, "prioridade": "MÉDIA"},
        oportunidades=[_oportunidade_exemplo()],
    )

    assert isinstance(resultado, AbordagemComercial)
    assert "qualidade" in resultado.argumentacao.lower()
    assert len(resultado.perguntas_qualificacao) == 2


def test_gerar_abordagem_sem_oportunidades_nao_quebra():
    resposta_json = json.dumps(
        {
            "hipotese_dor": "Sem sinal suficiente para hipótese específica.",
            "perguntas_qualificacao": ["A empresa já conhece o SESI/SENAI?"],
            "argumentacao": "Nenhum produto aprovado ainda para esta empresa.",
            "proxima_acao": "Aguardar nova análise de portfólio.",
        }
    )

    cliente = _ClienteFalso(resposta_json)
    agente = SDRLLMAgent(client=cliente)

    resultado = agente.gerar_abordagem(
        lead=_lead_exemplo(),
        qualidade={"score": 85, "confianca": "ALTA"},
        qualificacao={"score": 60, "prioridade": "MÉDIA"},
        oportunidades=[],
    )

    assert isinstance(resultado, AbordagemComercial)
    assert "Nenhuma oportunidade aprovada" in cliente.ultima_chamada["messages"][0]["content"]


def test_gerar_abordagem_com_resposta_invalida_levanta_erro_claro():
    agente = SDRLLMAgent(client=_ClienteFalso("isso não é um JSON"))

    with pytest.raises(ValueError, match="não é um JSON válido"):
        agente.gerar_abordagem(
            lead=_lead_exemplo(),
            qualidade={"score": 85, "confianca": "ALTA"},
            qualificacao={"score": 60, "prioridade": "MÉDIA"},
            oportunidades=[],
        )


class _RespostaHttpFalsa:
    """Só o suficiente para satisfazer o construtor de APIStatusError."""

    def __init__(self, status_code: int = 401):
        self.request = None
        self.status_code = status_code
        self.headers = {}


def test_gerar_abordagem_trata_erro_de_autenticacao():
    class _ClienteComErro:
        class messages:
            @staticmethod
            def create(**kwargs):
                raise anthropic.AuthenticationError(
                    message="chave inválida",
                    response=_RespostaHttpFalsa(401),
                    body=None,
                )

    agente = SDRLLMAgent(client=_ClienteComErro())

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        agente.gerar_abordagem(
            lead=_lead_exemplo(),
            qualidade={"score": 85, "confianca": "ALTA"},
            qualificacao={"score": 60, "prioridade": "MÉDIA"},
            oportunidades=[],
        )
