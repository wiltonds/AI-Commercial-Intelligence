"""Sinal "venceu licitação" a partir do PNCP (Portal Nacional de Contratações Públicas).

Fonte: API pública de consulta, endpoint /v1/contratos (contratos por data
de publicação). Cada contrato traz o CNPJ do fornecedor contratado, o
órgão contratante, o objeto, o valor e as datas.

Por que isso é sinal comercial: contrato público assinado = equipe a
mobilizar com prazo, e o contratante público costuma exigir SST em dia
(PGR, PCMSO, NRs). No recorte construção, o fornecedor é uma construtora
ou prestadora de serviço de engenharia que vai abrir frente de trabalho.

A API não filtra por UF nem por palavra-chave: o job baixa o dia inteiro
e este módulo filtra AL e o recorte construção localmente.

Tudo aqui é função pura sobre dict/DataFrame (testável sem rede); o
download, o cache e a gravação ficam em jobs/coletar_pncp.py.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

import pandas as pd

URL_PORTAL_CONTRATO = "https://pncp.gov.br/app/contratos/{cnpj}/{ano}/{sequencial}"


def _sem_acento(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def _digitos(valor) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _url_contrato(reg: dict) -> str:
    cnpj = _digitos((reg.get("orgaoEntidade") or {}).get("cnpj"))
    ano, seq = reg.get("anoContrato"), reg.get("sequencialContrato")
    if not (ano and seq):
        # numeroControlePNCP = "CNPJ-2-SEQUENCIAL/ANO"
        m = re.match(r"(\d{14})-\d+-(\d+)/(\d{4})", str(reg.get("numeroControlePNCP") or ""))
        if not m:
            return ""
        cnpj, seq, ano = m.group(1), m.group(2), m.group(3)
    if not cnpj:
        return ""
    return URL_PORTAL_CONTRATO.format(cnpj=cnpj, ano=int(ano), sequencial=int(seq))


def normalizar_contratos(registros: list[dict]) -> pd.DataFrame:
    """JSON da API -> uma linha por contrato, com nomes estáveis.

    Usa .get em tudo: campo que o portal não publica vira vazio em vez de
    derrubar o job.
    """
    linhas = []
    for r in registros:
        orgao = r.get("orgaoEntidade") or {}
        unidade = r.get("unidadeOrgao") or {}
        categoria = r.get("categoriaProcesso") or {}
        linhas.append({
            "numero_controle": r.get("numeroControlePNCP") or "",
            "cnpj_orgao": _digitos(orgao.get("cnpj")),
            "orgao": orgao.get("razaoSocial") or "",
            "unidade": unidade.get("nomeUnidade") or "",
            "uf": (unidade.get("ufSigla") or "").upper(),
            "municipio": unidade.get("municipioNome") or "",
            "codigo_ibge": unidade.get("codigoIbge") or "",
            "ni_fornecedor": _digitos(r.get("niFornecedor")),
            "fornecedor": r.get("nomeRazaoSocialFornecedor") or "",
            "tipo_pessoa": r.get("tipoPessoa") or "",
            "objeto": " ".join(str(r.get("objetoContrato") or "").split()),
            "categoria": categoria.get("nome") or "",
            "valor": r.get("valorGlobal") if r.get("valorGlobal") is not None else r.get("valorInicial"),
            "data_assinatura": r.get("dataAssinatura"),
            "data_vigencia_inicio": r.get("dataVigenciaInicio"),
            "data_vigencia_fim": r.get("dataVigenciaFim"),
            "data_publicacao": r.get("dataPublicacaoPncp"),
            "url_fonte": _url_contrato(r),
        })
    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    for c in ("data_assinatura", "data_vigencia_inicio", "data_vigencia_fim", "data_publicacao"):
        df[c] = pd.to_datetime(df[c], errors="coerce").dt.tz_localize(None).dt.normalize()
    return df.drop_duplicates("numero_controle", keep="last").reset_index(drop=True)


def so_uf(registros: list[dict], uf: str = "AL") -> list[dict]:
    """Filtro barato no JSON cru, antes de normalizar — guarda só AL no cache."""
    uf = uf.upper()
    return [r for r in registros if ((r.get("unidadeOrgao") or {}).get("ufSigla") or "").upper() == uf]


def recorte_construcao(df: pd.DataFrame, regra: dict) -> pd.Series:
    """True para contratos de obra ou serviço de engenharia.

    Entra se a categoria do processo bate OU o objeto tem um termo de
    inclusão — e sai se o objeto tem um termo de exclusão (ex.: compra de
    material, em que o fornecedor é loja e não construtora). Listas
    editáveis em config/fontes.yaml -> pncp.recorte.
    """
    if df.empty:
        return pd.Series(dtype=bool)
    objeto = df["objeto"].map(_sem_acento)
    # "mão de obra" (limpeza, portaria...) não é obra: some antes da busca
    for expr in regra.get("ignorar_expressoes") or []:
        objeto = objeto.str.replace(_sem_acento(expr), " ", regex=False)
    categoria = df["categoria"].map(_sem_acento)

    def _padrao(termos):
        termos = [re.escape(_sem_acento(t)) for t in (termos or []) if str(t).strip()]
        return r"\b(?:" + "|".join(termos) + r")" if termos else None

    inclui = pd.Series(False, index=df.index)
    if (p := _padrao(regra.get("categorias"))):
        inclui |= categoria.str.contains(p, regex=True)
    if (p := _padrao(regra.get("termos_incluir"))):
        inclui |= objeto.str.contains(p, regex=True)
    if (p := _padrao(regra.get("termos_excluir"))):
        inclui &= ~objeto.str.contains(p, regex=True)
    return inclui


def filtrar_recentes(df: pd.DataFrame, hoje: date, janela_dias: int) -> pd.DataFrame:
    if df.empty:
        return df
    evento = df["data_assinatura"].fillna(df["data_vigencia_inicio"]).fillna(df["data_publicacao"])
    idade = (pd.Timestamp(hoje) - evento).dt.days
    return df[idade.between(0, janela_dias)].assign(data_evento=evento).reset_index(drop=True)


def extrair_sinais(contratos: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por (CNPJ fornecedor, contrato). Pessoa física fica fora."""
    df = contratos[contratos["ni_fornecedor"].str.len() == 14].copy()
    df["cnpj"] = df["ni_fornecedor"]
    df["cnpj_basico"] = df["cnpj"].str[:8]
    return df.reset_index(drop=True)


def _brl(valor) -> str:
    if pd.isna(valor) or valor <= 0:
        return ""
    if valor >= 1_000_000:
        return f"R$ {valor / 1_000_000:,.1f} mi".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {valor:,.0f}".replace(",", ".")


def _descrever(linha) -> str:
    objeto = str(linha.get("objeto") or "")
    objeto = objeto if len(objeto) <= 140 else objeto[:137].rstrip() + "..."
    valor = _brl(linha.get("valor"))
    partes = [f"Contrato com {str(linha.get('orgao') or '').title()}", objeto]
    if valor:
        partes.append(valor)
    return " — ".join(p for p in partes if p)


def pontuar(sinais: pd.DataFrame, hoje: date, regra: dict) -> pd.DataFrame:
    """Peso (porte pelo valor do contrato) x decaimento linear até a validade.

    Mesma lógica transparente do CNO: regra em config/fontes.yaml.
    """
    df = sinais.copy()
    validade = int(regra.get("validade_dias", 120))
    peso = pd.Series(float(regra.get("peso_base", 3)), index=df.index)
    for limiar, bonus in sorted((regra.get("bonus_valor") or {}).items()):
        peso += (df["valor"].fillna(0) >= float(limiar)) * float(bonus)

    idade = (pd.Timestamp(hoje) - pd.to_datetime(df["data_evento"])).dt.days
    fator = (1 - idade.clip(lower=0) / validade).clip(lower=0)

    df["tipo_sinal"] = regra.get("tipo", "licitacao_vencida")
    df["fonte"] = "PNCP"
    df["idade_dias"] = idade
    df["peso"] = peso
    df["validade_dias"] = validade
    df["score_momento"] = (peso * fator).round(2)
    df["descricao"] = df.apply(_descrever, axis=1)
    return df.sort_values("score_momento", ascending=False).reset_index(drop=True)


def cruzar_com_base(sinais: pd.DataFrame, empresas: pd.DataFrame) -> pd.DataFrame:
    """Marca quem está na Base Mestre. Fornecedor de fora de AL ou fora do
    universo NÃO é descartado: está executando contrato em AL, é lead."""
    colunas = [c for c in ["CNPJ_BASICO", "razao_social", "Porte",
                           "STATUS_RELACIONAMENTO_REAL", "CNAE PRIMARIO"]
               if c in empresas.columns]
    ref = empresas[colunas].drop_duplicates("CNPJ_BASICO")
    df = sinais.merge(ref, left_on="cnpj_basico", right_on="CNPJ_BASICO", how="left")
    df["na_base_mestre"] = df["CNPJ_BASICO"].notna()
    if "razao_social" not in df:
        df["razao_social"] = pd.NA
    df["razao_social"] = df["razao_social"].replace("", pd.NA).fillna(df["fornecedor"])
    return df.drop(columns=["CNPJ_BASICO"])
