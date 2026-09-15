from src.domain.lead import LeadProfile
from src.tools.company_data import CompanyDataTool
from src.intelligence.cnae_classifier import CNAEClassificador


class LeadResearchTool:
    """Pesquisa e estrutura informações comerciais de um lead."""

    def __init__(
        self,
        company_data_tool: CompanyDataTool | None = None,
        cnae_classifier: CNAEClassificador | None = None,
    ):
        self.company_data_tool = company_data_tool or CompanyDataTool()
        self.cnae_classifier = cnae_classifier or CNAEClassificador()

    def pesquisar(self, cnpj: str) -> LeadProfile | None:
        empresa = self.company_data_tool.consultar_empresa(cnpj)

        if empresa is None:
            return None

        setor_cnae = self.cnae_classifier.classificar(
            empresa.get("cnae_principal")
        )

        return LeadProfile(
            cnpj=empresa["cnpj"],
            razao_social=empresa.get("razao_social"),
            municipio=empresa.get("municipio"),
            cnae_principal=empresa.get("cnae_principal"),
            setor=setor_cnae or empresa.get("setor"),
            porte=empresa.get("porte"),

            tem_sesi=bool(empresa.get("tem_sesi")),
            tem_senai=bool(empresa.get("tem_senai")),
            tem_sesi_senai=bool(empresa.get("tem_sesi_senai")),

            status_relacionamento=empresa.get(
                "status_relacionamento"
            ),

            encontrado_sebrae=bool(
                empresa.get("encontrado_sebrae")
            ),
            sebrae_elegivel=bool(
                empresa.get("sebrae_elegivel")
            ),

            oportunidade_sesi=empresa.get(
                "oportunidade_sesi"
            ),
            oportunidade_senai=empresa.get(
                "oportunidade_senai"
            ),
            oportunidade_sebrae=empresa.get(
                "oportunidade_sebrae"
            ),
            oportunidade_geral=empresa.get(
                "oportunidade_geral"
            ),
            oportunidade_cross_sell=empresa.get(
                "oportunidade_cross_sell"
            ),
        )