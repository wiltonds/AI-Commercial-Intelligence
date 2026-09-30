import pandas as pd

from src.tools.hubs import chave_email, mapear_canais, mapear_grupos


def _univ():
    return pd.DataFrame({"cnpj_basico": [f"{i:08d}" for i in range(1, 9)],
                         "razao_social": [f"EMPRESA {i}" for i in range(1, 9)],
                         "segmento": ["Construcao"] * 4 + ["Industria de transformacao"] * 4,
                         "situacao": ["Ativo", "Sem compra", "Sem compra", "Sem compra", "Sem compra", "Inativo", "Sem compra", "Sem compra"]})


def test_chave_email_agrupa_dominio_proprio_e_nao_o_generico():
    assert chave_email("fiscal@contabilalagoas.com.br") == "@contabilalagoas.com.br"
    assert chave_email("Joao@GMAIL.com") == "joao@gmail.com"
    assert chave_email("") == ""


def test_canal_contabilidade_com_porta_de_entrada():
    c = pd.DataFrame({"cnpj_basico": [f"{i:08d}" for i in range(1, 9)],
                      "email": ["a@contabilalagoas.com.br", "b@contabilalagoas.com.br", "c@contabilalagoas.com.br",
                                "d@contabilalagoas.com.br", "e@contabilalagoas.com.br", "x@gmail.com", "y@gmail.com", ""],
                      "telefone_1": [""] * 8, "telefone_2": [""] * 8})
    h = mapear_canais(c, _univ(), minimo=5).set_index("hub")
    assert list(h.index) == ["@contabilalagoas.com.br"]              # gmail diferentes não viram hub
    x = h.loc["@contabilalagoas.com.br"]
    assert (x["empresas"], x["ja_clientes"], x["sem_compra"]) == (5, 1, 4)
    assert bool(x["porta_de_entrada"]) and bool(x["provavel_contabilidade"])


def test_grupo_por_socio_em_comum():
    c = pd.DataFrame({"cnpj_basico": ["00000001", "00000002", "00000003", "00000004"],
                      "socios": ["Ana Lima (Sócio-Administrador); Holding X Ltda (Sócio)", "Ana Lima (Sócio)",
                                 "ANA LIMA (Administrador)", "Pedro Souza (Sócio)"]})
    g = mapear_grupos(c, _univ(), minimo=3)
    assert list(g["hub"]) == ["Ana Lima"] and g.iloc[0]["empresas"] == 3
