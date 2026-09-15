import pytest

from src.intelligence.portfolio_matcher import PortfolioMatcher
from src.agents.supervisor import Supervisor


"""
Dataset de avaliação: casos-limite descobertos manualmente durante o
desenvolvimento do PortfolioMatcher e do Supervisor.

Cada caso documenta uma decisão de aprovação/rejeição já validada por
inspeção humana. Servem como rede de segurança contra regressão quando
o algoritmo de match, os pesos de score ou os thresholds do Supervisor
mudarem — e como base para futuras métricas (precision@k) quando um
dataset de feedback real existir.
"""

CASOS_CONHECIDOS = [
    pytest.param(
        "Metalmecânica",
        "NR 12",
        True,
        "Correspondência textual de 100% com a área 'Segurança de "
        "Máquinas' — os dois termos da área aparecem no produto.",
        id="seguranca_maquinas_aprova_cobertura_total",
    ),
    pytest.param(
        "Alimentos",
        "GESTÃO DA QUALIDADE",
        True,
        "Cobertura de apenas 1 de 2 termos da área 'Qualidade e "
        "Laboratórios', mas o termo 'qualidade' é raro no catálogo "
        "(~0,8%) e sustenta a recomendação sozinho.",
        id="gestao_qualidade_aprova_termo_raro",
    ),
    pytest.param(
        "Construção",
        "TÉCNICAS DE VENDAS",
        False,
        "Único termo batido ('técnica') aparece em ~5,6% do catálogo — "
        "genérico demais para sustentar a recomendação sozinho, mesmo "
        "com fit combinado acima do mínimo.",
        id="tecnicas_de_vendas_rejeita_termo_generico",
    ),
    pytest.param(
        "Alimentos",
        "MECÂNICO DE MANUTENÇÃO DE MÁQUINAS INDUSTRIAIS",
        False,
        "Cobertura de apenas 1 de 3 termos (33%) da área 'Automação, "
        "Mecânica e Manutenção' — 'manutenção' sozinho é específico o "
        "bastante para passar em correspondência, mas não representa "
        "cobertura suficiente da área de afinidade.",
        id="manutencao_industrial_rejeita_cobertura_baixa",
    ),
    pytest.param(
        "Construção",
        "ATESTADO DE SAUDE OCUPACIONAL",
        False,
        "Termos batidos ('saúde', 'ocupacional') são ambos genéricos "
        "(>3% do catálogo) — nenhuma evidência específica sustenta "
        "o match, mesmo com 66% de cobertura.",
        id="aso_rejeita_termos_genericos",
    ),
]


@pytest.mark.parametrize(
    "setor, produto_contem, aprovado_esperado, motivo",
    CASOS_CONHECIDOS,
)
def test_supervisor_casos_conhecidos(
    setor,
    produto_contem,
    aprovado_esperado,
    motivo,
):
    matcher = PortfolioMatcher()
    supervisor = Supervisor()

    resultados = matcher.recomendar(setor, areas=10, produtos_por_area=50)

    produto = next(
        (
            resultado
            for resultado in resultados
            if produto_contem.upper() in resultado.produto.upper()
        ),
        None,
    )

    assert produto is not None, (
        f"Produto contendo '{produto_contem}' não apareceu no match "
        f"para o setor '{setor}' — o caso-limite pode ter mudado de "
        "forma (catálogo atualizado, área renomeada, matriz de "
        "afinidade alterada). Revise o caso antes de remover o teste."
    )

    avaliacao = supervisor.avaliar(produto)

    assert avaliacao["aprovado"] is aprovado_esperado, (
        f"{motivo}\n"
        f"Produto: {produto.produto}\n"
        f"Checks: {avaliacao['checks']}\n"
        f"Alertas: {avaliacao['alertas']}"
    )
