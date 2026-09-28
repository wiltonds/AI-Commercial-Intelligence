import json
from datetime import date

import pandas as pd
import pytest

from src.sinais.consolidar import aplicar_ofertas, carregar_ofertas
from src.sinais.fontes import carregar_catalogo
from src.sinais.pncp import (
    cruzar_com_base,
    extrair_sinais,
    filtrar_recentes,
    normalizar_contratos,
    pontuar,
    recorte_construcao,
    so_uf,
)

HOJE = date(2026, 9, 28)


def _contrato(ctrl, uf, ni, objeto, valor=500_000.0, assinatura="2026-09-20",
              categoria="Obras", tipo="PJ", fornecedor="CONSTRUTORA X LTDA"):
    return {
        "numeroControlePNCP": ctrl,
        "anoContrato": 2026,
        "sequencialContrato": int(ctrl.split("-")[2].split("/")[0]),
        "orgaoEntidade": {"cnpj": "12200192000169", "razaoSocial": "MUNICIPIO DE MACEIO"},
        "unidadeOrgao": {"ufSigla": uf, "municipioNome": "Maceió", "codigoIbge": "2704302",
                         "nomeUnidade": "SEC. INFRAESTRUTURA"},
        "niFornecedor": ni,
        "nomeRazaoSocialFornecedor": fornecedor,
        "tipoPessoa": tipo,
        "objetoContrato": objeto,
        "categoriaProcesso": {"id": 7, "nome": categoria},
        "valorInicial": valor,
        "valorGlobal": valor,
        "dataAssinatura": assinatura,
        "dataVigenciaInicio": assinatura,
        "dataVigenciaFim": "2027-09-20",
        "dataPublicacaoPncp": assinatura + "T10:00:00",
    }


@pytest.fixture
def regra():
    return carregar_catalogo()["pncp"]


@pytest.fixture
def brutos():
    return [
        _contrato("12200192000169-2-000010/2026", "AL", "11.111.111/0001-11",
                  "Execução de obra de pavimentação da Av. Central", valor=12_000_000),
        _contrato("12200192000169-2-000011/2026", "AL", "22222222000122",
                  "Contratação de mão de obra terceirizada de limpeza", categoria="Serviços"),
        _contrato("12200192000169-2-000012/2026", "AL", "33333333000133",
                  "Aquisição de material de construção", categoria="Compras"),
        _contrato("12200192000169-2-000013/2026", "AL", "12345678901",
                  "Reforma da escola municipal", tipo="PF"),
        _contrato("12200192000169-2-000014/2026", "PE", "44444444000144",
                  "Construção de ponte"),
        _contrato("12200192000169-2-000015/2026", "AL", "55555555000155",
                  "Reforma e ampliação da UBS", categoria="Serviços", assinatura="2026-01-10"),
    ]


def test_so_uf_filtra_no_json_cru(brutos):
    assert len(so_uf(brutos, "AL")) == 5
    assert all(r["unidadeOrgao"]["ufSigla"] == "AL" for r in so_uf(brutos, "al"))


def test_normaliza_campos_e_link_do_portal(brutos):
    df = normalizar_contratos(brutos)
    linha = df.iloc[0]
    assert linha["ni_fornecedor"] == "11111111000111"
    assert linha["valor"] == 12_000_000
    assert linha["url_fonte"] == "https://pncp.gov.br/app/contratos/12200192000169/2026/10"
    assert pd.api.types.is_datetime64_any_dtype(df["data_assinatura"])


def test_link_sai_do_numero_de_controle_quando_falta_ano(brutos):
    reg = dict(brutos[0])
    reg.pop("anoContrato"), reg.pop("sequencialContrato")
    assert normalizar_contratos([reg]).iloc[0]["url_fonte"].endswith("/2026/10")


def test_normaliza_tolera_campos_ausentes():
    df = normalizar_contratos([{"numeroControlePNCP": "x"}])
    assert df.iloc[0]["uf"] == "" and pd.isna(df.iloc[0]["valor"])


def test_recorte_pega_obra_e_descarta_mao_de_obra_e_compra(brutos, regra):
    df = normalizar_contratos(so_uf(brutos))
    mascara = recorte_construcao(df, regra["recorte"])
    pegos = set(df.loc[mascara, "numero_controle"].str[-9:-5])
    assert pegos == {"0010", "0013", "0015"}   # pavimentação, reforma escola, reforma UBS


def test_janela_e_pessoa_fisica(brutos, regra):
    df = normalizar_contratos(so_uf(brutos))
    obras = df[recorte_construcao(df, regra["recorte"])]
    recentes = filtrar_recentes(obras, HOJE, 90)
    assert "12200192000169-2-000015/2026" not in set(recentes["numero_controle"])  # jan/2026
    sinais = extrair_sinais(recentes)
    assert list(sinais["cnpj"]) == ["11111111000111"]                          # PF fora
    assert sinais.iloc[0]["cnpj_basico"] == "11111111"


def test_pontuacao_bonus_de_valor_e_decaimento(regra):
    base = pd.DataFrame({
        "valor": [500_000.0, 2_000_000.0, 20_000_000.0],
        "data_evento": pd.to_datetime(["2026-09-28"] * 3),
        "orgao": ["X"] * 3, "objeto": ["obra"] * 3,
    })
    df = pontuar(base, HOJE, regra["sinal"]).sort_values("valor")
    assert list(df["peso"]) == [3.0, 4.0, 5.0]
    assert list(df["score_momento"]) == [3.0, 4.0, 5.0]
    meio = base.assign(data_evento=pd.Timestamp("2026-07-30"))   # 60 de 120 dias
    assert pontuar(meio, HOJE, regra["sinal"])["score_momento"].min() == 1.5


def test_cruzar_mantem_fornecedor_fora_da_base():
    sinais = pd.DataFrame({"cnpj_basico": ["11111111", "99999999"],
                           "fornecedor": ["CONSTRUTORA X", "EMPRESA DE PE"]})
    base = pd.DataFrame({"CNPJ_BASICO": ["11111111"], "razao_social": ["CONSTRUTORA X SA"],
                         "STATUS_RELACIONAMENTO_REAL": ["Cliente SESI"]})
    df = cruzar_com_base(sinais, base)
    assert list(df["na_base_mestre"]) == [True, False]
    assert list(df["razao_social"]) == ["CONSTRUTORA X SA", "EMPRESA DE PE"]


def test_oferta_de_grande_valor_soma_adicional():
    ofertas = carregar_ofertas()
    df = pd.DataFrame({"tipo_sinal": ["licitacao_vencida"] * 2, "valor": [300_000, 8_000_000]})
    out = aplicar_ofertas(df, ofertas)
    assert out.iloc[0]["perfil_extra"] == ""
    assert out.iloc[1]["perfil_extra"] == "Contrato de grande valor"
    assert "Mestre de Obras" in out.iloc[1]["oferta_senai"]


def test_cache_nao_rebaixa_dia_antigo(tmp_path, brutos):
    from jobs.coletar_pncp import carregar_janela
    antigo = tmp_path / "20260920.json"
    antigo.write_text(json.dumps(so_uf(brutos)), encoding="utf-8")
    chamados = []

    def falso_baixar(dia, uf, sessao, avisar):
        chamados.append(dia)
        return []

    regs = carregar_janela(HOJE, 8, "AL", avisar=lambda *_: None,
                           pasta=tmp_path, baixar=falso_baixar)
    assert date(2026, 9, 20) not in chamados       # veio do cache
    assert len(chamados) == 8                      # 21/09 a 28/09
    assert len(regs) == 5


def test_cache_sempre_recarrega_dias_recentes(tmp_path):
    from jobs.coletar_pncp import carregar_janela
    (tmp_path / "20260928.json").write_text("[]", encoding="utf-8")
    chamados = []
    carregar_janela(HOJE, 0, "AL", avisar=lambda *_: None, pasta=tmp_path,
                    baixar=lambda d, *a: chamados.append(d) or [])
    assert chamados == [HOJE]


def test_baixar_dia_percorre_paginas_e_trata_204(monkeypatch, brutos):
    from jobs import coletar_pncp as job

    class Resp:
        def __init__(self, status, corpo=None):
            self.status_code, self._c = status, corpo
            self.headers = {"content-type": "application/json"}
        def raise_for_status(self): pass
        def json(self): return self._c

    paginas = {1: Resp(200, {"data": brutos[:3], "totalPaginas": 2}),
               2: Resp(200, {"data": brutos[3:], "totalPaginas": 2})}

    class Sessao:
        def get(self, url, params, timeout): return paginas[params["pagina"]]

    monkeypatch.setattr(job, "PAUSA_ENTRE_PAGINAS", 0)
    assert len(job.baixar_dia(HOJE, "AL", Sessao())) == 5

    class Vazia:
        def get(self, *a, **k): return Resp(204)
    assert job.baixar_dia(HOJE, "AL", Vazia()) == []


def test_catalogo_marca_pncp_implementado(regra):
    assert regra["status"] == "implementado"
    assert regra["job"] == "jobs/coletar_pncp.py"
