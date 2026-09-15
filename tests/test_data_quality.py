from src.agents.data_quality import DataQualityAgent
from src.domain.lead import LeadProfile


def test_data_quality_lead_completo():
    lead = LeadProfile(
        cnpj="24470149000100",
        razao_social="PADARIA OLIVEIRA PINDOBA LTDA",
        municipio="Pindoba",
        cnae_principal="Fabricacao de massas alimenticias",
        setor="ALIMENTOS",
        porte="MICRO EMPRESA",
        status_relacionamento="SEM RELACIONAMENTO",
        encontrado_sebrae=True,
    )

    resultado = DataQualityAgent().avaliar(lead)

    assert resultado["score"] == 85
    assert resultado["confianca"] == "ALTA"
    assert resultado["apto_para_decisao"] is True
    assert len(resultado["alertas"]) == 0