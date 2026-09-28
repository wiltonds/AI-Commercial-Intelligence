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

# Régua de indústria do Sistema (docs/arquitetura_dados.md): CNAE PRINCIPAL
# na Tabela DN da CNI (1.298 CNAEs). Ela inclui serviços que a seção IBGE
# não conta como indústria (engenharia, reparação de veículos, telecom...).
ARQ_TABELA_DN = Path(__file__).resolve().parents[2] / "config" / "referencia" / "tabela_dn_cni.csv"

# Faixa de colaboradores equivalente a cada Porte FIEA (critério de nº de
# empregados SEBRAE/IBGE, que difere entre indústria e comércio/serviços).
FAIXAS = {
    "Indústria fora da Base Mestre": {"Micro": "até 19", "Pequena": "20 a 99", "Média": "100 a 499", "Grande": "500 ou mais"},
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


def _cnae7(valor) -> str:
    d = "".join(ch for ch in str(valor or "").split(".")[0] if ch.isdigit())
    return d.zfill(7) if d else ""


def carregar_regua_industria(tabela_dn: Path = ARQ_TABELA_DN,
                             base_mestre: Path | None = None) -> tuple[set[str], str]:
    """CNAEs que contam como indústria, e de onde veio a régua.

    1. Tabela DN da CNI, se estiver em config/referencia/tabela_dn_cni.csv
       (primeira coluna com o código CNAE, em qualquer formato).
    2. Senão, aproximação: os CNAEs principais presentes na Base Mestre —
       que foi montada com a própria Tabela DN.
    """
    if Path(tabela_dn).exists():
        t = pd.read_csv(tabela_dn, dtype=str, sep=None, engine="python", encoding="utf-8-sig")
        codigos = {c for c in t.iloc[:, 0].map(_cnae7) if c}
        return codigos, f"Tabela DN da CNI ({len(codigos)} CNAEs)"
    if base_mestre is not None and Path(base_mestre).exists():
        b = pd.read_csv(base_mestre, dtype=str, usecols=["SEBRAE_cnae_norm"], encoding="utf-8-sig")
        codigos = {c for c in b["SEBRAE_cnae_norm"].map(_cnae7) if c}
        return codigos, f"aproximação: CNAEs da Base Mestre ({len(codigos)}) — copie a Tabela DN para config/referencia/"
    raise FileNotFoundError("Sem Tabela DN nem Base Mestre para definir o que é indústria.")


def tipo_empresa(cnae: str, na_base_mestre: bool, regua: set[str]) -> str:
    if na_base_mestre:
        return "Indústria"
    return "Indústria fora da Base Mestre" if _cnae7(cnae) in regua else "Não indústria"


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
