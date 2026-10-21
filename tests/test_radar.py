from datetime import date, datetime

import pandas as pd

from src.sinais.ibge import ler_sidra
from src.sinais.mercado import setor_cni
from src.sinais.noticias import (achar_municipio, casar_empresa, cita_alagoas, classificar, indice_empresas,
                                 juntar_historico, ler_rss, normalizar, processar)

CFG = {
    "consultas": ["Alagoas fábrica"],
    "contexto_empresarial": ["industria", "fabrica", "empresa", "usina"],
    "temas": [
        {"id": "incentivo", "tipo_sinal": "noticia_incentivo", "rotulo": "Incentivo", "peso": 4,
         "validade_dias": 120, "palavras": ["incentivo fiscal", "prodesin"]},
        {"id": "expansao", "tipo_sinal": "noticia_expansao", "rotulo": "Expansão", "peso": 4,
         "validade_dias": 120, "palavras": ["nova fabrica", "ampliacao"]},
        {"id": "contratacao", "tipo_sinal": "noticia_contratacao", "rotulo": "Contratação", "peso": 3,
         "validade_dias": 60, "palavras": ["vagas"]},
    ],
    "nomes_genericos": ["industria", "alagoas", "usina", "alimentos"],
}

EMPRESAS = pd.DataFrame([
    {"cnpj_basico": "11111111", "cnpj": "11111111000101", "razao_social": "SOCOCO S/A INDUSTRIAS ALIMENTICIAS",
     "nome_fantasia": "", "municipio": "Maceió", "Porte": "DEMAIS",
     "STATUS_RELACIONAMENTO_REAL": "Sem relacionamento", "tipo_empresa": "Indústria"},
    {"cnpj_basico": "22222222", "cnpj": "22222222000101", "razao_social": "USINA SANTA CLOTILDE S/A",
     "nome_fantasia": "", "municipio": "Rio Largo", "Porte": "DEMAIS",
     "STATUS_RELACIONAMENTO_REAL": "SESI + SENAI", "tipo_empresa": "Indústria"},
    {"cnpj_basico": "33333333", "cnpj": "33333333000101", "razao_social": "12.345.678 JOAO DA SILVA",
     "nome_fantasia": "", "municipio": "Arapiraca", "Porte": "MICRO EMPRESA",
     "STATUS_RELACIONAMENTO_REAL": "Sem relacionamento", "tipo_empresa": "Indústria"},
])

RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Sococo anuncia ampliacao de fabrica em Maceio - G1</title>
<link>https://news.google.com/x</link><pubDate>Sat, 18 Oct 2026 10:00:00 GMT</pubDate>
<description>&lt;a href="x"&gt;Sococo&lt;/a&gt; investe</description><source url="https://g1.globo.com">G1</source></item>
</channel></rss>"""


def _n(titulo, dia=18):
    return {"titulo": titulo, "resumo": "", "url_fonte": "http://x", "veiculo": "G1",
            "data_publicacao": datetime(2026, 10, dia), "consulta": "q"}


def test_ler_rss_tira_o_veiculo_do_titulo():
    itens = ler_rss(RSS, "q")
    assert itens[0]["titulo"] == "Sococo anuncia ampliacao de fabrica em Maceio"
    assert itens[0]["veiculo"] == "G1" and itens[0]["data_publicacao"].year == 2026


def test_municipio_mais_longo_primeiro():
    assert achar_municipio(normalizar("Obra na Barra de São Miguel")) == "Barra de São Miguel"
    assert cita_alagoas(normalizar("Fábrica em Arapiraca")) and not cita_alagoas(normalizar("Fábrica em Recife"))


def test_classifica_pelo_tema_mais_especifico():
    assert classificar(normalizar("Prodesin aprova incentivo para nova fábrica"), CFG)["id"] == "incentivo"
    assert classificar(normalizar("Empresa abre vagas"), CFG)["id"] == "contratacao"
    assert classificar(normalizar("Empresa muda logotipo"), CFG) is None


def test_casa_empresa_pelo_nome_raro_no_municipio_certo():
    idx = indice_empresas(EMPRESAS, {normalizar(g) for g in CFG["nomes_genericos"]})
    assert casar_empresa(normalizar("Sococo amplia fabrica em Maceio"), "Maceió", idx)["cnpj_basico"] == "11111111"
    # mesma palavra, outro município: não arrisca, manda revisar
    assert casar_empresa(normalizar("Sococo em Penedo"), "Penedo", idx)["casamento"] == "a revisar"
    # MEI com nome de pessoa nunca entra no índice
    assert casar_empresa(normalizar("Joao da Silva fala em Arapiraca"), "Arapiraca", idx)["casamento"] == "sem empresa"


def test_processar_filtra_alagoas_e_pontua():
    df = processar([_n("Sococo anuncia ampliação de fábrica em Maceió"), _n("Fábrica nova em Recife"),
                    _n("Usina Santa Clotilde abre vagas em Rio Largo", 20)], EMPRESAS, CFG, date(2026, 10, 21))
    assert len(df) == 2
    sococo = df[df["cnpj_basico"] == "11111111"].iloc[0]
    assert sococo["tipo_sinal"] == "noticia_expansao" and sococo["municipio"] == "Maceió"
    assert sococo["score_momento"] > 0 and bool(sococo["na_base_mestre"])


def test_historico_nao_duplica_e_descarta_vencidos():
    novo = processar([_n("Sococo anuncia ampliação de fábrica em Maceió")], EMPRESAS, CFG, date(2026, 10, 21))
    velho = novo.assign(descricao="Fábrica antiga em Maceió", data_publicacao=pd.Timestamp("2026-01-01"))
    out = juntar_historico(novo, pd.concat([novo, velho]), date(2026, 10, 21), 120)
    assert len(out) == 1


def test_ler_sidra_fica_com_ano_mais_recente_com_valor():
    js = [{"D1C": "cod"},
          {"D1C": "2704302", "D1N": "Maceió - AL", "V": "...", "D3N": "2023"},
          {"D1C": "2704302", "D1N": "Maceió - AL", "V": "9432", "D3N": "2021"},
          {"D1C": "2700300", "D1N": "ARAPIRACA - AL", "V": "100", "D3N": "2023"}]
    df = ler_sidra(js, "vab_industria_mil").set_index("cod_ibge")
    assert df.loc["2704302", "vab_industria_mil"] == 9432 and df.loc["2704302", "ano_vab_industria_mil"] == "2021"
    assert df.loc["2700300", "municipio"] == "Arapiraca"


def test_setor_cni_pela_divisao_cnae():
    assert setor_cni("1094-5/00") == "Indústria da Transformação"
    assert setor_cni("3600-6/01") == "Serviços Industriais de Utilidade Pública"
    assert setor_cni("4120-4/00") == "Indústria da Construção"
    assert setor_cni("0810-0/01") == "Indústria Extrativa"
    assert setor_cni("6201-5/01") == "Outros enquadrados pela CNI"


def test_palavra_comum_minuscula_nao_vira_empresa():
    emp = pd.concat([EMPRESAS, pd.DataFrame([
        {"cnpj_basico": "44444444", "cnpj": "44444444000101", "razao_social": "EMPREGOS MATCH LTDA",
         "nome_fantasia": "", "municipio": "Maceió", "Porte": "DEMAIS",
         "STATUS_RELACIONAMENTO_REAL": "Sem relacionamento", "tipo_empresa": "Não indústria"},
        {"cnpj_basico": "55555555", "cnpj": "55555555000101", "razao_social": "USINA CAETE S A",
         "nome_fantasia": "", "municipio": "São Miguel dos Campos", "Porte": "DEMAIS",
         "STATUS_RELACIONAMENTO_REAL": "SESI + SENAI", "tipo_empresa": "Indústria"}])], ignore_index=True)
    df = processar([_n("Alagoas prevê vagas e 4 mil empregos na indústria"),
                    _n("Usina Caeté anuncia ampliação em São Miguel dos Campos")], emp, CFG, date(2026, 10, 21))
    por = dict(zip(df["descricao"].str[:10], df["casamento"]))
    assert por["Alagoas pr"] == "sem empresa"
    assert df[df["casamento"] == "por nome"]["cnpj_basico"].tolist() == ["55555555"]
