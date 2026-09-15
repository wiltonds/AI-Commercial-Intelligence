from src.agents.supervisor import Supervisor
from src.intelligence.portfolio_matcher import PortfolioMatcher


def test_supervisor_aprova_match_com_evidencia_forte():

    matcher = PortfolioMatcher()
    supervisor = Supervisor()

    resultados = matcher.recomendar("Metalmecânica", areas=3, produtos_por_area=2)

    melhor = resultados[0]

    resultado = supervisor.avaliar(melhor)

    assert resultado["aprovado"] is True
    assert resultado["alertas"] == []
    assert all(resultado["checks"].values())


def test_supervisor_rejeita_match_por_correspondencia_generica():
    """
    'Técnicas de Vendas' tem fit acima do mínimo (sustentado pelo
    score de afinidade setorial), mas a única evidência textual é
    o termo genérico 'técnica' — o Supervisor deve rejeitar mesmo
    assim, pois a correspondência não é específica o suficiente.
    """

    matcher = PortfolioMatcher()
    supervisor = Supervisor()

    resultados = matcher.recomendar("Construção", areas=3, produtos_por_area=3)

    tecnicas_de_vendas = next(
        resultado
        for resultado in resultados
        if resultado.produto.upper() == "TÉCNICAS DE VENDAS"
    )

    assert tecnicas_de_vendas.score_fit >= 60

    resultado = supervisor.avaliar(tecnicas_de_vendas)

    assert resultado["aprovado"] is False
    assert resultado["checks"]["fit_minimo"] is True
    assert resultado["checks"]["correspondencia_aceitavel"] is False
    assert resultado["alertas"]


def test_avaliar_lote_processa_todos_os_resultados():

    matcher = PortfolioMatcher()
    supervisor = Supervisor()

    resultados = matcher.recomendar("Alimentos", areas=3, produtos_por_area=3)

    avaliacoes = supervisor.avaliar_lote(resultados)

    assert len(avaliacoes) == len(resultados)
    assert all("aprovado" in avaliacao for avaliacao in avaliacoes)
