"""Financiamentos do BNDES para empresas de AL (dados abertos, com CNPJ).

Financiamento contratado é investimento confirmado: a empresa vai comprar
máquina, ampliar, inovar. Fonte: dadosabertos.bndes.gov.br, conjunto
"Operações de financiamento" — arquivo de operações diretas e indiretas não
automáticas (projetos maiores, com descrição). Dicionário de dados no portal.
"""
from __future__ import annotations

import io
import re
import unicodedata
from datetime import date

import pandas as pd

PACOTE = "10e21ad1-568e-45e5-a8af-43f2c05ef1a2"
API_CKAN = "https://dadosabertos.bndes.gov.br/api/3/action/package_show?id=" + PACOTE


def _n(t) -> str:
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", t)


def achar_recursos(pacote: dict, automaticas: bool = False) -> list[str]:
    """URLs dos arquivos de operações (CSV), sem dicionários."""
    urls = []
    for r in pacote["result"]["resources"]:
        nome, fmt = _n(r.get("name", "")), _n(r.get("format", ""))
        if "dicionario" in nome or fmt not in ("csv", "zip"):
            continue
        if "naoautomatica" in nome or (automaticas and "automatica" in nome):
            urls.append(r["url"])
    return urls


def _col(cols, *nomes):
    alvo = {c: _n(c) for c in cols}
    for n in nomes:
        for c, k in alvo.items():
            if k == _n(n):
                return c
    for n in nomes:
        for c, k in alvo.items():
            if k.startswith(_n(n)):
                return c
    raise KeyError(f"coluna não encontrada: {nomes}. Colunas: {list(cols)}")


def _numero(serie: pd.Series) -> pd.Series:
    """Aceita '1234.56' e '1.234,56'."""
    s = serie.fillna("").astype(str).str.strip()
    br = s.str.contains(",")
    s = s.where(~br, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(s, errors="coerce")


def ler_operacoes(conteudo: bytes) -> pd.DataFrame:
    """Lê o CSV do BNDES (separador e encoding detectados) e padroniza as colunas."""
    for enc in ("utf-8-sig", "latin-1"):
        try:
            texto = conteudo.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    primeira = texto.splitlines()[0]
    sep = ";" if primeira.count(";") >= primeira.count(",") else ","
    df = pd.read_csv(io.StringIO(texto), sep=sep, dtype=str)
    c = df.columns
    out = pd.DataFrame({
        "cliente": df[_col(c, "cliente")],
        "cnpj": df[_col(c, "cnpj", "cpf_cnpj")].fillna("").str.replace(r"\D", "", regex=True).str.zfill(14),
        "projeto": df[_col(c, "descricao do projeto", "descricao_do_projeto")],
        "uf": df[_col(c, "uf")].str.strip().str.upper(),
        "municipio_bndes": df[_col(c, "municipio")],
        "data_contratacao": pd.to_datetime(df[_col(c, "data da contratacao", "data_da_contratacao")],
                                           errors="coerce", dayfirst=True),
        "valor": _numero(df[_col(c, "valor contratado reais", "valor_contratado_reais")]),
        "produto": df[_col(c, "produto")],
        "inovacao": df[_col(c, "inovacao")].fillna("").str.upper(),
        "natureza": df[_col(c, "natureza do cliente", "natureza_do_cliente")].fillna(""),
        "subsetor": df[_col(c, "subsetor cnae nome", "subsetor_cnae_nome")].fillna(""),
    })
    return out


def para_sinais(op: pd.DataFrame, empresas: pd.DataFrame, hoje: date, meses: int = 24,
                peso: float = 4, validade_dias: int = 365) -> pd.DataFrame:
    """Operações privadas em AL nos últimos N meses, no formato padrão de sinais."""
    from src.tools.municipios import padronizar

    limite = pd.Timestamp(hoje) - pd.DateOffset(months=meses)
    op = op[(op["uf"] == "AL") & (op["data_contratacao"] >= limite)
            & op["natureza"].str.upper().str.contains("PRIVAD", na=False)].copy()
    if op.empty:
        return pd.DataFrame()
    op["cnpj_basico"] = op["cnpj"].str[:8]
    ref = empresas[["cnpj_basico", "razao_social", "STATUS_RELACIONAMENTO_REAL", "Porte", "tipo_empresa"]]
    df = op.merge(ref, on="cnpj_basico", how="left")
    df["na_base_mestre"] = df["tipo_empresa"].eq("Indústria")
    df["razao_social"] = df["razao_social"].fillna(df["cliente"])
    df["STATUS_RELACIONAMENTO_REAL"] = df["STATUS_RELACIONAMENTO_REAL"].fillna("Fora da Base Mestre")
    df["municipio"] = padronizar(df["municipio_bndes"].fillna("").str.title())
    valor_mi = (df["valor"] / 1e6).round(2)
    df["descricao"] = ("Financiamento BNDES de R$ " + valor_mi.map(lambda v: f"{v:,.2f}".replace(",", "X")
                       .replace(".", ",").replace("X", ".")) + " mi: " + df["projeto"].fillna("").str.strip().str[:160])
    df["tipo_sinal"] = "financiamento_bndes"
    df["tema"] = df["inovacao"].map(lambda x: "Inovação" if x.startswith("S") else "Investimento")
    df["data_publicacao"] = df["data_evento"] = df["data_contratacao"]
    idade = (pd.Timestamp(hoje) - df["data_contratacao"]).dt.days.clip(lower=0)
    bonus = (df["valor"] >= 1e6).astype(float) + (df["valor"] >= 10e6).astype(float)
    df["idade_dias"], df["peso"], df["validade_dias"] = idade, peso + bonus, validade_dias
    df["score_momento"] = (df["peso"] * (1 - idade / validade_dias).clip(lower=0)).round(2)
    df["casamento"], df["fonte"] = "por CNPJ", "BNDES · dados abertos"
    df["url_fonte"] = "https://dadosabertos.bndes.gov.br/dataset/operacoes-financiamento"
    cols = ["tipo_sinal", "tema", "descricao", "cnpj_basico", "cnpj", "razao_social", "STATUS_RELACIONAMENTO_REAL",
            "Porte", "na_base_mestre", "casamento", "municipio", "data_publicacao", "data_evento", "valor",
            "produto", "subsetor", "inovacao", "peso", "validade_dias", "idade_dias", "score_momento", "fonte", "url_fonte"]
    return df[cols].sort_values("score_momento", ascending=False).reset_index(drop=True)
