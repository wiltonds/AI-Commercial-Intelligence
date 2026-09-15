from src.intelligence.sector_affinity import SectorAffinityEngine


def test_aderencia_construcao():

    engine = SectorAffinityEngine()

    recomendacoes = engine.recomendar("Construção")

    assert len(recomendacoes) > 0
    assert recomendacoes[0].area == "SESI SST & Saúde Ocupacional"
    assert recomendacoes[0].score == 95
def test_aderencia_alimentos():

    engine = SectorAffinityEngine()

    recomendacoes = engine.recomendar("Indústria de Alimentos")

    assert len(recomendacoes) > 0
    assert recomendacoes[0].area == "SESI SST & Ergonomia"
    assert recomendacoes[0].score == 92