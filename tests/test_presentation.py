from src.presentation import (
    CHECK_LABELS,
    classificar_aderencia,
    descrever_check,
    traduzir_evidencia,
)
from src.agents.supervisor import Supervisor
from src.intelligence.portfolio_matcher import PortfolioMatcher


def test_traduzir_evidencia_relacionamento():
    assert traduzir_evidencia("TEM_SESI=True") == "Já é cliente SESI"
    assert traduzir_evidencia("TEM_SESI=False") == "Ainda não é cliente SESI"
    assert traduzir_evidencia("TEM_SENAI=True") == "Já é cliente SENAI"


def test_traduzir_evidencia_setor():
    assert (
        traduzir_evidencia("Setor=ALIMENTOS")
        == "Setor identificado: ALIMENTOS"
    )


def test_traduzir_evidencia_area_afinidade():
    resultado = traduzir_evidencia(
        "Área de afinidade: SENAI Qualidade e Laboratórios (score 85)"
    )
    assert resultado == (
        "Área com maior aderência ao setor: SENAI Qualidade e Laboratórios"
    )


def test_traduzir_evidencia_esconde_detalhe_estatistico_do_modo_comercial():
    resultado = traduzir_evidencia(
        "Termo mais específico do match: 'qualidade' (presente em 29 de "
        "3712 produtos do catálogo)"
    )
    assert resultado is None


def test_traduzir_evidencia_desconhecida_mantem_texto_original():
    assert traduzir_evidencia("algo não mapeado") == "algo não mapeado"


def test_classificar_aderencia():
    assert classificar_aderencia(95) == "Alta"
    assert classificar_aderencia(70) == "Média"
    assert classificar_aderencia(50) == "Baixa"


def test_descrever_check_desconhecido_mantem_nome_original():
    assert descrever_check("check_novo_sem_label") == "check_novo_sem_label"


def test_check_labels_cobre_todos_os_checks_do_supervisor():
    """
    Roda o Supervisor de verdade e garante que nenhuma chave de
    `checks` fique sem descrição em CHECK_LABELS — se alguém adicionar
    um check novo no Supervisor e esquecer de documentar aqui, esse
    teste quebra em vez de o app mostrar o nome cru da chave.
    """

    matcher = PortfolioMatcher()
    supervisor = Supervisor()

    resultados = matcher.recomendar("Metalmecânica", areas=3, produtos_por_area=2)
    avaliacao = supervisor.avaliar(resultados[0])

    for nome_check in avaliacao["checks"]:
        assert nome_check in CHECK_LABELS, (
            f"Check '{nome_check}' não tem descrição em CHECK_LABELS."
        )
