from src.tools.lead_research import LeadResearchTool


def test_pesquisar_lead():
    tool = LeadResearchTool()

    lead = tool.pesquisar("24470149000100")

    assert lead is not None
    assert lead.cnpj == "24470149000100"
    assert lead.razao_social == "PADARIA OLIVEIRA PINDOBA LTDA"
    assert lead.tem_sesi is False
    assert lead.tem_senai is False