import pandas as pd

from jobs.enriquecer_digital import montar_fila, pesquisar
from src.tools.contatos import e_celular, normalizar_celular, segunda_passada, titular_firma_individual
from src.tools.presenca_digital import escolher_resultados, extrair_do_site, nome_de_busca, perfil_instagram


def test_celular_antigo_ganha_nono_digito():
    assert e_celular("(82) 8176-7041") and not e_celular("(82) 3221-1234")
    assert normalizar_celular("(82) 8176-7041") == "(82) 98176-7041"
    assert normalizar_celular("(82) 3221-1234") == "(82) 3221-1234"
    assert normalizar_celular("") == ""


def test_titular_de_firma_individual():
    assert titular_firma_individual("54.220.917 JOSE DA SILVA CRUZ") == "Jose Da Silva Cruz"
    assert titular_firma_individual("EMILLY OMENA CORREIA DE LUCENA") == "Emilly Omena Correia De Lucena"
    assert titular_firma_individual("F J DOS S MELO CONSTRUCAO") == ""
    assert titular_firma_individual("CONSTRUTORA ALAGOAS LTDA") == ""
    assert titular_firma_individual("SINALIZA") == ""


def test_segunda_passada():
    df = pd.DataFrame({
        "razao_social": ["54.220.917 JOSE DA SILVA CRUZ", "CONSTRUTORA X LTDA"],
        "telefone_1": ["(82) 8176-7041", "(82) 3221-1234"], "telefone_2": ["", ""],
        "email": ["", ""], "decisor": ["", ""], "decisor_cargo": ["", ""], "whatsapp_provavel": ["", ""],
    })
    out = segunda_passada(df)
    assert list(out["whatsapp_provavel"]) == ["(82) 98176-7041", ""]
    assert out.loc[0, "decisor"] == "Jose Da Silva Cruz" and out.loc[0, "decisor_cargo"].startswith("Titular")
    assert list(out["confianca"]) == ["alta", "media"]


def test_nome_e_instagram():
    assert nome_de_busca("CONSTRUTORA ALAGOAS LTDA") == "construtora alagoas"
    assert nome_de_busca("X LTDA", "Construal") == "construal"
    assert perfil_instagram("https://www.instagram.com/construal/?hl=pt") == "https://www.instagram.com/construal"
    assert perfil_instagram("https://www.instagram.com/p/Cx123/") == ""


def test_escolhe_site_e_instagram_ignorando_diretorios():
    org = [
        {"link": "https://cnpj.biz/12345678000190", "title": "CONSTRUAL - CNPJ"},
        {"link": "https://www.instagram.com/construal.al/", "title": "Construal (@construal.al)"},
        {"link": "https://www.outraempresa.com.br", "title": "Outra Empresa"},
        {"link": "https://www.construal.com.br/contato", "title": "Construal Engenharia"},
    ]
    r = escolher_resultados(org, "construal")
    assert r == {"site": "https://www.construal.com.br", "instagram": "https://www.instagram.com/construal.al"}


def test_extrai_do_site_prefere_email_do_dominio():
    html = ('<a href="mailto:contato@construal.com.br">x</a> fulano@gmail.com logo@2x.png '
            '<a href="https://instagram.com/construal.al">ig</a> <a href="https://wa.me/5582999887766">w</a>')
    r = extrair_do_site(html, "www.construal.com.br")
    assert r == {"email_site": "contato@construal.com.br", "instagram": "https://www.instagram.com/construal.al",
                 "whatsapp_site": "(82) 99988-7766"}


def test_pesquisar_com_buscas_falsas():
    chamadas = []

    def busca(q, chave):
        chamadas.append(q)
        if "instagram" in q:
            return [{"link": "https://www.instagram.com/construal.al/", "title": "Construal"}]
        return [{"link": "https://www.construal.com.br", "title": "Construal Engenharia"}]

    r = pesquisar({"razao_social": "CONSTRUAL LTDA", "nome_fantasia": "", "municipio": "Maceio"}, "k",
                  busca=busca, site=lambda url: "contato@construal.com.br")
    assert r["site"] == "https://www.construal.com.br" and r["email_site"] == "contato@construal.com.br"
    assert r["instagram"] == "https://www.instagram.com/construal.al" and len(chamadas) == 2


def test_fila_digital_prioriza_sinal_e_porte_e_pula_feitos():
    c = pd.DataFrame({"cnpj_basico": ["1", "2", "3", "4"], "digital_em": ["", "", "", "2026-09-28"]})
    fila = montar_fila(c, {"3"}, {"1": "MICRO EMPRESA", "2": "DEMAIS", "3": "MICRO EMPRESA"})
    assert list(fila["cnpj_basico"]) == ["3", "2", "1"]


# os 20 primeiros resultados reais (29/09/2026): o que deve ficar e o que deve sair
CASOS_REAIS = [
    ("ENGENHARQ LTDA", "https://engenharq.com.br", "https://www.instagram.com/engenharq_alagoas", True, True),
    ("UNICON CONSTRUCOES LTDA", "https://www.uniconconstrucoes.com.br", "https://www.instagram.com/unicon_engenharia", True, True),
    ("SOLIDEZ ENGENHARIA LTDA", "https://solidez-al.com.br", "https://www.instagram.com/solidezeng", True, True),
    ("ENGEMATLOC - TERRAPLENAGEM E LOCACOES LTDA", "https://prospectei.app.br", "https://www.instagram.com/x", False, False),
    ("EQUATORIAL ALAGOAS DISTRIBUIDORA DE ENERGIA S.A.", "https://al.equatorialenergia.com.br", "https://www.instagram.com/popular", True, False),
    ("METAL INFRAESTRUTURA LTDA", "https://www.perfill.com.br", "", False, False),
    ("SOLUCAO CONSTRUCOES E SERVICOS LTDA", "https://bamconstrucoes.com.br", "", False, False),
    ("CAVALCANTI FARIAS LTDA", "https://hipertms.com.br", "", False, False),
    ("F . P . CONSTRUTORA LTDA", "http://fpconstrutora-al.com.br", "https://www.instagram.com/fp.engenharia", True, True),
    ("LC ENGENHARIA E EMPREENDIMENTOS LTDA", "https://prospectei.app.br", "https://www.instagram.com/lcengenhariaeconstrucao", False, True),
    ("VERDE AMBIENTAL ALAGOAS S.A.", "https://www.verdealagoas.com.br", "https://www.instagram.com/verdealagoas", True, True),
    # sorteio de 15 do lote de 540
    ("NORDEPLAST INDUSTRIA E COMERCIO DE PLASTICOS LTDA", "https://www.lojaspapelaria.com.br", "https://www.instagram.com/nordeplastoficial", False, True),
    ("JOVENTINO FERREIRA DA SILVA", "https://www.alagoas24horas.com.br", "https://www.instagram.com/danieltineca", False, False),
    ("INCORPORADORA ALAMEDAS LTDA - EM RECUPERACAO JUDICIAL", "https://x.com.br", "https://www.instagram.com/alamedaempreendimentos", False, True),
    ("TRIUNFO AGROINDUSTRIAL LTDA EM RECUPERACAO JUDICIAL", "https://usinatriunfo.com.br", "https://www.instagram.com/triunfoagroindustrial", True, True),
    ("REI DA GLORIA TERRAS PLANAGENS E CONSTRUCOES LTDA", "https://cadastroempresa.com.br", "https://www.instagram.com/reidagloriaconst", False, True),
    ("JAIRO LYRA DE ANDRADE", "https://www.rededorsaoluiz.com.br", "https://www.instagram.com/dr.jairolyra", False, False),
    ("MRV ENGENHARIA E PARTICIPACOES SA", "https://www.perfill.com.br", "https://www.instagram.com/MRVENGENHARIA", False, True),
    ("CONSTRUTORA R PONTES LTDA", "https://rpontes.com.br", "https://www.instagram.com/construtorarpontes", True, True),
    ("COOPERATIVA DOS PRODUTORES DE DERIVADOS DE LEITE DE MAJOR ISIDORO E REGIAO - COOPDELMI",
     "https://www.sistemafaeal.org.br", "https://www.instagram.com/coopdelmi3808", False, True),
]


def test_regras_contra_os_20_casos_reais():
    for razao, site, ig, fica_site, fica_ig in CASOS_REAIS:
        org = [{"link": site, "title": razao}] + ([{"link": ig, "title": razao}] if ig else [])
        r = escolher_resultados(org, nome_de_busca(razao))
        assert bool(r["site"]) == fica_site, razao
        assert bool(r["instagram"]) == fica_ig, razao


def test_consorcio_nao_gasta_busca():
    from src.tools.presenca_digital import deve_buscar
    assert not deve_buscar("CONSORCIO CRECHES SEDUC/AL 2024.")
    chamadas = []
    r = pesquisar({"razao_social": "CONSORCIO PEDCAC"}, "k", busca=lambda q, k: chamadas.append(q) or [])
    assert chamadas == [] and r["digital_em"] != ""


def test_email_na_pagina_de_contato():
    paginas = {"https://www.construal.com.br": "<html>sem email</html>",
               "https://www.construal.com.br/contato": "fale: comercial@construal.com.br"}
    r = pesquisar({"razao_social": "CONSTRUAL LTDA", "municipio": "Maceio"}, "k",
                  busca=lambda q, k: [{"link": "https://www.construal.com.br", "title": "Construal"}],
                  site=lambda url: paginas.get(url, ""))
    assert r["email_site"] == "comercial@construal.com.br"


def test_firma_individual_com_nome_de_pessoa_nao_e_pesquisada():
    from src.tools.presenca_digital import deve_buscar
    assert not deve_buscar("JAIRO LYRA DE ANDRADE")
    assert not deve_buscar("54.220.917 JOSE DA SILVA CRUZ")
    assert deve_buscar("CONSTRUTORA R PONTES LTDA") and deve_buscar("NORDEPLAST INDUSTRIA E COMERCIO LTDA")


def test_revalidar_sem_busca():
    from jobs.enriquecer_digital import revalidar
    c = pd.DataFrame({
        "razao_social": ["MRV ENGENHARIA E PARTICIPACOES SA", "JAIRO LYRA DE ANDRADE", "CONSTRUTORA R PONTES LTDA"],
        "nome_fantasia": ["", "", ""],
        "site": ["https://www.perfill.com.br", "https://www.rededorsaoluiz.com.br", "https://rpontes.com.br"],
        "instagram": ["https://www.instagram.com/MRVENGENHARIA", "https://www.instagram.com/dr.jairolyra",
                      "https://www.instagram.com/construtorarpontes"],
        "email_site": ["x@perfill.com.br", "", "contato@rpontes.com.br"], "whatsapp_site": ["", "", ""],
        "digital_em": ["2026-09-29"] * 3,
    })
    out, sf, igf = revalidar(c)
    assert (sf, igf) == (2, 1)
    assert list(out["site"]) == ["", "", "https://rpontes.com.br"]
    assert list(out["email_site"]) == ["", "", "contato@rpontes.com.br"]
    assert list(out["instagram"]) == ["https://www.instagram.com/MRVENGENHARIA", "", "https://www.instagram.com/construtorarpontes"]
