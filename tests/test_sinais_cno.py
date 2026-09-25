import zipfile
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from src.sinais.cno import (
    cruzar_com_base,
    extrair_sinais,
    filtrar_obras_recentes,
    ler_zip_cno,
    pontuar,
    renomear_colunas,
    _MAPA_OBRAS,
)
from src.sinais.fontes import carregar_catalogo, registrar_execucao, carregar_log, saude_das_fontes

HOJE = date(2026, 9, 25)

# Cabeçalho idêntico ao layout oficial da Receita (com acento)
CAB_OBRAS = [
    "CNO", "Código do país", "Nome do País", "Data de início",
    "Data de início da responsabilidade", "Data de registro", "CNO vinculado",
    "CEP", "NI do responsável", "Qualificação do responsável", "Nome",
    "Código do município", "Nome do município", "Tipo de logradouro",
    "Logradouro", "Número do logradouro", "Bairro", "Estado", "Caixa Postal",
    "Complemento", "Unidade de medida", "Área total", "Situação",
    "Data da situação", "Nome empresarial",
]
CAB_VINC = ["CNO", "Data de início", "Data de fim", "Data de registro",
            "Qualificação do contribuinte", "NI do responsável"]


def _obra(cno, inicio, ni, qualif, municipio, uf, area, situacao, nome_emp="", nome="OBRA X"):
    return [cno, "105", "BRASIL", inicio, inicio, inicio, "", "57000000", ni, qualif,
            nome, "2785", municipio, "RUA", "A", "1", "CENTRO", uf, "", "", "m2",
            area, situacao, inicio, nome_emp]


def _zip(tmp_path, obras, vinculos, sep=",", encoding="latin1"):
    caminho = tmp_path / "cno.zip"
    def csv(cab, linhas):
        return "\n".join(sep.join(f'"{v}"' for v in l) for l in [cab] + linhas).encode(encoding)
    with zipfile.ZipFile(caminho, "w") as zf:
        zf.writestr("cno.csv", csv(CAB_OBRAS, obras))
        zf.writestr("cno_vinculos.csv", csv(CAB_VINC, vinculos))
    return caminho


OBRAS = [
    # AL, ativa, recente, PJ dono da obra, 6.000 m2
    _obra("000000000001", "2026-09-01", "11111111000191", "57", "MACEIO", "AL", "6000", "02",
          "ALFA CONSTRUCOES LTDA", "GALPAO LOGISTICO"),
    # AL, ativa, recente, responsável pessoa física (NI vem em branco)
    _obra("000000000002", "2026-08-01", "", "70", "ARAPIRACA", "AL", "150", "02"),
    # AL, mas ENCERRADA
    _obra("000000000003", "2026-09-10", "22222222000105", "53", "MACEIO", "AL", "900", "15"),
    # AL, ativa, mas antiga (fora da janela de 180 dias)
    _obra("000000000004", "2025-01-01", "33333333000180", "53", "MACEIO", "AL", "900", "02"),
    # Outra UF
    _obra("000000000005", "2026-09-01", "44444444000100", "53", "RECIFE", "PE", "900", "02"),
]
VINCULOS = [
    # construtora vinculada à obra 1, vínculo vigente
    ["000000000001", "2026-09-02", "", "2026-09-02", "53", "55555555000155"],
    # vínculo já encerrado
    ["000000000001", "2026-09-02", "2026-09-05", "2026-09-02", "53", "66666666000166"],
    # vínculo de obra de outra UF — nem deve ser lido
    ["000000000005", "2026-09-02", "", "2026-09-02", "53", "77777777000177"],
]


def test_renomeia_layout_oficial_com_acento_e_caixa():
    df = pd.DataFrame(columns=["NI DO RESPONSÁVEL", "Área_total", "Estado", "Campo Novo"])
    assert list(renomear_colunas(df, _MAPA_OBRAS).columns) == ["ni_responsavel", "area_total", "uf"]


@pytest.mark.parametrize("sep,encoding", [(",", "latin1"), (";", "utf-8")])
def test_ler_zip_guarda_so_alagoas_e_vinculos_dessas_obras(tmp_path, sep, encoding):
    obras, vinculos = ler_zip_cno(_zip(tmp_path, OBRAS, VINCULOS, sep, encoding))
    assert set(obras["cno"]) == {"000000000001", "000000000002", "000000000003", "000000000004"}
    assert "77777777000177" not in set(vinculos["ni_responsavel"])


def test_filtra_ativas_dentro_da_janela(tmp_path):
    obras, _ = ler_zip_cno(_zip(tmp_path, OBRAS, VINCULOS))
    recentes = filtrar_obras_recentes(obras, HOJE, janela_dias=180)
    assert set(recentes["cno"]) == {"000000000001", "000000000002"}


def test_sinais_so_para_cnpj_incluindo_vinculo_vigente(tmp_path):
    obras, vinculos = ler_zip_cno(_zip(tmp_path, OBRAS, VINCULOS))
    sinais = extrair_sinais(filtrar_obras_recentes(obras, HOJE, 180), vinculos, HOJE)

    # obra 2 é de pessoa física: sem sinal. Vínculo encerrado: sem sinal.
    assert set(sinais["cnpj"]) == {"11111111000191", "55555555000155"}
    dono = sinais[sinais["cnpj"] == "11111111000191"].iloc[0]
    assert dono["papel"] == "responsável"
    assert dono["qualificacao_desc"] == "Dono da obra"
    assert dono["cnpj_basico"] == "11111111"


def test_pontuacao_bonus_de_area_e_decaimento():
    sinais = pd.DataFrame({
        "cnpj": ["1" * 14, "2" * 14, "3" * 14],
        "area_total": [6000.0, 200.0, 200.0],
        "data_evento": pd.to_datetime(["2026-09-25", "2026-09-25", "2026-06-27"]),
        "qualificacao_desc": ["Dono da obra"] * 3,
        "papel": ["responsável"] * 3,
        "nome_obra": ["A", "B", "C"],
        "municipio": ["MACEIO"] * 3,
    })
    regra = {"validade_dias": 120, "peso_base": 3, "bonus_area_m2": {1000: 1, 5000: 1}}
    out = pontuar(sinais, HOJE, regra).set_index("cnpj")

    assert out.loc["1" * 14, "score_momento"] == 5.0   # 3 + 1 + 1, obra de hoje
    assert out.loc["2" * 14, "score_momento"] == 3.0   # sem bônus
    assert out.loc["3" * 14, "score_momento"] == 0.75  # 90 de 120 dias: sobra 25%


def test_decaimento_linear_na_metade_da_validade():
    sinais = pd.DataFrame({
        "cnpj": ["1" * 14], "area_total": [0.0],
        "data_evento": pd.to_datetime(["2026-07-27"]),  # 60 dias antes de HOJE
        "qualificacao_desc": ["Dono da obra"], "papel": ["responsável"],
        "nome_obra": ["A"], "municipio": ["MACEIO"],
    })
    out = pontuar(sinais, HOJE, {"validade_dias": 120, "peso_base": 4})
    assert out.loc[0, "score_momento"] == 2.0


def test_cruzar_com_base_mantem_quem_nao_esta_no_universo():
    sinais = pd.DataFrame({"cnpj_basico": ["11111111", "99999999"],
                           "nome_empresarial": ["ALFA", "ATACAREJO X"]})
    empresas = pd.DataFrame({"CNPJ_BASICO": ["11111111"], "razao_social": ["ALFA LTDA"],
                             "STATUS_RELACIONAMENTO_REAL": ["Somente SESI"]})
    out = cruzar_com_base(sinais, empresas).set_index("cnpj_basico")
    assert out.loc["11111111", "na_base_mestre"]
    assert out.loc["11111111", "STATUS_RELACIONAMENTO_REAL"] == "Somente SESI"
    assert not out.loc["99999999", "na_base_mestre"]
    assert out.loc["99999999", "razao_social"] == "ATACAREJO X"


def test_catalogo_real_tem_regra_do_cno():
    cat = carregar_catalogo()
    assert cat["cno"]["status"] == "implementado"
    assert cat["cno"]["sinal"]["validade_dias"] > 0


def test_semaforo(tmp_path):
    log_path = tmp_path / "log.csv"
    catalogo = {
        "a": {"status": "implementado", "frequencia_dias": 1},
        "b": {"status": "implementado", "frequencia_dias": 1},
        "c": {"status": "planejado", "frequencia_dias": 1},
    }
    registrar_execucao("a", "sucesso", 10, caminho=log_path)
    registrar_execucao("b", "sucesso", 10, caminho=log_path)
    registrar_execucao("b", "falha", 0, "erro", caminho=log_path)

    saude = saude_das_fontes(catalogo, carregar_log(log_path),
                             agora=datetime.now(timezone.utc)).set_index("fonte")
    assert saude.loc["a", "semaforo"] == "🟢"
    assert saude.loc["b", "semaforo"] == "🔴"
    assert saude.loc["c", "semaforo"] == "⚪"


class _RespostaFalsa:
    def __init__(self, conteudo):
        self.conteudo = conteudo
        self.headers = {"content-length": str(len(conteudo))}
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def raise_for_status(self): pass
    def iter_content(self, chunk_size):
        yield self.conteudo


def test_baixar_rejeita_pagina_html_do_waf(tmp_path, monkeypatch):
    import jobs.coletar_cno as job
    monkeypatch.setattr(job.requests, "get", lambda *a, **k: _RespostaFalsa(b"<html>Request Rejected</html>"))
    with pytest.raises(RuntimeError, match="--arquivo"):
        job.baixar("https://x/cno.zip", tmp_path / "cno.zip", tentativas=2, espera=0)
    assert not (tmp_path / "cno.zip").exists()


def test_baixar_aceita_zip(tmp_path, monkeypatch):
    import jobs.coletar_cno as job
    monkeypatch.setattr(job.requests, "get", lambda *a, **k: _RespostaFalsa(b"PK\x03\x04resto"))
    destino = job.baixar("https://x/cno.zip", tmp_path / "cno.zip", tentativas=1, espera=0)
    assert destino.read_bytes().startswith(b"PK")


# ------------------------------------------------------------
# Camada genérica: novidades e oferta sugerida
# ------------------------------------------------------------
from src.sinais.consolidar import (  # noqa: E402
    aplicar_ofertas, carregar_ofertas, carregar_todos_sinais, marcar_novidades, sugerir,
)


def test_novidade_pela_data_de_publicacao():
    df = pd.DataFrame({"data_publicacao": pd.to_datetime(["2026-09-24", "2026-09-10", "2026-09-30"])})
    out = marcar_novidades(df, HOJE, dias=7)
    assert list(out["novo"]) == [True, False, False]  # futura não conta como novidade


def test_oferta_construtora_vs_dono_e_bonus_grande_porte():
    ofertas = carregar_ofertas()
    construtora = sugerir({"tipo_sinal": "obra_nova", "qualificacao": "53", "area_total": 800}, ofertas)
    dono_grande = sugerir({"tipo_sinal": "obra_nova", "qualificacao": "0057", "area_total": 6000}, ofertas)

    assert construtora["perfil"] == "Construtora no canteiro"
    assert "NR 35" in construtora["oferta_sesi"]
    assert "Montador de Andaimes" in construtora["oferta_senai"]
    assert construtora["perfil_extra"] == ""

    assert dono_grande["perfil"] == "Dono da obra (expansão)"
    assert dono_grande["perfil_extra"] == "Obra de grande porte"
    assert "LTCAT" in dono_grande["oferta_sesi"]


def test_tipo_desconhecido_nao_quebra():
    s = sugerir({"tipo_sinal": "algo_novo"}, carregar_ofertas())
    assert s["rotulo_tipo"] == "algo_novo" and s["oferta_sesi"] == ""


def test_todos_os_tipos_do_catalogo_tem_perfil_padrao():
    for tipo, cfg in carregar_ofertas().items():
        assert any(not p.get("quando") for p in cfg["perfis"]) or len(cfg["perfis"]) >= 1, tipo


def test_carregar_todos_sinais_junta_arquivos_de_fontes_diferentes(tmp_path):
    comum = {"cnpj_basico": "11111111", "razao_social": "A", "na_base_mestre": "True",
             "descricao": "x", "municipio": "MACEIO", "score_momento": 3,
             "data_evento": "2026-09-20"}
    pd.DataFrame([{**comum, "tipo_sinal": "obra_nova", "data_publicacao": "2026-09-21",
                   "STATUS_RELACIONAMENTO_REAL": "Somente SESI"}]).to_csv(
        tmp_path / "SINAIS_CNO.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([{**comum, "tipo_sinal": "empresa_nova"}]).to_csv(
        tmp_path / "SINAIS_CNPJ.csv", index=False, encoding="utf-8-sig")

    df = aplicar_ofertas(carregar_todos_sinais(tmp_path), carregar_ofertas())
    assert set(df["rotulo_tipo"]) == {"Obra nova", "Empresa nova"}
    # arquivo sem data_publicacao usa data_evento; sem relacionamento vira "Fora da Base Mestre"
    nova = df[df["tipo_sinal"] == "empresa_nova"].iloc[0]
    assert nova["data_publicacao"] == pd.Timestamp("2026-09-20")
    assert nova["STATUS_RELACIONAMENTO_REAL"] == "Fora da Base Mestre"
