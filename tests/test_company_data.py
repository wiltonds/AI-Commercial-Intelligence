from src.tools.company_data import CompanyDataTool


def test_consultar_empresa():
    tool = CompanyDataTool()

    empresa = tool.consultar_empresa("24470149000100")

    assert empresa is not None
    assert empresa["cnpj"] == "24470149000100"
    assert empresa["razao_social"] == "PADARIA OLIVEIRA PINDOBA LTDA"