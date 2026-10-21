"""Sinal de obra nova a partir do Cadastro Nacional de Obras (CNO).

Fonte: dados abertos da Receita Federal (arquivo cno.zip), layout oficial
em config/fontes.yaml -> cno.url_layout. O zip traz, entre outros:

- CNO.CSV           uma linha por obra (responsável, município, UF,
                    área, situação, datas)
- CNO_VINCULOS.CSV  outros contribuintes vinculados à obra ao longo do
                    tempo (construtora, incorporadora, consórcio...)

Por que isso é sinal comercial: obra nova = canteiro com trabalhador
exposto a risco (SST: PGR, PCMSO, NRs) e equipe a qualificar. O CNPJ do
responsável e dos vínculos casa direto com a Base Mestre pelo CNPJ raiz.

A Receita não publica o CPF de responsável pessoa física (LGPD) — o
campo vem em branco. Este módulo só gera sinal para CNPJ, que é o
recorte B2B de qualquer forma.

Tudo aqui é função pura sobre DataFrame (testável sem rede); o download
e a gravação ficam em jobs/coletar_cno.py.
"""
from __future__ import annotations

import csv
import io
import math
import unicodedata
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

QUALIFICACOES = {
    "0070": "Proprietário do imóvel",
    "0057": "Dono da obra",
    "0064": "Incorporador de construção civil",
    "0053": "Pessoa jurídica construtora",
    "0111": "Sociedade líder de consórcio",
    "0109": "Consórcio",
    "0110": "Construção em nome coletivo",
}

SITUACAO_ATIVA = "02"
UFS_ALAGOAS = {"AL", "ALAGOAS"}

# Nome da coluna no layout oficial (normalizado) -> nome interno.
_MAPA_OBRAS = {
    "cno": "cno",
    "data de inicio": "data_inicio",
    "data de inicio da responsabilidade": "data_inicio_responsabilidade",
    "data de registro": "data_registro",
    "cno vinculado": "cno_vinculado",
    "cep": "cep",
    "ni do responsavel": "ni_responsavel",
    "qualificacao do responsavel": "qualificacao",
    "nome": "nome_obra",
    "codigo do municipio": "codigo_municipio",
    "nome do municipio": "municipio",
    "bairro": "bairro",
    "estado": "uf",
    "unidade de medida": "unidade_medida",
    "area total": "area_total",
    "situacao": "situacao",
    "data da situacao": "data_situacao",
    "nome empresarial": "nome_empresarial",
}

_MAPA_VINCULOS = {
    "cno": "cno",
    "data de inicio": "data_inicio",
    "data de fim": "data_fim",
    "data de registro": "data_registro",
    "qualificacao do contribuinte": "qualificacao",
    "ni do responsavel": "ni_responsavel",
}


# ------------------------------------------------------------
# Normalização
# ------------------------------------------------------------

def _normalizar_texto(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.replace("_", " ").lower().split())


def renomear_colunas(df: pd.DataFrame, mapa: dict[str, str]) -> pd.DataFrame:
    """Renomeia pelo layout oficial, tolerando acento, caixa e '_' vs espaço.

    Colunas fora do layout são descartadas — o job não quebra se a Receita
    acrescentar um campo novo, e acusa erro claro se sumir um essencial.
    """
    renomear = {}
    for coluna in df.columns:
        chave = _normalizar_texto(coluna)
        if chave in mapa:
            renomear[coluna] = mapa[chave]
    return df.rename(columns=renomear)[list(dict.fromkeys(renomear.values()))]


def _so_digitos(serie: pd.Series) -> pd.Series:
    return serie.fillna("").astype(str).str.replace(r"\D", "", regex=True)


def _para_numero(serie: pd.Series) -> pd.Series:
    texto = serie.fillna("").astype(str).str.strip()
    # aceita "1.234,56" e "1234.56"
    tem_virgula = texto.str.contains(",", regex=False)
    texto = texto.where(~tem_virgula, texto.str.replace(".", "", regex=False))
    texto = texto.str.replace(",", ".", regex=False)
    return pd.to_numeric(texto, errors="coerce")


# ------------------------------------------------------------
# Leitura do zip (streaming, só o recorte de AL)
# ------------------------------------------------------------

def _achar_membro(zf: zipfile.ZipFile, nome: str) -> str:
    """Acha 'cno.csv' / 'cno_vinculos.csv' sem depender de caixa ou pasta."""
    alvo = nome.lower()
    for membro in zf.namelist():
        if Path(membro).name.lower() == alvo:
            return membro
    raise FileNotFoundError(
        f"'{nome}' não encontrado no zip. Arquivos presentes: {zf.namelist()}"
    )


def _detectar_formato(amostra: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "latin1"):
        try:
            texto = amostra.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    primeira_linha = texto.splitlines()[0] if texto else ""
    try:
        separador = csv.Sniffer().sniff(primeira_linha, delimiters=",;|").delimiter
    except csv.Error:
        separador = ","
    return encoding, separador


def _ler_em_blocos(zf, membro, mapa, filtro, tamanho_bloco=200_000):
    with zf.open(membro) as bruto:
        amostra = bruto.read(4096)
    encoding, separador = _detectar_formato(amostra)

    partes = []
    with zf.open(membro) as bruto:
        texto = io.TextIOWrapper(bruto, encoding=encoding, newline="")
        for bloco in pd.read_csv(
            texto, sep=separador, dtype=str, chunksize=tamanho_bloco,
            keep_default_na=False,
        ):
            bloco = renomear_colunas(bloco, mapa)
            bloco = filtro(bloco)
            if len(bloco):
                partes.append(bloco)

    if not partes:
        return pd.DataFrame(columns=list(dict.fromkeys(mapa.values())))
    return pd.concat(partes, ignore_index=True)


def ler_zip_cno(caminho_zip: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lê o cno.zip nacional e devolve (obras de AL, vínculos dessas obras).

    O arquivo nacional tem milhões de linhas; lê em blocos e guarda só AL.
    """
    with zipfile.ZipFile(caminho_zip) as zf:
        obras = _ler_em_blocos(
            zf, _achar_membro(zf, "cno.csv"), _MAPA_OBRAS,
            lambda b: b[b["uf"].str.strip().str.upper().isin(UFS_ALAGOAS)],
        )
        faltando = {"cno", "uf", "ni_responsavel", "situacao"} - set(obras.columns)
        if faltando:
            raise ValueError(f"Layout do CNO mudou — colunas ausentes: {faltando}")

        cnos_al = set(obras["cno"])
        try:
            membro_vinc = _achar_membro(zf, "cno_vinculos.csv")
        except FileNotFoundError:
            vinculos = pd.DataFrame(columns=list(dict.fromkeys(_MAPA_VINCULOS.values())))
        else:
            vinculos = _ler_em_blocos(
                zf, membro_vinc, _MAPA_VINCULOS,
                lambda b: b[b["cno"].isin(cnos_al)],
            )

    return obras, vinculos


# ------------------------------------------------------------
# Regras de negócio
# ------------------------------------------------------------

def filtrar_obras_recentes(
    obras: pd.DataFrame, hoje: date, janela_dias: int
) -> pd.DataFrame:
    """Obras de AL, ATIVAS, iniciadas (ou registradas) dentro da janela."""
    df = obras.copy()
    df["situacao"] = _so_digitos(df["situacao"]).str.zfill(2)
    df = df[df["situacao"] == SITUACAO_ATIVA]

    inicio = pd.to_datetime(df.get("data_inicio"), errors="coerce")
    registro = pd.to_datetime(df.get("data_registro"), errors="coerce")
    df["data_evento"] = inicio.fillna(registro)

    limite = pd.Timestamp(hoje) - pd.Timedelta(days=janela_dias)
    return df[df["data_evento"] >= limite].copy()


def extrair_sinais(
    obras: pd.DataFrame, vinculos: pd.DataFrame, hoje: date
) -> pd.DataFrame:
    """Uma linha por (CNPJ, obra): o responsável e cada vínculo PJ vigente."""
    base = obras.copy()
    base["area_total"] = _para_numero(base.get("area_total", pd.Series(dtype=str)))

    colunas_obra = [
        c for c in ["cno", "nome_obra", "municipio", "bairro", "area_total",
                    "unidade_medida", "data_evento"]
        if c in base.columns
    ]

    responsaveis = base[colunas_obra].copy()
    # data em que o fato ficou público: base do selo "novo"
    responsaveis["data_publicacao"] = pd.to_datetime(
        base.get("data_registro"), errors="coerce").fillna(base["data_evento"])
    responsaveis["cnpj"] = _so_digitos(base["ni_responsavel"])
    responsaveis["qualificacao"] = _so_digitos(base["qualificacao"]).str.zfill(4)
    responsaveis["papel"] = "responsável"
    responsaveis["nome_empresarial"] = base.get("nome_empresarial", "")

    partes = [responsaveis]

    if len(vinculos):
        vinc = vinculos.copy()
        fim = pd.to_datetime(vinc.get("data_fim"), errors="coerce")
        vinc = vinc[fim.isna() | (fim >= pd.Timestamp(hoje))]
        registro_vinc = pd.to_datetime(vinc.get("data_registro"), errors="coerce")
        vinc = vinc.drop(columns=["data_registro", "data_inicio", "data_fim"], errors="ignore")
        vinc = vinc.assign(_registro=registro_vinc).merge(base[colunas_obra], on="cno", how="inner")
        vinc["data_publicacao"] = vinc["_registro"].fillna(vinc["data_evento"])
        vinc["cnpj"] = _so_digitos(vinc["ni_responsavel"])
        vinc["qualificacao"] = _so_digitos(vinc["qualificacao"]).str.zfill(4)
        vinc["papel"] = "vínculo"
        vinc["nome_empresarial"] = ""
        partes.append(vinc[responsaveis.columns])

    sinais = pd.concat(partes, ignore_index=True)
    sinais = sinais[sinais["cnpj"].str.len() == 14]  # CPF vem vazio; só PJ
    sinais["cnpj_basico"] = sinais["cnpj"].str[:8]
    sinais["qualificacao_desc"] = (
        sinais["qualificacao"].map(QUALIFICACOES).fillna("Outra")
    )
    # responsável ganha do vínculo quando a mesma empresa aparece nos dois
    sinais = sinais.sort_values("papel").drop_duplicates(["cnpj", "cno"])
    return sinais.reset_index(drop=True)


def pontuar(sinais: pd.DataFrame, hoje: date, regra: dict) -> pd.DataFrame:
    """Peso da obra (porte pela área) x decaimento linear até a validade.

    Regra transparente e editável em config/fontes.yaml, pelo mesmo
    motivo do score de semelhança: precisa ser defensável na frente da
    controladoria, não uma caixa-preta.
    """
    df = sinais.copy()
    validade = int(regra.get("validade_dias", 120))
    peso = pd.Series(float(regra.get("peso_base", 3)), index=df.index)
    for limiar, bonus in sorted((regra.get("bonus_area_m2") or {}).items()):
        peso += (df["area_total"].fillna(0) >= float(limiar)) * float(bonus)

    idade = (pd.Timestamp(hoje) - pd.to_datetime(df["data_evento"])).dt.days
    fator = (1 - idade.clip(lower=0) / validade).clip(lower=0)

    df["tipo_sinal"] = regra.get("tipo", "obra_nova")
    df["fonte"] = "CNO / Receita Federal"
    df["idade_dias"] = idade
    df["peso"] = peso
    df["validade_dias"] = validade
    df["score_momento"] = (peso * fator).round(2)
    df["descricao"] = df.apply(_descrever, axis=1)
    return df.sort_values("score_momento", ascending=False).reset_index(drop=True)


def _descrever(linha) -> str:
    area = linha.get("area_total")
    area_txt = (
        ", " + f"{area:,.0f}".replace(",", ".") + f" {str(linha.get('unidade_medida') or 'm²').strip()}"
        if isinstance(area, (int, float)) and not math.isnan(area) and area > 0
        else ""
    )
    nome = str(linha.get("nome_obra") or "").strip() or "Obra sem nome"
    return (
        f"{nome} — {str(linha.get('municipio') or '').strip().title()}{area_txt} "
        f"({linha['qualificacao_desc'].lower()}, {linha['papel']})"
    )


def cruzar_com_base(sinais: pd.DataFrame, empresas: pd.DataFrame) -> pd.DataFrame:
    """Marca quem já está no universo da Base Mestre e traz o relacionamento.

    Quem não está na base NÃO é descartado: o dono de uma obra pode não
    ser indústria (ex.: um atacarejo erguendo loja nova), mas a
    construtora vinculada é — e ambos são informação comercial.
    """
    colunas = [c for c in ["CNPJ_BASICO", "razao_social", "Porte",
                           "STATUS_RELACIONAMENTO_REAL", "CNAE PRIMARIO"]
               if c in empresas.columns]
    ref = empresas[colunas].drop_duplicates("CNPJ_BASICO")
    df = sinais.merge(ref, left_on="cnpj_basico", right_on="CNPJ_BASICO", how="left")
    df["na_base_mestre"] = df["CNPJ_BASICO"].notna()
    nome = df["razao_social"].fillna(df["nome_empresarial"]).replace("", pd.NA)
    # vínculos não trazem nome no CNO: mostra o CNPJ para o comercial consultar
    df["razao_social"] = nome.fillna("(sem nome no CNO) CNPJ " + df.get("cnpj", df["cnpj_basico"]))
    return df.drop(columns=["CNPJ_BASICO"])
