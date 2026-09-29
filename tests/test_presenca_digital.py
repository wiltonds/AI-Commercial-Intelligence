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
