from src.agents.sdr import SDRAgent
from src.domain.lead import LeadProfile


def test_sdr_prioriza_empresa_com_oportunidade():
    lead = LeadProfile(
        cnpj="24470149000100",
        razao_social="PADARIA OLIVEIRA PINDOBA LTDA",
        municipio="Pindoba",
        cnae_principal="Fabricacao de massas alimenticias",
        setor="ALIMENTOS",
        porte="MICRO EMPRESA",
        tem_sesi=False,
        tem_senai=False,
        tem_sesi_senai=False,
        status_relacionamento="SEM RELACIONAMENTO",
        encontrado_sebrae=True,
        sebrae_elegivel=True,
        oportunidade_sesi="SIM",
        oportunidade_senai="SIM",
        oportunidade_sebrae="NÃO ATENDIDA",
    )

    resultado = SDRAgent().qualificar(lead)

    assert resultado["cnpj"] == "24470149000100"
    assert resultado["score"] == 60
    assert resultado["prioridade"] == "MÉDIA"