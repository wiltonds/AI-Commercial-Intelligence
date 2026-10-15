import numpy as np
import pandas as pd

from src.tools.potencial import alertas, faixa, grupo_natureza, numero_br, pontuar, segmento_cnae
from src.tools.universo_comercial import A_CONFIRMAR, CLIENTE, MERCADO, filtrar, montar, porte_fiea_padrao


def test_segmento_e_faixa():
    assert segmento_cnae("10") == "Indústria de transformação"
    assert segmento_cnae("4120400") == "Construção"
    assert segmento_cnae("") == "Não classificado"
    assert [faixa(p) for p in (0.5, 0.2, 0.06, 0.01)] == ["Muito alto", "Alto", "Médio", "Baixo"]


def test_numero_natureza_alerta():
    assert numero_br("71918642,00") == 71918642.0
    assert numero_br("1.234,50") == 1234.5
    assert grupo_natureza("Sociedade Anônima Fechada") == "S.A."
    assert alertas("LAGINHA AGRO INDUSTRIAL S/A - FALIDO", True) == "Falência/recuperação judicial"
    assert alertas("OI S.A. - EM RECUPERACAO JUDICIAL", False).count("·") == 1
    assert alertas("ACME LTDA", True) == ""


def test_porte_fiea_nunca_vem_da_receita():
    assert porte_fiea_padrao("Pequena") == "EPP"
    assert porte_fiea_padrao("Grande") == "Demais"
    assert porte_fiea_padrao("") == A_CONFIRMAR
    assert porte_fiea_padrao(None) == A_CONFIRMAR


def _universo_sintetico(n=400, seed=0):
    rng = np.random.default_rng(seed)
    porte = rng.choice(["MICRO EMPRESA", "PEQUENO PORTE", "DEMAIS"], n)
    cliente = (porte == "DEMAIS") & (rng.random(n) < 0.6) | (rng.random(n) < 0.03)
    return pd.DataFrame({
        "cnpj_basico": [f"{i:08d}" for i in range(n)], "razao_social": [f"EMPRESA {i}" for i in range(n)],
        "Categoria": "Indústria", "Segmento": "Indústria de transformação", "divisao": "10", "cnae": "1091100",
        "Porte Receita": porte, "Município": "Maceió", "capital": rng.uniform(1e3, 1e7, n), "n_estab": 1,
        "natureza_grupo": "Ltda", "data_abertura": "20100101", "sede_em_al": True, "cliente": cliente,
    })


def test_pontuar_da_nota_so_para_quem_nao_e_cliente_e_aprende_o_perfil():
    u = _universo_sintetico()
    out, auc = pontuar(u)
    assert auc > 0.7
    assert out.loc[u["cliente"].values, "nota"].isna().all()
    sem = out[~u["cliente"].values]
    assert sem["nota"].notna().all() and sem["potencial"].ne("").all()
    demais = u.loc[~u["cliente"], "Porte Receita"].eq("DEMAIS").values
    assert sem.loc[demais, "nota"].mean() > sem.loc[~demais, "nota"].mean()


def test_montar_separa_clientes_e_mercado_com_as_duas_reguas():
    mestre = pd.DataFrame({
        "CNPJ_BASICO": ["11111111", "22222222"], "razao_social": ["CLIENTE IND", "NOVA IND"],
        "SEBRAE_cnae_norm": ["1091100.0", "2330301.0"], "CNAE PRIMARIO": ["Panificação", "Concreto"],
        "Porte": ["DEMAIS", "DEMAIS"], "Municipio": ["Maceió", "Arapiraca"],
        "POSSUI_SESI": [True, False], "POSSUI_SENAI": [False, False],
        "SITUACAO_CLIENTE": ["Ativo", "Sem compra"], "ULTIMA_COMPRA": ["2026-05-01", ""],
        "unidade_sesi": ["Farol", "Agreste/Sertão"], "unidade_senai": ["Poço", "Agreste/Sertão"],
        "unidades": ["Farol|Poço", "Agreste/Sertão"],
    })
    ampliada = pd.DataFrame({
        "cnpj_basico": ["33333333"], "razao_social": ["HOSPITAL X"], "cnae_principal": ["8610101"],
        "CNAE PRIMARIO": ["Hospital"], "Porte": ["DEMAIS"], "Municipio": ["Maceió"],
        "POSSUI_SESI": [False], "POSSUI_SENAI": [False], "SITUACAO_CLIENTE": ["Sem compra"],
        "unidade_sesi": ["Tabuleiro"], "unidade_senai": ["Poço"], "unidades": ["Tabuleiro|Poço"],
    })
    porte = pd.DataFrame({"cnpj_basico": ["11111111"], "porte_fiea": ["Pequena"]})
    pot = pd.DataFrame({"cnpj_basico": ["22222222", "33333333", "11111111"], "bairro": ["Centro", "Farol", "Jatiúca"],
                        "nota": [6.2, 1.0, 9.9], "potencial": ["Muito alto", "Baixo", "Muito alto"],
                        "motivo": ["m", "m", "m"], "alerta": ["", "", ""]})
    u = montar(mestre, ampliada, porte, pot).set_index("cnpj_basico")
    assert u.loc["11111111", "Relacionamento"] == CLIENTE
    assert u.loc["11111111", "Porte FIEA"] == "EPP" and u.loc["11111111", "Porte Receita"] == "DEMAIS"
    assert pd.isna(u.loc["11111111", "Nota"]) and u.loc["11111111", "Potencial"] == ""
    assert u.loc["22222222", "Relacionamento"] == MERCADO and u.loc["22222222", "Porte FIEA"] == A_CONFIRMAR
    assert u.loc["33333333", "Categoria"] == "Não indústria" and u.loc["33333333", "Segmento"] == "Saúde e serviços sociais"
    assert u.loc["22222222", "Segmento"] == "Indústria de transformação"
    uu = u.reset_index()
    assert set(filtrar(uu, unidades_sesi=["Farol"])["cnpj_basico"]) == {"11111111"}
    assert set(filtrar(uu, unidades_senai=["Poço"], categorias=["Não indústria"])["cnpj_basico"]) == {"33333333"}
    assert set(filtrar(uu, regua="FIEA", portes=[A_CONFIRMAR])["cnpj_basico"]) == {"22222222", "33333333"}
    assert set(filtrar(uu, regua="Receita", portes=["DEMAIS"])["cnpj_basico"]) == {"11111111", "22222222", "33333333"}
    assert set(filtrar(uu, bairros=["Centro"])["cnpj_basico"]) == {"22222222"}
