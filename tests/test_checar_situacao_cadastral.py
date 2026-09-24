import pandas as pd
import pytest

import jobs.checar_situacao_cadastral as job
from jobs.checar_situacao_cadastral import carregar_monitoramento, escolher_lote


@pytest.fixture(autouse=True)
def isolar_arquivo_de_estado(tmp_path, monkeypatch):
    """Nunca deixa os testes lerem/escreverem o CSV real de monitoramento."""
    monkeypatch.setattr(job, "ARQ_MONITORAMENTO", tmp_path / "monitoramento.csv")


def _universo():
    return pd.DataFrame(
        {
            "CNPJ_BASICO": ["11111111", "22222222", "33333333"],
            "cnpj": ["11111111000191", "22222222000105", "33333333000280"],
            "razao_social": ["A LTDA", "B LTDA", "C LTDA"],
            "situacao_conhecida": ["ATIVA", "ATIVA", "ATIVA"],
        }
    )


def test_inicializa_estado_do_zero_sem_ninguem_checado():
    estado = carregar_monitoramento(_universo())

    assert len(estado) == 3
    assert (estado["ultima_checagem"] == "").all()
    assert (estado["mudou_status"] == "NAO").all()
    assert list(estado["situacao_atual"]) == ["ATIVA", "ATIVA", "ATIVA"]


def test_escolher_lote_prioriza_nunca_checado():
    estado = carregar_monitoramento(_universo())
    estado.loc[estado["CNPJ_BASICO"] == "11111111", "ultima_checagem"] = (
        "2026-01-01T00:00:00+00:00"
    )

    lote = escolher_lote(estado, tamanho=2)

    # os dois nunca checados (22222222, 33333333) vêm antes do já checado
    assert set(lote["CNPJ_BASICO"]) == {"22222222", "33333333"}


def test_escolher_lote_prioriza_checagem_mais_antiga():
    estado = carregar_monitoramento(_universo())
    estado["ultima_checagem"] = [
        "2026-01-01T00:00:00+00:00",  # 11111111 — mais antiga
        "2026-06-01T00:00:00+00:00",  # 22222222
        "2026-09-01T00:00:00+00:00",  # 33333333 — mais recente
    ]

    lote = escolher_lote(estado, tamanho=1)

    assert list(lote["CNPJ_BASICO"]) == ["11111111"]


def test_carregar_monitoramento_incorpora_empresa_nova_do_universo():
    estado_existente = pd.DataFrame(
        {
            "CNPJ_BASICO": ["11111111"],
            "cnpj": ["11111111000191"],
            "razao_social": ["A LTDA"],
            "situacao_atual": ["ATIVA"],
            "ultima_checagem": ["2026-01-01T00:00:00+00:00"],
            "mudou_status": ["NAO"],
            "data_deteccao_mudanca": [""],
        }
    )
    estado_existente.to_csv(job.ARQ_MONITORAMENTO, index=False, encoding="utf-8-sig")

    estado = carregar_monitoramento(_universo())

    assert len(estado) == 3
    novas = estado[estado["CNPJ_BASICO"] != "11111111"]
    assert (novas["ultima_checagem"] == "").all()
