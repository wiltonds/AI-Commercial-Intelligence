from src.sinais.pncp_bim import eh_obra, escolher_documentos, linha, termos_bim


def test_eh_obra():
    assert eh_obra("Contratação de empresa para construção de creche tipo 1")
    assert eh_obra("Serviços de engenharia para reforma da escola municipal")
    assert not eh_obra("Contratação de mão de obra terceirizada de limpeza")
    assert not eh_obra("Aquisição de gêneros alimentícios para merenda")


def test_termos_bim():
    assert termos_bim("Os projetos deverão ser entregues em BIM, no formato IFC 4")
    assert termos_bim("metodologia Building Information Modeling")
    assert termos_bim("Modelagem da Informação da Construção (BIM)")
    assert not termos_bim("o bimestre e a bimestral; Bimbo")


def test_documentos_e_linha():
    docs = [{"titulo": "Aviso", "url": "u1"}, {"titulo": "Termo de Referência", "url": "u2"},
            {"titulo": "Edital", "url": "u3"}, {"titulo": "Planilha", "url": "u4"}]
    assert [d["url"] for d in escolher_documentos(docs, 2)] == ["u2", "u3"]
    ln = linha({"numeroControlePNCP": "X", "anoCompra": 2026, "sequencialCompra": 7, "dataPublicacaoPncp": "2026-09-01T10:00",
                "orgaoEntidade": {"cnpj": "123", "razaoSocial": "Município de Maceió", "esferaId": "M"},
                "unidadeOrgao": {"municipioNome": "Maceió"}, "objetoCompra": "Construção de UBS com projeto em BIM"}, 4)
    assert ln["esfera"] == "Municipal" and ln["bim_no_objeto"] and ln["url_pncp"].endswith("/123/2026/7")
