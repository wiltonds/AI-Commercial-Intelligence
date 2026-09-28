"""Leitura dos dados abertos do CNPJ (Receita Federal) — arquivos mensais.

Os arquivos vêm em .zip, cada um com um CSV sem cabeçalho, separado por
";", em latin-1. Layouts usados aqui (dicionário de dados oficial):

  Estabelecimentos*.zip  uma linha por estabelecimento (matriz ou filial)
  Empresas*.zip          uma linha por CNPJ raiz (razão social, porte)
  Municipios.zip / Cnaes.zip / Naturezas.zip   tabelas de códigos

Os arquivos de Estabelecimentos do Brasil inteiro somam dezenas de
milhões de linhas: a leitura é feita em blocos, e só as linhas de AL
ativas ficam na memória.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

COLS_ESTAB = [
    "cnpj_basico", "cnpj_ordem", "cnpj_dv", "matriz_filial", "nome_fantasia",
    "situacao", "data_situacao", "motivo_situacao", "cidade_exterior", "pais",
    "data_inicio_atividade", "cnae_principal", "cnaes_secundarios",
    "tipo_logradouro", "logradouro", "numero", "complemento", "bairro", "cep",
    "uf", "municipio_codigo", "ddd_1", "telefone_1", "ddd_2", "telefone_2",
    "ddd_fax", "fax", "email", "situacao_especial", "data_situacao_especial",
]
COLS_EMPRESA = ["cnpj_basico", "razao_social", "natureza_juridica", "qualificacao_responsavel",
                "capital_social", "porte_codigo", "ente_federativo"]

PORTE = {"01": "MICRO EMPRESA", "03": "PEQUENO PORTE", "05": "DEMAIS", "00": "NÃO INFORMADO"}
ATIVA = "02"

# Indústria pela seção CNAE: B extrativa, C transformação, D energia,
# E água/esgoto/resíduos, F construção (divisões 05 a 43).
DIVISOES_INDUSTRIA = set(range(5, 44))

# Faixa de colaboradores equivalente a cada Porte FIEA (critério de nº de
# empregados SEBRAE/IBGE, que difere entre indústria e comércio/serviços).
FAIXAS = {
    "Indústria": {"Micro": "até 19", "Pequena": "20 a 99", "Média": "100 a 499", "Grande": "500 ou mais"},
    "Não indústria": {"Micro": "até 9", "Pequena": "10 a 49", "Média": "50 a 99", "Grande": "100 ou mais"},
}
ORDEM_FAIXA = ["até 9", "até 19", "10 a 49", "20 a 99", "50 a 99", "100 ou mais", "100 a 499", "500 ou mais"]


def _ler_zip(caminho: Path, colunas: list[str], blocos: int = 500_000):
    with zipfile.ZipFile(caminho) as z:
        nome = z.namelist()[0]
        with z.open(nome) as f:
            yield from pd.read_csv(f, sep=";", header=None, names=colunas, dtype=str,
                                   encoding="latin-1", chunksize=blocos, keep_default_na=False,
                                   quotechar='"', on_bad_lines="skip")


def ler_estabelecimentos(caminho: Path, uf: str = "AL") -> pd.DataFrame:
    partes = [b[(b["uf"] == uf) & (b["situacao"] == ATIVA)] for b in _ler_zip(caminho, COLS_ESTAB)]
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=COLS_ESTAB)


def ler_empresas(caminho: Path, raizes: set[str]) -> pd.DataFrame:
    partes = [b[b["cnpj_basico"].isin(raizes)] for b in _ler_zip(caminho, COLS_EMPRESA)]
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=COLS_EMPRESA)


def ler_codigos(caminho: Path) -> dict[str, str]:
    if not caminho or not Path(caminho).exists():
        return {}
    tabela = pd.concat(_ler_zip(caminho, ["codigo", "descricao"]), ignore_index=True)
    return dict(zip(tabela["codigo"].str.strip(), tabela["descricao"].str.strip()))


def tipo_por_cnae(cnae: str) -> str:
    try:
        return "Indústria" if int(str(cnae)[:2]) in DIVISOES_INDUSTRIA else "Não indústria"
    except ValueError:
        return "Não indústria"


def consolidar_por_raiz(estab: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por empresa: a matriz, se estiver em AL; senão a filial mais antiga."""
    df = estab.copy()
    df["cnpj"] = df["cnpj_basico"] + df["cnpj_ordem"] + df["cnpj_dv"]
    df["_ordem"] = (df["matriz_filial"] != "1").astype(int)
    df = df.sort_values(["cnpj_basico", "_ordem", "data_inicio_atividade"])
    qtd = df.groupby("cnpj_basico").size().rename("QTD_ESTABELECIMENTOS")
    df = df.drop_duplicates("cnpj_basico").drop(columns="_ordem")
    return df.merge(qtd, left_on="cnpj_basico", right_index=True)


def formatar_tel(ddd: str, numero: str) -> str:
    d = "".join(ch for ch in f"{ddd}{numero}" if ch.isdigit())
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return ""


def faixa_colaboradores(tipo: str, porte_fiea: str) -> str:
    return FAIXAS.get(tipo, {}).get(str(porte_fiea or "").strip(), "")


def carregar_porte_fiea(caminho: Path) -> pd.DataFrame:
    """Porte FIEA e cobertura por CNPJ raiz, da base de relacionamento SESI/SENAI."""
    if not Path(caminho).exists():
        return pd.DataFrame(columns=["cnpj_basico", "porte_fiea", "sesi", "senai"])
    r = pd.read_excel(caminho, dtype=str).fillna("")
    r["cnpj_basico"] = r["CNPJ"].str.replace(r"\D", "", regex=True).str.zfill(14).str[:8]
    r["_ordem"] = pd.to_numeric(r["Porte"].str[:1], errors="coerce").fillna(9)
    r["porte_fiea"] = r["Porte"].str[2:].str.strip()
    cob = r.groupby("cnpj_basico")["COBERTURA"].agg(lambda s: set(s.str.upper()))
    porte = r.sort_values("_ordem").drop_duplicates("cnpj_basico").set_index("cnpj_basico")["porte_fiea"]
    out = pd.DataFrame({"porte_fiea": porte}).join(cob.rename("cob"))
    out["sesi"] = out["cob"].map(lambda c: "SESI" in c)
    out["senai"] = out["cob"].map(lambda c: "SENAI" in c)
    return out.drop(columns="cob").reset_index()
