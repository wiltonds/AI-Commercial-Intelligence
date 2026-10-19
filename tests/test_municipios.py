import pandas as pd

from src.tools.municipios import MUNICIPIOS_AL, padronizar, padronizar_df


def test_lista_tem_os_102_municipios():
    assert len(set(MUNICIPIOS_AL)) == 102


def test_variacoes_viram_a_grafia_oficial():
    s = pd.Series(["ARAPIRACA", "Arapiraca", "MACEIO", "Sao Miguel Dos Campos", "Olho D'Agua Das Flores"])
    assert padronizar(s).tolist() == ["Arapiraca", "Arapiraca", "Maceió", "São Miguel dos Campos",
                                      "Olho d'Água das Flores"]


def test_o_que_nao_e_municipio_de_al_fica_igual():
    s = pd.Series(["NÃO INFORMADO", "", None, "Recife"])
    out = padronizar(s)
    assert out.iloc[0] == "NÃO INFORMADO" and out.iloc[1] == "" and pd.isna(out.iloc[2]) and out.iloc[3] == "Recife"


def test_padroniza_todas_as_colunas_de_municipio_menos_codigo():
    df = pd.DataFrame({"Municipio": ["ARAPIRACA"], "SEBRAE_Municipio": ["PENEDO"], "municipio_codigo": ["2700300"]})
    padronizar_df(df)
    assert df.iloc[0].tolist() == ["Arapiraca", "Penedo", "2700300"]
