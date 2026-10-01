import pandas as pd

from src.tools.colaboradores import arredondar, calcular, faixa, texto


def test_faixa_e_arredondamento():
    assert faixa(5) == "até 9" and faixa(25) == "20 a 49" and faixa(1200) == "1.000 ou mais"
    assert arredondar(3.4, True) == 4 and arredondar(23, True) == 25 and arredondar(23, False) == 20
    assert arredondar(0.2, False) == 1


def test_real_soma_unidades_e_estima_o_resto():
    n = 120
    univ = pd.DataFrame({"cnpj_basico": [f"{i:08d}" for i in range(n)],
                         "porte": ["DEMAIS" if i % 2 else "MICRO EMPRESA" for i in range(n)],
                         "div": ["10"] * n, "classe": ["1052"] * n, "unidades": [1] * n, "municipio": ["Maceió"] * n})
    real = pd.DataFrame({"cnpj": [f"{i:08d}000100" for i in range(100)] + ["00000001000200"],
                         "colaboradores": [200 if i % 2 else 5 for i in range(100)] + [50.0]})
    out = calcular(univ, real).set_index("cnpj_basico")
    assert out.loc["00000001", "colaboradores"] == 250              # matriz 200 + filial 50
    assert out.loc["00000001", "origem_colaboradores"] == "Solução 360"
    est = out.loc["00000101"]                                         # DEMAIS sem dado
    assert est["origem_colaboradores"] == "Estimado" and est["colab_min"] < est["colab_max"]
    assert est["colab_max"] > out.loc["00000100", "colab_max"]       # DEMAIS estimada maior que micro


def test_texto_na_tela():
    assert texto({"origem_colaboradores": "Solução 360", "colaboradores": 25, "faixa_colaboradores": "20 a 49"}, True) == "25"
    assert texto({"origem_colaboradores": "Solução 360", "colaboradores": "", "faixa_colaboradores": "20 a 49"}, False) == "20 a 49"
    assert texto({"origem_colaboradores": "Estimado", "faixa_colaboradores": "entre 4 e 30"}, False) == "entre 4 e 30 (estimado)"
