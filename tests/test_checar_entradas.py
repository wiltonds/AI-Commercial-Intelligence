from datetime import datetime

import yaml

from jobs.checar_entradas import ARQ_ENTRADAS, avaliar
from src.tools.log_atualizacoes import registrar, ultimas


def test_status_por_idade_e_log(tmp_path):
    entradas = yaml.safe_load(open(ARQ_ENTRADAS, encoding="utf-8"))["entradas"]
    log = {"propostas": {"data": "2026-09-01T00:00:00"}, "receita_cnpj": {"data": "2026-07-01T10:00:00"},
           "contatos_robo": {"data": "2026-09-25T10:00:00"}}
    r = {x["chave"]: x for x in avaliar(entradas, log, datetime(2026, 9, 29), raiz=tmp_path)}
    assert r["propostas"]["status"] == "vence em 3 dias"            # 28 de 31 dias
    assert r["receita_cnpj"]["status"].startswith("VENCIDO") and r["receita_cnpj"]["atencao"]
    assert r["contatos_robo"]["status"] == "em dia"
    assert r["presenca_digital"]["status"] == "NUNCA REGISTRADO"
    assert r["tabela_dn"]["status"] == "FALTANDO"                    # tmp_path sem a tabela
    assert [x["chave"] for x in avaliar(entradas, log, datetime(2026, 9, 29))][0] == "tabela_dn"   # ordem 0


def test_log_grava_e_le_ultima(tmp_path):
    arq = tmp_path / "log.csv"
    registrar("propostas", "a", arq)
    registrar("propostas", "b", arq)
    assert ultimas(arq)["propostas"]["resumo"] == "b"


def test_toda_entrada_tem_os_campos():
    entradas = yaml.safe_load(open(ARQ_ENTRADAS, encoding="utf-8"))["entradas"]
    for chave, e in entradas.items():
        for campo in ("nome", "dono", "como_obter", "onde_colocar", "comando", "atualiza", "frequencia_dias", "ordem"):
            assert campo in e, (chave, campo)
