from src.intelligence.cnae_classifier import CNAEClassificador


def test_classifica_alimentos():
    classificador = CNAEClassificador()

    resultado = classificador.classificar(
        "Fabricação de massas alimentícias"
    )

    assert resultado == "ALIMENTOS"


def test_classifica_construcao():
    classificador = CNAEClassificador()

    resultado = classificador.classificar(
        "Construção de edifícios"
    )

    assert resultado == "CONSTRUCAO"


def test_classifica_metal():
    classificador = CNAEClassificador()

    resultado = classificador.classificar(
        "Serviços de usinagem, tornearia e solda"
    )

    assert resultado == "METALMECANICA"


def test_nao_classifica_desconhecido():
    classificador = CNAEClassificador()

    resultado = classificador.classificar(
        "Atividades administrativas diversas"
    )

    assert resultado is None