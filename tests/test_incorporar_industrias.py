import shutil

import pandas as pd
import pytest

from src.tools.company_data import BASE_PATH


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    from jobs import incorporar_industrias_novas as j
    base = tmp_path / "BASE.csv"
    shutil.copy(BASE_PATH, base)
    amp = tmp_path / "AMP.csv"
    pd.DataFrame({
        "cnpj": ["11111111000110", "22222222000120", "33333333000130", "44444444000140"],
        "cnpj_basico": ["11111111", "22222222", "33333333", "44444444"],
        "razao_social": ["RESIDENCIAL MAR SPE LTDA", "PADARIA NOVA LTDA", "OBRAS AL LTDA", "SUPERMERCADO X"],
        "nome_fantasia": ["", "", "", ""],
        "Tipo": ["Indústria fora da Base Mestre"] * 3 + ["Não indústria"],
        "Municipio": ["Maceio", "Arapiraca", "Marechal Deodoro", "Maceio"],
        "Porte": ["PEQUENO PORTE", "DEMAIS", "PEQUENO PORTE", "DEMAIS"],
        "cnae_principal": ["4110700", "1091102", "4120400", "4711302"],
        "CNAE PRIMARIO": ["Incorporação de empreendimentos imobiliários", "Fabricação de produtos de padaria",
                          "Construção de edifícios", "Supermercados"],
        "data_inicio_atividade": ["20260315", "20250101", "20260601", "20100101"],
        "POSSUI_SESI": ["False", "True", "False", "False"], "POSSUI_SENAI": ["False"] * 4,
    }).to_csv(amp, index=False)
    monkeypatch.setattr(j, "BASE_PATH", base)
    monkeypatch.setattr(j, "ARQ_AMPLIADA", amp)
    monkeypatch.setattr(j, "PASTA_LISTA", tmp_path)
    monkeypatch.setattr(j, "carregar_contatos", lambda: pd.DataFrame(
        {"cnpj_basico": ["22222222"], "telefone_1": ["(82) 3221-1234"], "whatsapp_provavel": [""],
         "email": ["padaria@x.com"], "decisor": ["Ana Lima"]}))
    return j, base, amp, tmp_path


def test_incorpora_e_gera_lista(ambiente, monkeypatch):
    j, base, amp, pasta = ambiente
    antes = pd.read_csv(base, dtype=str, low_memory=False)
    monkeypatch.setattr("sys.argv", ["x", "--competencia", "2026-07"])
    j.main()
    depois = pd.read_csv(base, dtype=str, low_memory=False)
    assert len(depois) == len(antes) + 3
    novas = depois[depois["ORIGEM_REGISTRO"] == "Receita 2026-07 (incorporada)"].set_index("CNPJ_BASICO")
    assert (depois["ORIGEM_REGISTRO"] == "Base Mestre (BI_Project)").sum() == len(antes)
    obra = novas.loc["33333333"]
    assert obra["Municipio"] == "Marechal Deodoro" and obra["SETOR"] == "INDÚSTRIA"
    assert isinstance(obra["SEBRAE_setor"], str) and obra["SEBRAE_setor"] != ""       # copiado da base
    assert obra["STATUS_RELACIONAMENTO"] == "SEM RELACIONAMENTO" and obra["OPORTUNIDADE_GERAL"] == "PROSPECT"
    pad = novas.loc["22222222"]
    assert pad["STATUS_RELACIONAMENTO"] == "SOMENTE SESI" and pad["OPORTUNIDADE_CROSS_SELL"] == "SENAI"
    assert pad["Municipio"] == "Arapiraca" and pad["SEBRAE_cnae_divisao"] == "10.0"
    assert list(pd.read_csv(amp, dtype=str)["cnpj_basico"]) == ["44444444"]       # saem da base ampliada
    lista = pd.read_excel(pasta / "INDUSTRIAS_NOVAS_202607.xlsx", dtype=str)
    assert list(lista["CNPJ"])[0] == "33333333000130"                              # mais recente primeiro
    assert lista.set_index("CNPJ").loc["22222222000120", "Responsável"] == "Ana Lima"
    assert lista.set_index("CNPJ").loc["11111111000110", "SPE"] == "Sim"

    j.main()                                                                      # rodar de novo não duplica
    assert len(pd.read_csv(base, dtype=str, low_memory=False)) == len(antes) + 3
