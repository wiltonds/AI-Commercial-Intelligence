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
    out["endereco_sede"] = "bairro pelo CEP 57000001: Farol (Maceió; na Receita 'X')"
    p = dc.publico(out)
    assert list(p.columns) == ["cnpj_basico", "unidade_sesi", "unidade_senai", "unidades"]
    assert not [c for c in p.columns if c.startswith(("motivo_", "historico_", "endereco", "bairro", "municipio"))]


def _end_cep(linhas):
    return pd.DataFrame(linhas, columns=["cnpj", "cnpj_basico", "matriz", "bairro", "cep", "municipio"])


def test_bairro_pelo_cep():
    from src.tools.carteira import cep_generico, mapa_cep_bairro
    vizinhos = [(f"9000000{i}000101", f"9000000{i}", "S", "Jatiuca", "57036540", "Maceio") for i in range(3)]
    end = _end_cep(vizinhos + [
        ("55555555000105", "55555555", "S", "Tabuleiro Dos Martin", "57036540", "Maceio"),   # alias diz Tabuleiro, CEP diz Jatiúca
        ("66666666000106", "66666666", "S", "Reginaldo", "57036540", "Maceio"),              # fora da minuta, CEP resolve
        ("77777777000107", "77777777", "S", "Magabeiras", "57010000", "Maceio"),             # CEP genérico: vale o alias
        ("88888888000108", "88888888", "S", "Farol", "57036540", "Maceio"),                  # nome exato vence o CEP
    ])
    assert cep_generico("57010-000") and not cep_generico("57036-540")
    assert mapa_cep_bairro(end, B)["57036540"] == "JATIUCA"
    out = distribuir(end, None).set_index("cnpj_basico")
    assert out.at["55555555", "unidade_sesi"] == "Farol"                 # Jatiúca -> Cambona/Farol, não Tabuleiro
    assert out.at["55555555", "endereco_sede"].startswith("bairro pelo CEP")
    assert out.at["66666666", "unidade_sesi"] == "Farol"
    assert out.at["77777777", "endereco_sede"] == "sede no bairro Mangabeiras (Maceió)"
    assert out.at["88888888", "endereco_sede"] == "sede no bairro Farol (Maceió)"


def test_cep_sem_maioria_nao_decide():
    from src.tools.carteira import mapa_cep_bairro
    end = _end_cep([("1", "1", "S", "Farol", "57051111", "Maceio"), ("2", "2", "S", "Prado", "57051111", "Maceio"),
                    ("3", "3", "S", "Pinheiro", "57052222", "Maceio")])                    # empate e apoio de 1
    assert mapa_cep_bairro(end, B) == {}


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
