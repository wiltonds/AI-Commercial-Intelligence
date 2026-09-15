from src.domain.lead import LeadProfile


def test_criar_lead():

    lead = LeadProfile(
        cnpj="12345678000199",
        razao_social="Empresa Exemplo LTDA",
        municipio="Maceió",
        uf="AL",
        cnae_principal="4120400",
        setor="Construção",
        porte="Médio",
        tem_sesi=True,
        tem_senai=False,
        encontrado_sebrae=True,
    )

    assert lead.cnpj == "12345678000199"
    assert lead.tem_sesi is True
    assert lead.tem_senai is False