import pandas as pd

from src.sinais.bndes import datas
from src.sinais.detalhe_fonte import detalhes


def test_datas_bndes_nao_troca_dia_e_mes():
    s = pd.Series(["2026-08-12", "2026-08-25", "12/08/2026", "2024-01-03 00:00:00", ""])
    r = datas(s)
    assert r.dt.strftime("%Y-%m-%d").tolist()[:4] == ["2026-08-12", "2026-08-25", "2026-08-12", "2024-01-03"]
    assert pd.isna(r.iloc[4])


def test_detalhes_bndes_lista_operacoes_e_como_conferir():
    s = {"tipo_sinal": "financiamento_bndes", "cnpj": "12191409000111", "casamento": "por CNPJ parcial + nome",
         "detalhe_fonte": "12/08/2026 · R$ 1,00 mi · BNDES FINAME · Banco Volvo | 01/07/2026 · R$ 1,03 mi · BNDES FINAME",
         "arquivo_fonte": "Operações indiretas automáticas", "subsetor": "TRANSP RODOV"}
    d = detalhes(s)
    assert d[0].startswith("Operação: 12/08/2026") and len([x for x in d if x.startswith("Operação")]) == 2
    assert any("confirmar a empresa" in x for x in d)
    assert "12191409000111" in d[-1] and "Operações indiretas automáticas" in d[-1]


def test_detalhes_cno_e_sinal_antigo():
    d = detalhes({"tipo_sinal": "obra_nova", "cno": "900308594672", "area_total": "5731.76",
                  "unidade_medida": "m2", "data_evento": "2026-10-01", "qualificacao_desc": "Dono da obra"})
    assert "CNO nº 900308594672" in d[0] and "5.732" in d[0] and "01/10/2026" in d[0]
    d = detalhes({"tipo_sinal": "financiamento_bndes", "data_evento": "2026-05-04", "valor": "2028000",
                  "n_operacoes": "3", "produto": "BNDES FINAME", "origem": "automática"})
    assert "04/05/2026" in d[0] and "R$ 2,03 mi" in d[0]
