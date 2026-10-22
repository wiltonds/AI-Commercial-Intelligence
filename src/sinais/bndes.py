"""Financiamentos do BNDES para empresas de AL (dados abertos, com CNPJ).

Financiamento contratado é investimento confirmado: a empresa vai comprar
máquina, ampliar, construir, inovar. Fonte: dadosabertos.bndes.gov.br, conjunto
"Operações de financiamento", dois arquivos:

  não automáticas  projetos maiores, direto com o BNDES, com descrição do projeto
  automáticas      a maior parte do volume: crédito via bancos credenciados
                   (BNDES Máquinas/FINAME, capital de giro...). Sem descrição,
                   mas com produto, instrumento, setor CNAE e porte.

Nem todo financiamento é de indústria, e tudo bem: um hotel que amplia vira obra
(SESI/SENAI na construção), um hospital que compra equipamento precisa de
manutenção e SST. Por isso cada operação recebe um SEGMENTO e a oferta muda
conforme o segmento (config/ofertas.yaml, financiamento_bndes).
"""
from __future__ import annotations

import io
import re
import unicodedata
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

PACOTE = "10e21ad1-568e-45e5-a8af-43f2c05ef1a2"
API_CKAN = "https://dadosabertos.bndes.gov.br/api/3/action/package_show?id=" + PACOTE
URL_FONTE = "https://dadosabertos.bndes.gov.br/dataset/operacoes-financiamento"


def _n(t) -> str:
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", t)


def achar_recursos(pacote: dict, automaticas: bool = False) -> list[tuple[str, str]]:
    """(origem, url) dos arquivos de operações (CSV/ZIP), sem dicionários."""
    urls = []
    for r in pacote["result"]["resources"]:
        nome, fmt = _n(r.get("name", "")), _n(r.get("format", ""))
        if "dicionario" in nome or fmt not in ("csv", "zip"):
            continue
        if "naoautomatica" in nome:
            urls.append(("não automática", r["url"]))
        elif automaticas and "automatica" in nome:
            urls.append(("automática", r["url"]))
    return urls


def _col(cols, *nomes, obrigatoria: bool = True, contem: tuple = (), evita: tuple = ()):
    """Acha a coluna pelo nome (normalizado), mesmo com variações entre arquivos do BNDES.

    1) nome exato; 2) começa com o nome; 3) contém todas as palavras de `contem`
    e nenhuma de `evita` (ex.: 'valor' + 'operacao', sem 'desembolsado').
    """
    alvo = {c: _n(c) for c in cols}
    for n in nomes:
        for c, k in alvo.items():
            if k == _n(n):
                return c
    for n in nomes:
        for c, k in alvo.items():
            if k.startswith(_n(n)):
                return c
    if contem:
        for c, k in alvo.items():
            if all(_n(p) in k for p in contem) and not any(_n(p) in k for p in evita):
                return c
    if obrigatoria:
        raise KeyError(f"coluna não encontrada: {nomes}. Colunas: {list(cols)}")
    return None


def _numero(serie: pd.Series) -> pd.Series:
    """Aceita '1234.56' e '1.234,56'."""
    s = serie.fillna("").astype(str).str.strip()
    br = s.str.contains(",")
    s = s.where(~br, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(s, errors="coerce")


# ------------------------------------------------------------
# Segmento: onde o SENAI/SESI entra muda conforme a atividade
# ------------------------------------------------------------
SEGMENTOS = ["Indústria", "Construção", "Utilidade pública", "Agropecuária", "Comércio e serviços"]


def segmento(codigo_cnae, setor_nome="") -> str:
    """Pela divisão CNAE (2 primeiros dígitos); se não houver, pelo nome do setor."""
    m = re.search(r"\d{2}", str(codigo_cnae or ""))
    if m:
        d = int(m.group())
        if 1 <= d <= 3:
            return "Agropecuária"
        if 5 <= d <= 33:
            return "Indústria"
        if 35 <= d <= 39:
            return "Utilidade pública"
        if 41 <= d <= 43:
            return "Construção"
        return "Comércio e serviços"
    s = _n(setor_nome)
    if "agropecu" in s:
        return "Agropecuária"
    if "construcao" in s:
        return "Construção"
    if "industria" in s or "extrativ" in s:
        return "Indústria"
    if "infraestrutura" in s or "energia" in s or "saneamento" in s:
        return "Utilidade pública"
    return "Comércio e serviços" if s else "Não informado"


# ------------------------------------------------------------
# Leitura (em pedaços: o arquivo das automáticas é grande)
# ------------------------------------------------------------

def _abrir_texto(fonte) -> tuple[io.TextIOBase, str]:
    if isinstance(fonte, (bytes, bytearray)):
        bruto = fonte
    else:
        with open(fonte, "rb") as f:
            bruto = f.read(200_000)
    enc = "utf-8-sig"
    try:
        bruto[:200_000].decode("utf-8-sig")
    except UnicodeDecodeError:
        enc = "latin-1"
    primeira = bruto[:5000].decode(enc, errors="ignore").splitlines()[0]
    sep = ";" if primeira.count(";") >= primeira.count(",") else ","
    if isinstance(fonte, (bytes, bytearray)):
        return io.StringIO(fonte.decode(enc, errors="replace")), sep
    return open(fonte, encoding=enc, errors="replace", newline=""), sep


def _valor_col(c):
    for contem in (("valor", "contratad"), ("valor", "operacao")):
        col = _col(c, "valor contratado reais", "valor da operacao reais", obrigatoria=False,
                   contem=contem, evita=("desembols", "dolar", "usd"))
        if col:
            return col
    return _col(c, "valor", contem=("valor",), evita=("desembols",))


def datas(s: pd.Series) -> pd.Series:
    """Datas do BNDES: o arquivo das automáticas vem em AAAA-MM-DD e o das não automáticas
    em DD/MM/AAAA. dayfirst=True num AAAA-MM-DD trocava dia e mês (12/08 virava 08/12)."""
    t = s.fillna("").astype(str).str.strip().str[:10]
    iso = pd.to_datetime(t, format="%Y-%m-%d", errors="coerce")
    return iso.fillna(pd.to_datetime(t, format="%d/%m/%Y", errors="coerce"))


ARQUIVO = {"automática": "Operações indiretas automáticas", "não automática": "Operações não automáticas"}


def _padronizar(df: pd.DataFrame, origem: str) -> pd.DataFrame:
    c = df.columns
    opc = lambda *n: _col(c, *n, obrigatoria=False)  # noqa: E731
    proj, instr = opc("descricao do projeto"), opc("instrumento financeiro")
    cod, setor = opc("subsetor cnae codigo"), opc("setor cnae")
    porte, banco, nat = opc("porte do cliente"), opc("instituicao financeira credenciada"), opc("natureza do cliente")
    vazio = pd.Series("", index=df.index)
    out = pd.DataFrame({
        "cliente": df[_col(c, "cliente")],
        "cnpj": df[_col(c, "cnpj", "cpf_cnpj")].fillna("").astype(str).str.replace(r"\D", "", regex=True).str.zfill(14),
        "projeto": (df[proj] if proj else df[instr] if instr else vazio).fillna(""),
        "uf": df[_col(c, "uf")].fillna("").str.strip().str.upper(),
        "municipio_bndes": df[_col(c, "municipio")].fillna(""),
        "data_contratacao": datas(df[_col(c, "data da contratacao")]),
        "valor": _numero(df[_valor_col(c)]),
        "produto": df[_col(c, "produto")].fillna(""),
        "inovacao": df[_col(c, "inovacao")].fillna("").str.upper(),
        "natureza": (df[nat] if nat else vazio).fillna(""),
        "subsetor": df[_col(c, "subsetor cnae nome")].fillna("").str.strip(),
        "subsetor_codigo": (df[cod] if cod else vazio).fillna(""),
        "setor_cnae": (df[setor] if setor else vazio).fillna(""),
        "porte_bndes": (df[porte] if porte else vazio).fillna(""),
        "banco": (df[banco] if banco else vazio).fillna(""),
        "origem": origem,
    })
    out["segmento"] = [segmento(a, b) for a, b in zip(out["subsetor_codigo"], out["setor_cnae"])]
    return out


def ler_operacoes(fonte, origem: str = "não automática", uf: str | None = "AL",
                  pedaco: int = 200_000) -> pd.DataFrame:
    """Lê o CSV do BNDES (bytes ou caminho) e devolve só as operações da UF."""
    arq, sep = _abrir_texto(fonte)
    partes = []
    with arq:
        for bloco in pd.read_csv(arq, sep=sep, dtype=str, chunksize=pedaco, on_bad_lines="skip"):
            if uf:
                col_uf = _col(bloco.columns, "uf")
                bloco = bloco[bloco[col_uf].fillna("").str.strip().str.upper() == uf]
            if not bloco.empty:
                partes.append(_padronizar(bloco, origem))
    return pd.concat(partes, ignore_index=True) if partes else _padronizar(pd.DataFrame(columns=[
        "cliente", "cnpj", "uf", "municipio", "data da contratacao", "valor contratado reais",
        "produto", "inovacao", "subsetor cnae nome"]), origem)


# ------------------------------------------------------------
# Sinais: uma linha por empresa (soma das operações recentes)
# ------------------------------------------------------------

# ------------------------------------------------------------
# CNPJ mascarado: as operações automáticas mostram só 9 dígitos (**.*XX.XXX/XXXX-**)
# ------------------------------------------------------------
_SUFIXOS = {"LTDA", "ME", "EPP", "SA", "S", "A", "EIRELI", "CIA", "DE", "DA", "DO", "DOS", "DAS", "E", "EM", "LTD"}


def _tokens_nome(nome) -> set[str]:
    t = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore").decode().upper()
    return {p for p in re.split(r"[^A-Z0-9]+", t) if len(p) > 1 and p not in _SUFIXOS}


def mascarado(cnpj: str) -> bool:
    """CNPJ das automáticas: 14 dígitos com os 5 primeiros zerados (só 9 visíveis)."""
    return str(cnpj).startswith("00000")


def ligar_mascarados(op: pd.DataFrame, empresas: pd.DataFrame) -> pd.Series:
    """cnpj_basico da base para cada operação; nos mascarados, pelos dígitos visíveis + nome.

    Dígitos visíveis = posições 4 a 8 da raiz + ordem (filial). Vários CNPJs da base
    podem ter os mesmos 5 dígitos, então o nome confirma: pelo menos metade das
    palavras do nome (sem LTDA, S/A...) em comum, contando pelo nome mais longo.
    """
    base = empresas[["cnpj", "cnpj_basico", "razao_social"]].dropna(subset=["cnpj"]).copy()
    base["chave"] = base["cnpj"].astype(str).str.zfill(14).str[3:8]
    por_chave = {k: g for k, g in base.groupby("chave")}
    saida = []
    for cnpj, cliente in zip(op["cnpj"], op["cliente"]):
        if not mascarado(cnpj):
            saida.append(str(cnpj)[:8])
            continue
        cand = por_chave.get(str(cnpj)[5:10])
        achou = None
        if cand is not None:
            tc = _tokens_nome(cliente)
            melhor = 0.0
            for _, r in cand.iterrows():
                tb = _tokens_nome(r["razao_social"])
                if not tc or not tb:
                    continue
                sim = len(tc & tb) / max(len(tc), len(tb))
                if sim >= 0.5 and sim > melhor:
                    melhor, achou = sim, r["cnpj_basico"]
        saida.append(achou if achou else "*" + str(cnpj)[5:10] + "**")  # não identificado: chave própria
    return pd.Series(saida, index=op.index)


def _cnpj_exibicao(cnpj: str) -> str:
    c = str(cnpj).zfill(14)
    if mascarado(c):
        v = c[5:]
        return f"**.*{v[0:2]}.{v[2:5]}/{v[5:9]}-**"
    return c


def _mi(v: float) -> str:
    return f"{v / 1e6:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def para_sinais(op: pd.DataFrame, empresas: pd.DataFrame, hoje: date, meses: int = 24,
                peso: float = 4, validade_dias: int = 365, valor_min: float = 100_000) -> pd.DataFrame:
    """Empresas privadas de AL com financiamento nos últimos N meses, no formato padrão de sinais.

    valor_min tira o miúdo (Cartão BNDES, giro pequeno) que não muda nada na empresa.
    """
    from src.tools.municipios import padronizar

    limite = pd.Timestamp(hoje) - pd.DateOffset(months=meses)
    nat = op["natureza"].str.upper()
    op = op[(op["uf"] == "AL") & (op["data_contratacao"] >= limite)
            & (nat.str.contains("PRIVAD", na=False) | nat.eq(""))
            & op["cnpj"].str.fullmatch(r"\d{14}") & op["cnpj"].ne("0" * 14)].copy()
    if op.empty:
        return pd.DataFrame()
    op["cnpj_basico"] = ligar_mascarados(op, empresas)

    # cada operação como linha conferível no arquivo do BNDES
    op["_linha"] = (op["data_contratacao"].dt.strftime("%d/%m/%Y") + " · R$ " + op["valor"].map(_mi) + " mi · "
                    + op["produto"].str.strip() + op["banco"].map(lambda b: f" · {b.strip().title()}"
                                                                   if str(b).strip().strip("-") else ""))
    # por empresa: total, quantidade, a operação maior dá o projeto e o segmento
    op = op.sort_values("valor", ascending=False)
    g = op.groupby("cnpj_basico", sort=False)
    emp = g.first()
    emp["valor"] = g["valor"].sum()
    emp["n_operacoes"] = g.size()
    emp["data_contratacao"] = g["data_contratacao"].max()
    emp["inovacao"] = g["inovacao"].agg(lambda s: "SIM" if s.str.startswith("S").any() else "NÃO")
    emp["produtos"] = g["produto"].agg(lambda s: ", ".join(dict.fromkeys(p.strip() for p in s if p.strip()))[:120])
    emp["detalhe_fonte"] = g["_linha"].agg(lambda s: " | ".join(s.head(8)))
    emp["arquivo_fonte"] = g["origem"].agg(lambda s: " e ".join(dict.fromkeys(ARQUIVO.get(o, o) for o in s)))
    emp = emp[emp["valor"] >= valor_min].reset_index()
    if emp.empty:
        return pd.DataFrame()

    ref = empresas[["cnpj_basico", "cnpj", "razao_social", "STATUS_RELACIONAMENTO_REAL", "Porte", "tipo_empresa",
                    "municipio"]].rename(columns={"municipio": "municipio_base", "cnpj": "cnpj_base"})
    df = emp.merge(ref, on="cnpj_basico", how="left")
    na_base = df["cnpj_base"].notna()
    mask = df["cnpj"].map(mascarado)
    df["casamento"] = np.select([na_base & ~mask, na_base & mask, mask],
                                ["por CNPJ", "por CNPJ parcial + nome", "não identificado (CNPJ mascarado)"],
                                "por CNPJ")
    df["cnpj"] = df["cnpj_base"].where(na_base & mask, df["cnpj"].map(_cnpj_exibicao))
    df["na_base_mestre"] = df["tipo_empresa"].eq("Indústria")
    df["razao_social"] = df["razao_social"].fillna(df["cliente"])
    df["STATUS_RELACIONAMENTO_REAL"] = df["STATUS_RELACIONAMENTO_REAL"].fillna("Fora da Base Mestre")
    df["Porte"] = df["Porte"].fillna(df["porte_bndes"].str.upper())
    mun = padronizar(df["municipio_bndes"].str.title())
    mun = mun.where(~mun.str.lower().str.startswith("sem "), "")
    df["municipio"] = mun.where(mun.ne(""), df["municipio_base"].fillna(""))
    df["municipio"] = df["municipio"].replace("", "Não informado")

    qtd = df["n_operacoes"].map(lambda n: "" if n == 1 else f" em {n} operações")
    via = df["banco"].map(lambda b: f" via {b.strip().title()}" if str(b).strip() else "")
    proj = df["projeto"].str.strip().str[:140]
    df["descricao"] = ("Financiamento BNDES de R$ " + df["valor"].map(_mi) + " mi" + qtd + via
                       + " (" + df["segmento"] + ")" + proj.map(lambda p: f": {p}" if p else ""))
    df["tipo_sinal"] = "financiamento_bndes"
    df["tema"] = df["inovacao"].map(lambda x: "Inovação" if x.startswith("S") else "Investimento")
    df["data_publicacao"] = df["data_evento"] = df["data_contratacao"]
    idade = (pd.Timestamp(hoje) - df["data_contratacao"]).dt.days.clip(lower=0)
    bonus = (df["valor"] >= 1e6).astype(float) + (df["valor"] >= 10e6).astype(float)
    df["idade_dias"], df["peso"], df["validade_dias"] = idade, peso + bonus, validade_dias
    df["score_momento"] = (df["peso"] * (1 - idade / validade_dias).clip(lower=0)).round(2)
    df["fonte"], df["url_fonte"] = "BNDES · dados abertos", URL_FONTE
    df["produto"] = df["produtos"]
    cols = ["tipo_sinal", "tema", "segmento", "descricao", "cnpj_basico", "cnpj", "razao_social",
            "STATUS_RELACIONAMENTO_REAL", "Porte", "na_base_mestre", "casamento", "municipio", "data_publicacao",
            "data_evento", "valor", "n_operacoes", "produto", "subsetor", "inovacao", "origem", "peso",
            "validade_dias", "idade_dias", "score_momento", "fonte", "url_fonte", "detalhe_fonte", "arquivo_fonte"]
    return df[cols].sort_values("score_momento", ascending=False).reset_index(drop=True)
