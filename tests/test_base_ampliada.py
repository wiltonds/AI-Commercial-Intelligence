import zipfile

import pandas as pd
import pytest

from src.tools.contatos import carregar_contatos
from src.tools.receita_cnpj import COLS_ESTAB, carregar_regua_industria, faixa_colaboradores, tipo_empresa
from src.tools.universo_ampliado import anotar_industrias, carregar_ampliada, opcoes_faixa


def _estab(basico, ordem, matriz, uf, situacao, cnae, email="", tel="32211234", inicio="20100101"):
    v = dict.fromkeys(COLS_ESTAB, "")
    v.update(cnpj_basico=basico, cnpj_ordem=ordem, cnpj_dv="10", matriz_filial=matriz, situacao=situacao,
             cnae_principal=cnae, uf=uf, municipio_codigo="2785", ddd_1="82", telefone_1=tel,
             email=email, data_inicio_atividade=inicio, nome_fantasia="FANTASIA " + basico)
    return ";".join(f'"{v[c]}"' for c in COLS_ESTAB)


def _zip(pasta, nome, linhas):
    with zipfile.ZipFile(pasta / nome, "w") as z:
        z.writestr(nome.replace(".zip", ".CSV"), "\n".join(linhas).encode("latin-1"))


@pytest.fixture
def pasta(tmp_path):
    _zip(tmp_path, "Estabelecimentos0.zip", [
        _estab("11111111", "0001", "1", "AL", "02", "4711302", "CONTATO@MERCADO.COM.BR"),  # supermercado DEMAIS
        _estab("11111111", "0002", "2", "AL", "02", "4711302"),                             # filial: mesma empresa
        _estab("22222222", "0001", "1", "AL", "02", "8610101"),                             # hospital EPP
        _estab("33333333", "0001", "1", "AL", "02", "4781400"),                             # loja ME -> fora
        _estab("44444444", "0001", "1", "PE", "02", "4711302"),                             # outro estado
        _estab("55555555", "0001", "1", "AL", "08", "4711302"),                             # baixada
        _estab("66666666", "0001", "1", "AL", "02", "8411600"),                             # prefeitura -> fora
        _estab("77777777", "0001", "1", "AL", "02", "2511000", "fabrica@x.com"),            # indústria da Base Mestre
        _estab("88888888", "0001", "1", "AL", "02", "7112000"),                             # engenharia: DN, fora da base
    ])
    emp = lambda b, nome, nat, porte: ";".join(f'"{x}"' for x in [b, nome, nat, "49", "1000,00", porte, ""])
    _zip(tmp_path, "Empresas0.zip", [
        emp("11111111", "SUPERMERCADO ALAGOAS LTDA", "2062", "05"),
        emp("22222222", "HOSPITAL MACEIO LTDA", "2062", "03"),
        emp("33333333", "LOJINHA ME", "2135", "01"),
        emp("66666666", "MUNICIPIO DE MACEIO", "1244", "05"),
        emp("77777777", "METALURGICA X", "2062", "05"),
        emp("88888888", "ENGENHARIA Y LTDA", "2062", "03"),
    ])
    _zip(tmp_path, "Municipios.zip", ['"2785";"MACEIO"'])
    _zip(tmp_path, "Cnaes.zip", ['"4711302";"Comércio varejista de mercadorias em geral - supermercados"',
                                 '"8610101";"Atividades de atendimento hospitalar"'])
    _zip(tmp_path, "Naturezas.zip", ['"2062";"Sociedade Empresária Limitada"'])
    return tmp_path


@pytest.fixture
def job(monkeypatch, tmp_path):
    from jobs import carregar_base_ampliada as j
    mestre = tmp_path / "mestre.csv"
    pd.DataFrame({"CNPJ_BASICO": ["77777777", "99999999"],
                  "SEBRAE_cnae_norm": ["2511000.0", "7112000.0"]}).to_csv(mestre, index=False)
    monkeypatch.setattr(j, "BASE_PATH", mestre)
    rel = tmp_path / "rel.xlsx"
    pd.DataFrame({"CNPJ": ["22.222.222/0001-10"], "Porte": ["2.Média"], "COBERTURA": ["SESI"]}).to_excel(rel, index=False)
    monkeypatch.setattr(j, "ARQ_RELACIONAMENTO", rel)
    return j


def test_monta_nao_industrias_e_lacunas_de_al(pasta, job):
    amp, contatos = job.montar(pasta)
    assert set(amp["cnpj_basico"]) == {"11111111", "22222222", "88888888"}
    tipos = amp.set_index("cnpj_basico")["Tipo"]
    assert tipos["11111111"] == "Não indústria" and tipos["22222222"] == "Não indústria"
    assert tipos["88888888"] == "Indústria fora da Base Mestre"          # CNAE da Tabela DN, sem estar na base
    sup = amp.set_index("cnpj_basico").loc["11111111"]
    assert sup["Porte"] == "DEMAIS" and sup["Municipio"] == "Maceio" and sup["QTD_ESTABELECIMENTOS"] == 2
    assert sup["cnpj"] == "11111111000110"                                  # matriz, não a filial
    assert sup["CNAE PRIMARIO"].startswith("Comércio varejista")
    assert "email" not in amp.columns                                       # contatos ficam fora do arquivo público
    hosp = amp.set_index("cnpj_basico").loc["22222222"]
    assert hosp["Colaboradores (faixa)"] == "50 a 99" and bool(hosp["POSSUI_SESI"])
    assert set(contatos["cnpj_basico"]) == {"11111111", "22222222", "77777777", "88888888"}
    assert contatos.set_index("cnpj_basico").loc["11111111", "email"] == "contato@mercado.com.br"


def test_faixas_e_regua(tmp_path):
    assert faixa_colaboradores("Indústria", "Média") == "100 a 499"
    assert faixa_colaboradores("Não indústria", "Pequena") == "10 a 49"
    assert faixa_colaboradores("Não indústria", "") == ""
    dn = tmp_path / "tabela_dn.csv"
    pd.DataFrame({"CNAE": ["4520-0/01", "7112000"], "descricao": ["Reparação", "Engenharia"]}).to_csv(dn, index=False)
    regua, origem = carregar_regua_industria(dn)
    assert regua == {"4520001", "7112000"} and origem.startswith("Tabela DN")
    assert tipo_empresa("4520001", False, regua) == "Indústria fora da Base Mestre"
    assert tipo_empresa("4711302", False, regua) == "Não indústria"
    assert tipo_empresa("4711302", True, regua) == "Indústria"               # a Base Mestre sempre manda
    with pytest.raises(FileNotFoundError):
        carregar_regua_industria(tmp_path / "x.csv", tmp_path / "y.csv")


def test_contatos_da_receita_complementam_o_robo(tmp_path):
    robo = tmp_path / "robo.csv"
    pd.DataFrame([{"cnpj_basico": "11111111", "cnpj": "11111111000110", "telefone_1": "(82) 3221-1234",
                   "email": "", "decisor": "Ana Lima", "whatsapp_provavel": ""}]).to_csv(robo, index=False)
    rec = tmp_path / "rec.csv"
    pd.DataFrame([{"cnpj_basico": "11111111", "cnpj": "11111111000110", "telefone_1": "", "telefone_2": "",
                   "email": "contato@mercado.com.br"},
                  {"cnpj_basico": "22222222", "cnpj": "22222222000110", "telefone_1": "(82) 99988-7766",
                   "telefone_2": "", "email": ""}]).to_csv(rec, index=False)
    c = carregar_contatos(robo, rec).set_index("cnpj_basico")
    assert c.loc["11111111", "email"] == "contato@mercado.com.br"            # preencheu o vazio
    assert c.loc["11111111", "telefone_1"] == "(82) 3221-1234"               # não sobrescreveu
    assert c.loc["11111111", "confianca"] == "alta"
    assert c.loc["22222222", "whatsapp_provavel"] == "(82) 99988-7766"       # empresa nova, sem decisor
    assert c.loc["22222222", "confianca"] == "media"
    assert carregar_contatos(robo, None).shape[0] == 1


def test_universo_do_explorador(pasta, job, tmp_path):
    amp, _ = job.montar(pasta)
    arq = tmp_path / "amp.csv"
    amp.to_csv(arq, index=False, encoding="utf-8-sig")
    nao = carregar_ampliada(arq)
    assert nao.set_index("cnpj_basico")["STATUS_RELACIONAMENTO_REAL"].to_dict() == {
        "11111111": "Sem relacionamento", "22222222": "Somente SESI", "88888888": "Sem relacionamento"}
    assert set(nao["Colaboradores (faixa)"]) == {"50 a 99", "Sem informação"}
    ind = anotar_industrias(pd.DataFrame({"cnpj": ["77777777000110"]}),
                            pd.DataFrame({"cnpj_basico": ["77777777"], "porte_fiea": ["Grande"]}))
    assert ind.iloc[0]["Colaboradores (faixa)"] == "500 ou mais" and ind.iloc[0]["Tipo"] == "Indústria"
    assert opcoes_faixa(pd.concat([nao, ind])["Colaboradores (faixa)"]) == ["50 a 99", "500 ou mais", "Sem informação"]
    assert carregar_ampliada(tmp_path / "nao_existe.csv").empty
