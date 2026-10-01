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
    assert r.loc["9", "STI_status"] == "prospectar" and int(r.loc["9", "STI_pct"]) >= 10   # nunca comprou nada
    assert r.loc["5", "STI_status"] == "cross"            # compra SSI, não compra STI: cross-sell
    assert r.loc["4", "retomar_360"] == "STI"
    assert "STI" in r.loc["9", "oportunidades_360"] and r.loc["9", "STI_motivo"].startswith("Perfil")
    assert r.loc["5", "linhas_ativas"] == 1


def test_regras_obrigatoria_e_cota():
    cfg = {"meses_ativo": 24, "oportunidade_min_pct": 90, "suavizacao": 2,     # 90%: ninguém passa por "parecido"
           "linhas": {"SSI": {"entidade": "SESI", "produtos": ["Saúde"], "regra": "obrigatoria", "motivo": "NR"},
                      "EP": {"entidade": "SENAI", "produtos": ["Aprendizagem"], "regra": "cota", "motivo": "Cota"},
                      "STI": {"entidade": "SENAI", "produtos": ["Metrologia"], "regra": "parecido"}}}
    univ = pd.DataFrame({"cnpj_basico": ["a", "b", "c"], "classe": ["1052"] * 3, "div": ["10"] * 3,
                         "porte": ["DEMAIS", "MICRO EMPRESA", "DEMAIS"]})
    vendas = pd.DataFrame({"cnpj_basico": ["c"], "linha": ["STI"], "data": pd.to_datetime(["2026-01-01"])})
    r = calcular(univ, vendas, cfg, "2026-09-29").set_index("cnpj_basico")
    assert list(r["SSI_status"]) == ["prospectar", "prospectar", "cross"]       # obrigatória: todas
    assert r.loc["a", "SSI_motivo"] == "NR"
    assert list(r["EP_status"]) == ["prospectar", "baixa", "cross"]             # cota: só DEMAIS
    assert r.loc["a", "EP_motivo"] == "Cota"
    assert list(r["STI_status"]) == ["baixa", "baixa", "compra"]                # parecido: ninguém passou dos 90%


def test_config_real_tem_as_quatro_linhas_do_foco():
    cfg = carregar_linhas()
    assert list(cfg["linhas"]) == ["SSI", "EB", "STI", "EP"]
    assert {l["entidade"] for l in cfg["linhas"].values()} == {"SESI", "SENAI"}
