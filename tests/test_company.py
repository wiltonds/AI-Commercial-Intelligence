from src.domain.company import Company


def test_criar_empresa():

    empresa = Company(
        cnpj="12345678000199",
        razao_social="Empresa Exemplo LTDA",
        municipio="Maceió",
        uf="AL",
        cnae_principal="4120400",
        setor="Construção",
        porte="Médio",
    )

    assert empresa.cnpj == "12345678000199"
    assert empresa.municipio == "Maceió"
    assert empresa.setor == "Construção"