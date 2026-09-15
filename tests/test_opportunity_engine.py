from src.domain.lead import LeadProfile
from src.agents.opportunity_engine import OpportunityEngine


def test_identificar_cross_sell_senai_retorna_produtos_reais_aprovados():

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

    engine = OpportunityEngine()

    oportunidades = engine.identificar(lead)

    assert oportunidades

    for oportunidade in oportunidades:
        assert oportunidade.area == "SENAI"
        assert oportunidade.origem == "CROSS_SELL"
        assert oportunidade.confidence == 0.95
        assert oportunidade.produto_codigo is not None
        assert oportunidade.caminho_catalogo is not None
        # "Técnicas de Vendas" era o falso positivo que motivou o
        # Supervisor — não pode mais aparecer aqui.
        assert oportunidade.solucao.upper() != "TÉCNICAS DE VENDAS"

    assert oportunidades == sorted(
        oportunidades, key=lambda o: o.score_fit, reverse=True
    )


def test_identificar_sem_relacionamento_retorna_produtos_das_duas_entidades():

    lead = LeadProfile(
        cnpj="98765432000188",
        razao_social="Indústria de Alimentos LTDA",
        setor="Alimentos",
        tem_sesi=False,
        tem_senai=False,
    )

    engine = OpportunityEngine()

    oportunidades = engine.identificar(lead)

    assert oportunidades
    assert all(o.origem == "AQUISIÇÃO" for o in oportunidades)
    assert all(o.produto_codigo is not None for o in oportunidades)
    assert {o.area for o in oportunidades} <= {"SESI", "SENAI"}


def test_identificar_com_auditoria_expoe_rejeitadas_do_supervisor():

    lead = LeadProfile(
        cnpj="12345678000199",
        razao_social="Empresa Exemplo LTDA",
        setor="Construção",
        tem_sesi=True,
        tem_senai=False,
    )

    engine = OpportunityEngine(produtos_por_area=3)

    resultado = engine.identificar_com_auditoria(lead)

    assert resultado["aprovadas"] == engine.identificar(lead)
    assert resultado["rejeitadas"]

    tecnicas_de_vendas = next(
        avaliacao
        for avaliacao in resultado["rejeitadas"]
        if avaliacao["produto"].upper() == "TÉCNICAS DE VENDAS"
    )

    assert tecnicas_de_vendas["aprovado"] is False
    assert tecnicas_de_vendas["origem"] == "CROSS_SELL"
    assert tecnicas_de_vendas["alertas"]


def test_identificar_setor_sem_area_conhecida_nao_gera_oportunidade():

    lead = LeadProfile(
        cnpj="11111111000111",
        razao_social="Empresa Setor Desconhecido",
        setor="Setor Inexistente",
        tem_sesi=False,
        tem_senai=False,
    )

    engine = OpportunityEngine()

    assert engine.identificar(lead) == []
