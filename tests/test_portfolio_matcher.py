from src.intelligence.portfolio_matcher import PortfolioMatcher


def test_catalogo_pesquisavel_carrega_todos_os_produtos():

    matcher = PortfolioMatcher()

    catalogo = matcher.catalogo_pesquisavel()

    assert len(catalogo) == 3712
    assert all(produto.codigo for produto in catalogo)
    assert all(produto.texto_busca for produto in catalogo)


def test_recomendar_metalmecanica_encontra_produto_real_com_alta_correspondencia():

    matcher = PortfolioMatcher()

    resultados = matcher.recomendar("Metalmecânica", areas=3, produtos_por_area=2)

    assert resultados

    melhor = resultados[0]

    assert melhor.entidade == "SESI"
    assert melhor.codigo is not None
    assert melhor.score_correspondencia_texto == 100.0
    assert "MÁQUINAS" in melhor.produto.upper()
    assert melhor.area_origem == "SESI Segurança de Máquinas"
    assert melhor.correspondencia_especifica is True


def test_correspondencia_especifica_rejeita_match_por_termo_generico():
    """
    'Técnicas de Vendas' batia com a área 'SENAI Formação Técnica'
    apenas pelo termo genérico 'técnica' (presente em ~5,6% do
    catálogo) — sem nenhum termo específico sustentando o match.
    """

    matcher = PortfolioMatcher()

    resultados = matcher.recomendar("Construção", areas=3, produtos_por_area=3)

    tecnicas_de_vendas = [
        resultado
        for resultado in resultados
        if resultado.produto.upper() == "TÉCNICAS DE VENDAS"
    ]

    assert tecnicas_de_vendas

    for resultado in tecnicas_de_vendas:
        assert resultado.correspondencia_especifica is False


def test_correspondencia_especifica_aceita_match_por_termo_raro():
    """
    'Gestão da Qualidade' bate com 'Qualidade e Laboratórios' apenas
    pelo termo 'qualidade', mas ele é raro no catálogo (~0,8%) e
    por isso é considerado evidência específica suficiente.
    """

    matcher = PortfolioMatcher()

    resultados = matcher.recomendar("Alimentos", areas=3, produtos_por_area=3)

    gestao_qualidade = [
        resultado
        for resultado in resultados
        if resultado.produto.upper() == "GESTÃO DA QUALIDADE"
    ]

    assert gestao_qualidade

    for resultado in gestao_qualidade:
        assert resultado.correspondencia_especifica is True


def test_recomendar_setor_desconhecido_retorna_lista_vazia():

    matcher = PortfolioMatcher()

    assert matcher.recomendar("Setor Inexistente") == []


def test_buscar_por_area_nao_repete_evidencias_sem_termos_compativeis():

    matcher = PortfolioMatcher()

    resultados = matcher.recomendar("Alimentos", areas=3, produtos_por_area=3)

    for resultado in resultados:
        assert resultado.score_fit > 0
        assert resultado.evidencias
        assert resultado.area_origem in resultado.evidencias[0]
