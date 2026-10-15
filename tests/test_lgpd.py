import pandas as pd

from src.tools.lgpd import limpar_cpf, sem_cpf


def test_tira_cpf_da_razao_social():
    assert sem_cpf("ABEL SERAFIM DA SILVA 02265288470") == "ABEL SERAFIM DA SILVA"
    assert sem_cpf("MARIA SOUZA 022.652.884-70") == "MARIA SOUZA"
    assert sem_cpf("ACME INDUSTRIA LTDA") == "ACME INDUSTRIA LTDA"
    assert sem_cpf("LOJA 2000 LTDA") == "LOJA 2000 LTDA"                    # número curto fica
    assert sem_cpf("HOLDING 12345678000199") == "HOLDING 12345678000199"    # CNPJ (14 dígitos) fica
    assert sem_cpf("") == ""


def test_limpar_cpf_so_mexe_nas_colunas_de_nome():
    df = pd.DataFrame({"cnpj_basico": ["02265288"], "razao_social": ["ABEL SILVA 02265288470"],
                       "nome_fantasia": ["ABEL 02265288470"], "obs": ["02265288470"]})
    out = limpar_cpf(df)
    assert out.loc[0, "razao_social"] == "ABEL SILVA" and out.loc[0, "nome_fantasia"] == "ABEL"
    assert out.loc[0, "obs"] == "02265288470" and out.loc[0, "cnpj_basico"] == "02265288"
    assert df.loc[0, "razao_social"] == "ABEL SILVA 02265288470"            # não altera o original
