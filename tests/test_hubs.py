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


def test_classifica_tipos_de_canal():
    from src.tools.hubs import classificar_canal
    assert classificar_canal("@contabilalagoas.com.br", []) == "Contabilidade"
    assert classificar_canal("@alagoassst.com.br", []) == "Consultoria de SST"
    assert classificar_canal("@medicinadotrabalhoal.com.br", []) == "Consultoria de SST"
    assert classificar_canal("@legalizamais.com.br", []) == "Assessoria / despachante"
    assert classificar_canal("@grupoalfa.com.br", ["ALFA ALIMENTOS LTDA", "ALFA BEBIDAS LTDA", "ALFA LOG"]) == "Grupo empresarial"
    assert classificar_canal("(82) 3326-0000", []) == "Telefone compartilhado"
    assert classificar_canal("@xyz.com.br", ["EMPRESA A", "EMPRESA B"]) == "Outro"


def test_publico_so_dominio_de_empresa():
    from src.tools.hubs import publico
    c = pd.DataFrame({"hub": ["@contabil.com.br", "joao@gmail.com", "(82) 3326-0000"], "empresas": [9, 7, 6]})
    assert list(publico(c)["hub"]) == ["@contabil.com.br"]
