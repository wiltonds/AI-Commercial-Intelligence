from src.domain.opportunity import Opportunity


def test_criar_oportunidade():

    oportunidade = Opportunity(
        company_cnpj="12345678000199",
        origem="CNAE + relacionamento",
        area="Saúde e Segurança",
        solucao="NR-12",
        motivo="Empresa possui aderência ao setor e relacionamento SESI, mas não SENAI.",
        score_fit=91,
        confidence=0.87,
        evidencias=[
            "CNAE compatível",
            "Possui relacionamento SESI",
            "Não possui relacionamento SENAI",
        ],
        fonte="Base Mestre + Matriz de Afinidade Setorial",
        tipo_evidencia="RELACIONAMENTO + INDÍCIO SETORIAL",
        prioridade="Alta",
        consultor_destino="SENAI",
    )

    assert oportunidade.company_cnpj == "12345678000199"
    assert oportunidade.score_fit == 91
    assert oportunidade.confidence == 0.87
    assert oportunidade.fonte == "Base Mestre + Matriz de Afinidade Setorial"
    assert oportunidade.tipo_evidencia == "RELACIONAMENTO + INDÍCIO SETORIAL"
    assert oportunidade.prioridade == "Alta"
    assert oportunidade.consultor_destino == "SENAI"