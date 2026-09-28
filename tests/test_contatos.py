from datetime import datetime

import pandas as pd

from jobs.enriquecer_contatos import montar_fila
from src.tools.contatos import (
    avaliar_qualidade,
    e_celular,
    escolher_decisor,
    extrair_contato,
    formatar_telefone,
    juntar_contatos,
)

RESPOSTA = {  # formato real da BrasilAPI /api/cnpj/v1
    "cnpj": "12345678000190", "razao_social": "CONSTRUTORA ALAGOAS LTDA",
    "nome_fantasia": "CONSTRUAL", "descricao_situacao_cadastral": "ATIVA",
    "descricao_tipo_de_logradouro": "RUA", "logradouro": "DO COMERCIO", "numero": "100",
    "complemento": "", "bairro": "CENTRO", "cep": "57020-000", "municipio": "MACEIO", "uf": "AL",
    "ddd_telefone_1": "8232211234", "ddd_telefone_2": "82999887766", "email": "OBRAS@CONSTRUAL.COM.BR",
    "cnae_fiscal": 4120400, "cnae_fiscal_descricao": "Construção de edifícios",
    "cnaes_secundarios": [{"codigo": 4399103, "descricao": "Obras de alvenaria"},
                          {"codigo": 0, "descricao": ""}],
    "qsa": [
        {"identificador_de_socio": 1, "nome_socio": "HOLDING XYZ LTDA", "qualificacao_socio": "Sócio"},
        {"identificador_de_socio": 2, "nome_socio": "MARIA SOUZA", "qualificacao_socio": "Sócio"},
        {"identificador_de_socio": 2, "nome_socio": "JOAO SILVA", "qualificacao_socio": "Sócio-Administrador"},
    ],
}


def test_extrai_colunas_do_cadastro():
    c = extrair_contato(RESPOSTA)
    assert c["cnpj_basico"] == "12345678"
    assert c["telefone_1"] == "(82) 3221-1234"
    assert c["whatsapp_provavel"] == "(82) 99988-7766"
    assert c["email"] == "obras@construal.com.br"
    assert c["decisor"] == "Joao Silva" and c["decisor_cargo"] == "Sócio-Administrador"
    assert c["cnae_principal"] == "4120400 - Construção de edifícios"
    assert c["cnaes_secundarios"] == "4399103 - Obras de alvenaria"      # código 0 some
    assert c["endereco"].startswith("Rua Do Comercio, 100") and c["municipio"] == "Maceio"


def test_decisor_ignora_socio_pessoa_juridica_e_cai_no_primeiro_socio():
    qsa = [{"identificador_de_socio": 1, "nome_socio": "HOLDING SA", "qualificacao_socio": "Administrador"},
           {"identificador_de_socio": 2, "nome_socio": "ANA LIMA", "qualificacao_socio": "Sócio"}]
    assert escolher_decisor(qsa) == ("Ana Lima", "Sócio")
    assert escolher_decisor([]) == ("", "")


def test_telefones():
    assert formatar_telefone("82 3221-1234") == "(82) 3221-1234"
    assert formatar_telefone("123") == ""
    assert e_celular("(82) 99988-7766") and not e_celular("(82) 3221-1234")


def test_contador_derruba_confianca():
    base = pd.DataFrame({
        "telefone_1": ["(82) 3000-0000"] * 3 + ["(82) 3221-1234", ""],
        "telefone_2": ["", "", "", "", ""],
        "email": ["", "", "", "", "fiscal@escritoriocontabil.com.br"],
        "decisor": ["A", "B", "C", "D", "E"],
    })
    q = avaliar_qualidade(base)
    assert list(q["contato_de_contador"]) == [True, True, True, False, True]
    assert list(q["confianca"]) == ["baixa", "baixa", "baixa", "alta", "baixa"]
    assert avaliar_qualidade(base.assign(decisor=""))["confianca"].iloc[3] == "media"


def test_fila_prioriza_sinal_e_porte_e_pula_recentes():
    universo = pd.DataFrame({
        "cnpj_basico": ["1", "2", "3", "4"], "cnpj": ["a", "b", "c", "d"],
        "razao_social": ["A", "B", "C", "D"],
        "Porte": ["MICRO EMPRESA", "DEMAIS", "MICRO EMPRESA", "DEMAIS"],
    })
    contatos = pd.DataFrame({"cnpj_basico": ["4"], "atualizado_em": ["2026-09-20T10:00:00"]})
    fila = montar_fila(universo, contatos, {"3"}, 90, hoje=datetime(2026, 9, 28))
    assert list(fila["cnpj_basico"]) == ["3", "2", "1"]           # sinal > porte; "4" é recente
    assert list(montar_fila(universo, contatos, {"3"}, 90, so_sinais=True,
                            hoje=datetime(2026, 9, 28))["cnpj_basico"]) == ["3"]


def test_juntar_com_e_sem_arquivo():
    emp = pd.DataFrame({"cnpj_basico": ["12345678", "99999999"], "razao_social": ["X", "Y"]})
    vazio = juntar_contatos(emp, pd.DataFrame())
    assert "decisor_cargo" in vazio and (vazio["telefone_1"] == "").all()
    cont = avaliar_qualidade(pd.DataFrame([extrair_contato(RESPOSTA)]))
    out = juntar_contatos(emp, cont)
    assert out.loc[0, "decisor"] == "Joao Silva" and pd.isna(out.loc[1, "decisor"])
