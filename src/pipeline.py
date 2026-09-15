from src.tools.lead_research import LeadResearchTool
from src.agents.data_quality import DataQualityAgent
from src.agents.sdr import SDRAgent
from src.agents.opportunity_engine import OpportunityEngine


class CommercialPipeline:
    """Executa o diagnóstico comercial completo de um CNPJ."""

    def __init__(self):
        self.research = LeadResearchTool()
        self.data_quality = DataQualityAgent()
        self.sdr = SDRAgent()
        self.opportunity = OpportunityEngine()

    def executar(self, cnpj: str) -> dict | None:
        # 1. Pesquisa do lead
        lead = self.research.pesquisar(cnpj)

        if lead is None:
            return None

        # 2. Avaliação da qualidade dos dados
        qualidade = self.data_quality.avaliar(lead)

        # 3. Qualificação SDR
        qualificacao = self.sdr.qualificar(lead)

        # 4. Identificação de oportunidades
        oportunidades = self.opportunity.identificar(lead)

        return {
            "lead": lead,
            "qualidade_dados": qualidade,
            "qualificacao": qualificacao,
            "oportunidades": oportunidades,
        }