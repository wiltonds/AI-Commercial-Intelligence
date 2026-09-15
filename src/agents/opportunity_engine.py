from src.domain.lead import LeadProfile
from src.domain.opportunity import Opportunity
from src.intelligence.sector_affinity import SectorAffinityEngine
from src.intelligence.portfolio_matcher import PortfolioMatcher
from src.agents.supervisor import Supervisor


class OpportunityEngine:
    """Identifica e prioriza oportunidades comerciais."""

    def __init__(
        self,
        affinity_engine: SectorAffinityEngine | None = None,
        portfolio_matcher: PortfolioMatcher | None = None,
        supervisor: Supervisor | None = None,
        produtos_por_area: int = 2,
    ):
        self.affinity_engine = affinity_engine or SectorAffinityEngine()
        self.portfolio_matcher = portfolio_matcher or PortfolioMatcher(
            affinity_engine=self.affinity_engine
        )
        self.supervisor = supervisor or Supervisor()
        self.produtos_por_area = produtos_por_area

    def _avaliar_produtos(self, recomendacao, origem: str):
        produtos = self.portfolio_matcher.buscar_por_area(
            recomendacao, limite=self.produtos_por_area
        )

        aprovados = []
        rejeitados = []

        for produto in produtos:
            avaliacao = self.supervisor.avaliar(produto)
            avaliacao["origem"] = origem

            if avaliacao["aprovado"]:
                aprovados.append(produto)
            else:
                rejeitados.append(avaliacao)

        return aprovados, rejeitados

    def _gerar(
        self,
        lead: LeadProfile,
    ) -> tuple[list[Opportunity], list[dict]]:

        oportunidades = []
        rejeitadas = []

        recomendacoes = self.affinity_engine.recomendar(lead.setor)

        # ==========================================================
        # CASO 1: SESI → SENAI
        # ==========================================================
        if lead.tem_sesi and not lead.tem_senai:

            for recomendacao in recomendacoes:

                if not recomendacao.area.startswith("SENAI"):
                    continue

                aprovados, rejeitados_area = self._avaliar_produtos(
                    recomendacao, origem="CROSS_SELL"
                )
                rejeitadas.extend(rejeitados_area)

                for produto in aprovados:
                    oportunidades.append(
                        Opportunity(
                            company_cnpj=lead.cnpj,
                            origem="CROSS_SELL",
                            area=produto.entidade,
                            solucao=produto.produto,
                            motivo=(
                                "Empresa possui relacionamento com SESI, "
                                "mas não possui relacionamento identificado "
                                "com SENAI. Aderência setorial identificada."
                            ),
                            score_fit=produto.score_fit,
                            confidence=0.95,
                            evidencias=[
                                "TEM_SESI=True",
                                "TEM_SENAI=False",
                                f"Setor={lead.setor}",
                                *produto.evidencias,
                            ],
                            fonte=(
                                "Base Mestre + Matriz de Afinidade Setorial "
                                "+ Portfolio Matcher"
                            ),
                            tipo_evidencia=(
                                "RELACIONAMENTO + INDÍCIO SETORIAL "
                                "+ PRODUTO REAL"
                            ),
                            prioridade="ALTA",
                            produto_codigo=produto.codigo,
                            caminho_catalogo=produto.caminho_texto,
                        )
                    )

        # ==========================================================
        # CASO 2: SENAI → SESI
        # ==========================================================
        elif lead.tem_senai and not lead.tem_sesi:

            for recomendacao in recomendacoes:

                if not recomendacao.area.startswith("SESI"):
                    continue

                aprovados, rejeitados_area = self._avaliar_produtos(
                    recomendacao, origem="CROSS_SELL"
                )
                rejeitadas.extend(rejeitados_area)

                for produto in aprovados:
                    oportunidades.append(
                        Opportunity(
                            company_cnpj=lead.cnpj,
                            origem="CROSS_SELL",
                            area=produto.entidade,
                            solucao=produto.produto,
                            motivo=(
                                "Empresa possui relacionamento com SENAI, "
                                "mas não possui relacionamento identificado "
                                "com SESI. Aderência setorial identificada."
                            ),
                            score_fit=produto.score_fit,
                            confidence=0.95,
                            evidencias=[
                                "TEM_SESI=False",
                                "TEM_SENAI=True",
                                f"Setor={lead.setor}",
                                *produto.evidencias,
                            ],
                            fonte=(
                                "Base Mestre + Matriz de Afinidade Setorial "
                                "+ Portfolio Matcher"
                            ),
                            tipo_evidencia=(
                                "RELACIONAMENTO + INDÍCIO SETORIAL "
                                "+ PRODUTO REAL"
                            ),
                            prioridade="ALTA",
                            produto_codigo=produto.codigo,
                            caminho_catalogo=produto.caminho_texto,
                        )
                    )

        # ==========================================================
        # CASO 3: NENHUM RELACIONAMENTO
        # ==========================================================
        elif not lead.tem_sesi and not lead.tem_senai:

            for recomendacao in recomendacoes:

                aprovados, rejeitados_area = self._avaliar_produtos(
                    recomendacao, origem="AQUISIÇÃO"
                )
                rejeitadas.extend(rejeitados_area)

                for produto in aprovados:
                    oportunidades.append(
                        Opportunity(
                            company_cnpj=lead.cnpj,
                            origem="AQUISIÇÃO",
                            area=produto.entidade,
                            solucao=produto.produto,
                            motivo=(
                                "Empresa não possui relacionamento "
                                "identificado com SESI ou SENAI e "
                                "apresenta aderência setorial."
                            ),
                            score_fit=produto.score_fit,
                            confidence=0.82,
                            evidencias=[
                                "TEM_SESI=False",
                                "TEM_SENAI=False",
                                f"Setor={lead.setor}",
                                *produto.evidencias,
                            ],
                            fonte=(
                                "Base Mestre + Classificador CNAE + "
                                "Matriz de Afinidade Setorial + "
                                "Portfolio Matcher"
                            ),
                            tipo_evidencia="INDÍCIO SETORIAL + PRODUTO REAL",
                            prioridade="MÉDIA",
                            produto_codigo=produto.codigo,
                            caminho_catalogo=produto.caminho_texto,
                        )
                    )

        oportunidades.sort(
            key=lambda oportunidade: oportunidade.score_fit,
            reverse=True,
        )

        rejeitadas.sort(
            key=lambda avaliacao: avaliacao["score_fit"],
            reverse=True,
        )

        return oportunidades, rejeitadas

    def identificar(self, lead: LeadProfile) -> list[Opportunity]:
        oportunidades, _ = self._gerar(lead)
        return oportunidades

    def identificar_com_auditoria(self, lead: LeadProfile) -> dict:
        """
        Mesmo resultado de `identificar`, mas também retorna as
        recomendações que o Supervisor rejeitou (com os checks e
        alertas que motivaram a rejeição) — para revisão interna da
        qualidade do motor, não para exibir ao time comercial.
        """

        aprovadas, rejeitadas = self._gerar(lead)

        return {
            "aprovadas": aprovadas,
            "rejeitadas": rejeitadas,
        }
