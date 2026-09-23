import pandas as pd

from src.tools.company_data import BASE_PATH
from src.tools.cnpj_raiz import consolidar_por_cnpj_raiz, resumir_consolidacao


def _base_sintetica():
    return pd.DataFrame(
        {
            "cnpj": [
                "11111111000191",  # matriz, sem relacionamento
                "11111111000272",  # filial, com SESI
                "22222222000105",  # empresa única, sem filial
                "33333333000280",  # só filiais na base, nenhuma 0001
                "33333333000361",
            ],
            "situacao_atual": ["ATIVA", "ATIVA", "ATIVA", "ATIVA", "BAIXADA"],
            "CNPJ_BASICO": [
                "11111111",
                "11111111",
                "22222222",
                "33333333",
                "33333333",
            ],
            "POSSUI_SESI": [False, True, False, False, True],
            "POSSUI_SENAI": [False, False, True, False, False],
            "POSSUI_SEBRAE": [False, False, False, False, False],
        }
    )


def test_uma_linha_por_cnpj_raiz():
    df_empresas = consolidar_por_cnpj_raiz(_base_sintetica())

    assert len(df_empresas) == 3
    assert set(df_empresas["CNPJ_BASICO"]) == {"11111111", "22222222", "33333333"}


def test_representante_prefere_matriz_mas_herda_relacionamento_da_filial():
    df_empresas = consolidar_por_cnpj_raiz(_base_sintetica())
    linha = df_empresas.set_index("CNPJ_BASICO").loc["11111111"]

    assert linha["cnpj"] == "11111111000191"  # matriz, não a filial cliente
    assert linha["POSSUI_SESI"]  # herdado da filial
    assert linha["STATUS_RELACIONAMENTO_REAL"] == "Somente SESI"
    assert linha["QTD_ESTABELECIMENTOS"] == 2
    assert linha["QTD_FILIAIS"] == 1
    assert linha["TEM_FILIAL"]


def test_grupo_sem_matriz_0001_usa_estabelecimento_ativo_e_cliente():
    df_empresas = consolidar_por_cnpj_raiz(_base_sintetica())
    linha = df_empresas.set_index("CNPJ_BASICO").loc["33333333"]

    assert linha["cnpj"] == "33333333000361"  # ativa e já cliente, não a baixada


def test_empresa_sem_filial_fica_inalterada():
    df_empresas = consolidar_por_cnpj_raiz(_base_sintetica())
    linha = df_empresas.set_index("CNPJ_BASICO").loc["22222222"]

    assert not linha["TEM_FILIAL"]
    assert linha["QTD_ESTABELECIMENTOS"] == 1


def test_numeros_reais_da_base_mestre():
    df = pd.read_csv(BASE_PATH, dtype=str, low_memory=False)
    df["cnpj"] = df["cnpj"].str.replace(r"\D", "", regex=True).str.zfill(14)

    val = df["TEM_SESI"].fillna("").astype(str).str.strip().str.upper()
    df["POSSUI_SESI"] = val.isin(["TRUE", "1", "SIM", "S", "VERDADEIRO", "T", "YES"])
    val = df["TEM_SENAI"].fillna("").astype(str).str.strip().str.upper()
    df["POSSUI_SENAI"] = val.isin(["TRUE", "1", "SIM", "S", "VERDADEIRO", "T", "YES"])

    df_empresas = consolidar_por_cnpj_raiz(df)
    resumo = resumir_consolidacao(df, df_empresas)

    assert resumo["total_estabelecimentos"] == 14903
    assert resumo["total_empresas"] == 13978
    assert resumo["empresas_com_filial"] == 428
    assert resumo["total_filiais"] == 925
    assert int(
        (df_empresas["STATUS_RELACIONAMENTO_REAL"] != "Sem relacionamento").sum()
    ) == 766
