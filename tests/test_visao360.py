import pandas as pd

from src.tools.visao360 import calcular, carregar_linhas, marcar_linhas

CFG = {"meses_ativo": 24, "oportunidade_min_pct": 10, "suavizacao": 2,
       "linhas": {"SSI": {"entidade": "SESI", "nome": "SSI", "produtos": ["Saúde"]},
                  "STI": {"entidade": "SENAI", "nome": "STI", "produtos": ["Metrologia", "Consultoria"]}}}


def test_mapeia_produto_por_entidade():
    v = pd.DataFrame({"Entidade": ["SESI", "SENAI", "SENAI", "SESI"], "produto": ["Saúde", "Metrologia", "Saúde", "Locação De Espaços"]})
    linha = marcar_linhas(v, CFG)["linha"]
    assert list(linha[:2]) == ["SSI", "STI"] and linha[2:].isna().all()   # Saúde no SENAI não é SSI


def test_status_compra_parou_oportunidade():
    univ = pd.DataFrame({"cnpj_basico": [f"{i}" for i in range(10)], "classe": ["1052"] * 10, "div": ["10"] * 10,
                         "porte": ["DEMAIS"] * 10})
    vendas = pd.DataFrame({"cnpj_basico": ["0", "1", "2", "3", "4", "5"],
                           "linha": ["STI", "STI", "STI", "STI", "STI", "SSI"],
                           "data": pd.to_datetime(["2026-05-01", "2026-01-01", "2025-11-01", "2025-10-01", "2021-01-01", "2026-06-01"])})
    r = calcular(univ, vendas, CFG, "2026-09-29").set_index("cnpj_basico")
    assert r.loc["0", "STI_status"] == "compra" and r.loc["4", "STI_status"] == "parou"
    assert r.loc["9", "STI_status"] == "oportunidade" and int(r.loc["9", "STI_pct"]) >= 10   # 5 de 10 parecidas compram
    assert r.loc["4", "retomar_360"] == "STI"
    assert "STI" in r.loc["9", "oportunidades_360"]
    assert r.loc["5", "linhas_ativas"] == 1


def test_config_real_tem_as_quatro_linhas_do_foco():
    cfg = carregar_linhas()
    assert list(cfg["linhas"]) == ["SSI", "EB", "STI", "EP"]
    assert {l["entidade"] for l in cfg["linhas"].values()} == {"SESI", "SENAI"}
