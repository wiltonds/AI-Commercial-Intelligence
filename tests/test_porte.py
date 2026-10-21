import pandas as pd

from src.tools import porte


def test_texto_e_colaboradores():
    assert porte.de_texto("MICRO EMPRESA") == "MICRO"
    assert porte.de_texto("EMPRESA DE PEQUENO PORTE") == "PEQUENA"
    assert porte.de_texto("Média") == "MÉDIA"
    assert porte.de_texto("1. GRANDE") == "GRANDE"
    assert porte.de_texto("DEMAIS") == ""
    assert [porte.de_colaboradores(n) for n in (5, 19, 20, 99, 100, 499, 500)] == \
        ["MICRO", "MICRO", "PEQUENA", "PEQUENA", "MÉDIA", "MÉDIA", "GRANDE"]


def test_padronizar_so_quatro_classes(monkeypatch):
    monkeypatch.setattr(porte, "_referencias", lambda: ({"11111111": "GRANDE"}, {"22222222": "PEQUENA"}))
    cnpj = pd.Series(["11111111", "22222222", "33333333", "44444444", "55555555"])
    p = pd.Series(["MICRO EMPRESA", "DEMAIS", "DEMAIS", "PEQUENO PORTE", "MÉDIA"])
    assert porte.padronizar(cnpj, p).tolist() == ["GRANDE", "PEQUENA", "MÉDIA", "PEQUENA", "MÉDIA"]
    assert porte.opcoes(pd.Series(["GRANDE", "MICRO", "MÉDIA"])) == ["MICRO", "MÉDIA", "GRANDE"]
