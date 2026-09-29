import pandas as pd

from src.tools.relacionamento import (
    aplicar_na_base,
    atendimento_por_ano,
    porte_fiea_por_raiz,
    ranking_produtos,
    resumo_por_cnpj,
    resumo_por_raiz,
    vendas,
)

HOJE = pd.Timestamp("2026-09-29")
CFG = {"meses_ativo": 24, "status_venda": ["Aceita"], "entidades": ["SESI", "SENAI"]}


def _prop():
    linhas = [  # cnpj, entidade, status, data, valor, produto, porte
        ("11111111000110", "SENAI", "Aceita", "2026-05-01", 1000, "Consultoria", "2. Médio"),
        ("11111111000200", "SESI", "Aceita", "2025-01-10", 500, "Saúde", "2. Médio"),     # filial da mesma raiz
        ("22222222000120", "SENAI", "Aceita", "2021-03-01", 300, "Educação Profissional", "4. Micro"),
        ("33333333000130", "SESI", "Cancelada", "2026-01-01", 900, "Saúde", "1. Grande"),
        ("44444444000140", "IEL", "Aceita", "2026-01-01", 900, "Estágio", ""),
    ]
    df = pd.DataFrame(linhas, columns=["cnpj", "Entidade", "Status", "data", "valor", "produto", "porte_fiea"])
    df["cnpj_basico"] = df["cnpj"].str[:8]
    df["data"] = pd.to_datetime(df["data"])
    df["ano"] = df["data"].dt.year
    df["porte_fiea"] = df["porte_fiea"].map({"2. Médio": "Média", "4. Micro": "Micro", "1. Grande": "Grande"}).fillna("")
    return df


def test_resumo_por_raiz_e_situacao():
    r = resumo_por_raiz(vendas(_prop(), CFG), HOJE, 24).set_index("cnpj_basico")
    assert set(r.index) == {"11111111", "22222222"}            # cancelada e IEL não contam
    a = r.loc["11111111"]
    assert bool(a["TEM_SESI"]) and bool(a["TEM_SENAI"]) and a["SITUACAO_CLIENTE"] == "Ativo"
    assert str(a["ULTIMA_COMPRA"]) == "2026-05-01" and a["QTD_CNPJS_ATENDIDOS"] == 2 and a["VALOR_ACEITO_TOTAL"] == 1500
    assert r.loc["22222222", "SITUACAO_CLIENTE"] == "Inativo"


def test_aplicar_na_base_por_raiz_e_por_cnpj():
    v = vendas(_prop(), CFG)
    base = pd.DataFrame({"cnpj": ["11111111000110", "11111111000300", "33333333000130"],
                         "CNPJ_BASICO": ["11111111", "11111111", "33333333"],
                         "OPORTUNIDADE_GERAL": ["PROSPECT"] * 3})
    b = aplicar_na_base(base, resumo_por_raiz(v, HOJE, 24), resumo_por_cnpj(v, HOJE, 24))
    assert list(b["TEM_SESI"]) == ["True", "True", "False"]        # a raiz inteira herda
    assert list(b["CNPJ_ATENDIDO"]) == ["Sim", "Não", "Não"]         # a unidade 0003 não comprou
    assert list(b["STATUS_RELACIONAMENTO"]) == ["SESI + SENAI", "SESI + SENAI", "SEM RELACIONAMENTO"]
    assert list(b["SITUACAO_CLIENTE"]) == ["Ativo", "Ativo", "Sem compra"]
    assert list(b["OPORTUNIDADE_GERAL"]) == ["CLIENTE", "CLIENTE", "PROSPECT"]


def test_agregados_e_porte():
    p = _prop()
    v = vendas(p, CFG)
    rk = ranking_produtos(v, {"11111111"}, HOJE, 24).set_index(["produto", "Entidade", "industria_base"])
    assert rk.loc[("Consultoria", "SENAI", True), "empresas_recentes"] == 1
    assert rk.loc[("Educação Profissional", "SENAI", False), "empresas_recentes"] == 0
    anos = atendimento_por_ano(v, {"11111111"})
    assert set(anos["ano"]) == {2021, 2025, 2026}
    porte = porte_fiea_por_raiz(p).set_index("cnpj_basico")["porte_fiea"].to_dict()
    assert porte == {"11111111": "Média", "22222222": "Micro", "33333333": "Grande"}


def test_exportacao_sem_coluna_da_erro_claro(tmp_path):
    import pytest
    from src.tools.relacionamento import carregar_propostas
    arq = tmp_path / "p.xlsx"
    pd.DataFrame({"CNPJ": ["11111111000110"], "Status": ["Aceita"]}).to_excel(arq, index=False)
    with pytest.raises(ValueError, match="Entidade"):
        carregar_propostas(arq)
