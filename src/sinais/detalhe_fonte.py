"""O que mostrar no cartão para o usuário conferir o sinal na fonte original.

Cada linha é um dado concreto (data, valor, número do registro) e a última diz
onde e como conferir. Funciona com sinais antigos que ainda não têm as colunas
detalhe_fonte/arquivo_fonte: usa os campos que existirem.
"""
from __future__ import annotations

import pandas as pd

URL_BNDES = "https://dadosabertos.bndes.gov.br/dataset/operacoes-financiamento"
URL_CNO = "https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-de-obras-cno"


def _v(s, k) -> str:
    x = s.get(k) if hasattr(s, "get") else None
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    t = str(x).strip()
    return "" if t.lower() in ("", "nan", "none", "nat") else t


def _data(x: str) -> str:
    d = pd.to_datetime(x, errors="coerce")
    return d.strftime("%d/%m/%Y") if pd.notna(d) else ""


def _reais(x: str) -> str:
    try:
        v = float(x)
    except ValueError:
        return ""
    return "R$ " + f"{v / 1e6:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " mi"


def _num(x: str) -> str:
    try:
        return f"{float(x):,.0f}".replace(",", ".")
    except ValueError:
        return ""


def rotulo_data(tipo: str) -> str:
    return {"financiamento_bndes": "contratado em", "obra_nova": "obra registrada em"}.get(tipo, "")


def detalhes(s) -> list[str]:
    """Linhas em markdown para o expander 'De onde vem este dado'."""
    tipo, out = _v(s, "tipo_sinal"), []
    cnpj = _v(s, "cnpj")
    if tipo == "financiamento_bndes":
        ops = _v(s, "detalhe_fonte")
        if ops:
            out += [f"Operação: {o}" for o in ops.split(" | ")]
        else:
            partes = [f"contratada em {_data(_v(s, 'data_evento'))}" if _data(_v(s, "data_evento")) else "",
                      f"total {_reais(_v(s, 'valor'))}" if _reais(_v(s, "valor")) else "",
                      f"{_v(s, 'n_operacoes')} operação(ões)" if _v(s, "n_operacoes") else "",
                      _v(s, "produto")]
            out.append("Operação: " + " · ".join(p for p in partes if p))
        if _v(s, "subsetor"):
            out.append(f"Atividade informada ao BNDES: {_v(s, 'subsetor').title()}")
        arquivo = _v(s, "arquivo_fonte") or {"automática": "Operações indiretas automáticas",
                                             "não automática": "Operações não automáticas"}.get(_v(s, "origem"), "")
        casa = _v(s, "casamento")
        if casa:
            alerta = " ⚠️ confirmar a empresa antes de abordar" if "parcial" in casa or "não identificado" in casa else ""
            out.append(f"Ligação com a empresa: {casa}{alerta}")
        out.append(f"Como conferir: [Dados abertos do BNDES ↗]({URL_BNDES}) › arquivo “{arquivo or 'Operações'}” "
                   f"› filtrar UF = AL e CNPJ {cnpj or '—'}")
    elif tipo == "obra_nova":
        partes = [f"CNO nº {_v(s, 'cno')}" if _v(s, "cno") else "",
                  f"{_num(_v(s, 'area_total'))} {_v(s, 'unidade_medida') or 'm²'}" if _num(_v(s, "area_total")) else "",
                  f"registrada em {_data(_v(s, 'data_evento'))}" if _data(_v(s, "data_evento")) else "",
                  f"bairro {_v(s, 'bairro').title()}" if _v(s, "bairro") else ""]
        out.append("Obra: " + " · ".join(p for p in partes if p))
        if _v(s, "qualificacao_desc"):
            out.append(f"Papel da empresa na obra: {_v(s, 'qualificacao_desc')}")
        out.append(f"Como conferir: [Cadastro Nacional de Obras, Receita Federal ↗]({URL_CNO}) › nº do CNO acima"
                   + (f" › CNPJ {cnpj}" if cnpj else ""))
    else:
        d = _data(_v(s, "data_publicacao"))
        if d:
            out.append(f"Publicado em {d} · {_v(s, 'fonte')}")
        if _v(s, "casamento"):
            out.append(f"Ligação com a empresa: {_v(s, 'casamento')}")
    return [o for o in out if o.strip() and not o.endswith(": ")]
