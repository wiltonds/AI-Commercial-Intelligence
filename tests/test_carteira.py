import pandas as pd

from src.tools.carteira import A_DEFINIR, bairro_minuta, carregar_minuta, distribuir, unidade_do_historico, unidade_pela_sede

B, M = carregar_minuta()


def test_bairros_de_maceio_pela_minuta():
    assert unidade_pela_sede("Maceio", "Farol", B, M)[:2] == ("Farol", "Poço")           # Cambona/Poço
    assert unidade_pela_sede("MACEIÓ", "Tab. dos Martins", B, M)[:2] == ("Tabuleiro", "Poço")  # BB -> Poço
    assert unidade_pela_sede("Maceio", "Bairro Inventado", B, M)[:2] == ("", "")


def test_municipios():
    assert unidade_pela_sede("Marechal Deodoro", "", B, M)[:2] == ("Farol", "Poço")
    assert unidade_pela_sede("Arapiraca", "Centro", B, M)[:2] == ("Agreste/Sertão", "Agreste/Sertão")
    assert unidade_pela_sede("Rio Largo", "", B, M)[:2] == ("Tabuleiro", "Poço")       # SENAI BB -> Poço


def test_alias_de_bairro():
    assert bairro_minuta("STELLA MARIS", B) == "JATIUCA"
    assert bairro_minuta("Cidade Univesitaria", B) == "CIDADE UNIVERSITARIA"


def test_unidade_do_historico():
    assert unidade_do_historico("SESI", "Farol") == "Farol"
    assert unidade_do_historico("SESI", "Sesi Cambona") == "Farol"
    assert unidade_do_historico("SENAI", "Benedito Bentes") == "Poço"
    assert unidade_do_historico("SENAI", "UNIDADE SESI/SENAI AGRESTE SERTÃO") == "Agreste/Sertão"
    assert unidade_do_historico("SESI", "Outro") == ""


def _end(linhas):
    return pd.DataFrame(linhas, columns=["cnpj", "cnpj_basico", "matriz", "bairro", "municipio"])


def test_preservacao_historico_e_nova():
    end = _end([("11111111000101", "11111111", "S", "Farol", "Maceio"),          # sede Farol
                ("22222222000102", "22222222", "S", "Benedito Bentes", "Maceio"),  # nova, sede Tabuleiro/BB
                ("33333333000203", "33333333", "N", "Centro", "Maceio")])          # só filial em AL
    hist = pd.DataFrame([("11111111", "SESI", "Tabuleiro"),                        # histórico SESI no Tabuleiro
                         ("11111111", "SENAI", "Benedito Bentes")], columns=["cnpj_basico", "Entidade", "Unidade"])
    out = distribuir(end, hist).set_index("cnpj_basico")
    assert out.at["11111111", "unidade_sesi"] == "Tabuleiro"          # preserva o histórico, não a sede
    assert out.at["11111111", "unidade_senai"] == "Poço"              # BB desativado -> Poço
    assert out.at["11111111", "unidades"] == "Poço | Tabuleiro"
    assert out.at["22222222", "unidade_sesi"] == "Tabuleiro" and out.at["22222222", "unidade_senai"] == "Poço"
    assert out.at["33333333", "unidade_sesi"] == A_DEFINIR


def test_historico_em_duas_unidades_vale_a_sede():
    end = _end([("44444444000104", "44444444", "S", "Jatiuca", "Maceio")])
    hist = pd.DataFrame([("44444444", "SESI", "Tabuleiro"), ("44444444", "SESI", "Farol")],
                        columns=["cnpj_basico", "Entidade", "Unidade"])
    out = distribuir(end, hist).set_index("cnpj_basico")
    assert out.at["44444444", "unidade_sesi"] == "Farol"


def test_filtro_por_unidade():
    from src.tools.carteira import filtrar_por_unidade
    df = pd.DataFrame({"unidades": ["Farol | Poço", "Poço | Tabuleiro", "Agreste/Sertão", ""]})
    assert len(filtrar_por_unidade(df, ["Poço"])) == 2
    assert len(filtrar_por_unidade(df, ["Farol", "Agreste/Sertão"])) == 2
    assert len(filtrar_por_unidade(df, [])) == 4


def test_versao_publica_sem_historico():
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location("dc", pathlib.Path(__file__).parents[1] / "jobs" / "distribuir_carteira.py")
    dc = importlib.util.module_from_spec(spec); spec.loader.exec_module(dc)
    out = pd.DataFrame({"cnpj_basico": ["1"], "historico_sesi": ["Farol, Tabuleiro"], "historico_senai": [""],
                        "unidade_sesi": ["Farol"], "motivo_sesi": ["histórico em Farol, Tabuleiro — vale a sede"],
                        "unidade_senai": ["Poço"], "motivo_senai": ["empresa nova — endereço da sede"], "unidades": ["Farol | Poço"]})
    p = dc.publico(out)
    assert "historico_sesi" not in p.columns and "historico_senai" not in p.columns
    assert p.loc[0, "motivo_sesi"] == "cliente" and p.loc[0, "motivo_senai"] == "empresa nova"


def test_olho_dagua_grande_com_acento_agudo():
    from src.tools.carteira import carregar_minuta, norm
    _, municipios = carregar_minuta()
    for grafia in ["Olho d´Agua Grande", "OLHO D'AGUA GRANDE", "Olho d’Água Grande"]:
        assert norm(grafia) == "OLHO DAGUA GRANDE"
        assert norm(grafia) in municipios
    # toda chave da minuta é a normalização do próprio nome
    import pandas as pd
    from src.tools.carteira import ARQ_MINUTA
    t = pd.read_csv(ARQ_MINUTA, dtype=str).fillna("")
    assert (t.nome.map(norm) == t.chave).all()
