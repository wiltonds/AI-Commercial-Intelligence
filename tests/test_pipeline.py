from src.pipeline import CommercialPipeline


def test_pipeline_completo():

    pipeline = CommercialPipeline()

    resultado = pipeline.executar("24470149000100")

    assert resultado is not None

    lead = resultado["lead"]
    qualificacao = resultado["qualificacao"]
    oportunidades = resultado["oportunidades"]

    assert lead.cnpj == "24470149000100"
    assert lead.razao_social == "PADARIA OLIVEIRA PINDOBA LTDA"

    assert qualificacao["cnpj"] == "24470149000100"

    assert isinstance(oportunidades, list)