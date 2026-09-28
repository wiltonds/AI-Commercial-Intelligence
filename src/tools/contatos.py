"""Contatos por empresa — o "Apollo" da base: um cadastro de contato por CNPJ raiz.

A ideia é o contato virar ATRIBUTO da empresa, não um passo do sinal:
o job jobs/enriquecer_contatos.py consulta cada CNPJ uma vez, salva aqui,
e qualquer recorte do painel (CNO, segmento, município) já sai com
telefone, e-mail e responsável.

Fonte da versão 1: cadastro da Receita Federal via BrasilAPI (público):
telefones e e-mail cadastrais, endereço, CNAE principal e secundários e o
quadro societário (QSA), de onde sai o decisor — em empresa pequena e
média, quem decide é o sócio-administrador.

Cuidado de qualidade: muitas empresas cadastram o telefone/e-mail do
CONTADOR. Quando o mesmo contato aparece em vários CNPJs, ele é marcado
como provável contador e não conta como contato da empresa.

Tudo aqui é função pura (testável sem rede).
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
ARQ_CONTATOS = RAIZ / "data" / "contatos" / "CONTATOS_EMPRESAS.csv"
ARQ_RECEITA = RAIZ / "data" / "contatos" / "CONTATOS_RECEITA.csv"   # jobs/carregar_base_ampliada.py

COLUNAS = [
    "cnpj_basico", "cnpj", "razao_social", "nome_fantasia", "situacao",
    "municipio", "uf", "endereco", "cep",
    "telefone_1", "telefone_2", "whatsapp_provavel", "email",
    "decisor", "decisor_cargo", "socios",
    "cnae_principal", "cnaes_secundarios",
    "contato_de_contador", "confianca", "fonte", "atualizado_em",
]

# ordem de preferência do "decisor" dentro do QSA
CARGOS_DECISOR = [
    "socio-administrador", "socio administrador", "administrador", "presidente",
    "diretor", "titular", "empresario", "socio",
]
EMAIL_CONTABIL = re.compile(r"contab|contador|escritorio|assessoria|fiscal", re.I)


def _digitos(valor) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def formatar_telefone(bruto) -> str:
    d = _digitos(bruto)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return ""


def e_celular(telefone: str) -> bool:
    d = _digitos(telefone)
    return len(d) == 11 and d[2] == "9"


def _sem_acento(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", str(t or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def escolher_decisor(qsa: list[dict]) -> tuple[str, str]:
    """Sócio pessoa física com o cargo mais alto na lista de preferência."""
    pessoas = [s for s in (qsa or [])
               if str(s.get("identificador_de_socio", 2)) != "1" and s.get("nome_socio")]
    for cargo in CARGOS_DECISOR:
        for s in pessoas:
            if cargo in _sem_acento(s.get("qualificacao_socio")):
                return s["nome_socio"].title(), s.get("qualificacao_socio") or ""
    if pessoas:
        return pessoas[0]["nome_socio"].title(), pessoas[0].get("qualificacao_socio") or ""
    return "", ""


def extrair_contato(dados: dict) -> dict:
    """Resposta da BrasilAPI (/api/cnpj/v1/{cnpj}) -> uma linha de contato."""
    cnpj = _digitos(dados.get("cnpj")).zfill(14)
    tel1 = formatar_telefone(dados.get("ddd_telefone_1"))
    tel2 = formatar_telefone(dados.get("ddd_telefone_2"))
    decisor, cargo = escolher_decisor(dados.get("qsa") or [])
    socios = "; ".join(
        f"{s['nome_socio'].title()} ({s.get('qualificacao_socio') or 'sócio'})"
        for s in (dados.get("qsa") or []) if s.get("nome_socio")
    )
    principal = dados.get("cnae_fiscal")
    secundarios = [c for c in (dados.get("cnaes_secundarios") or []) if c.get("codigo")]
    endereco = ", ".join(p for p in [
        " ".join(x for x in [dados.get("descricao_tipo_de_logradouro") or dados.get("descricao_tipo_logradouro"), dados.get("logradouro")] if x),
        str(dados.get("numero") or "").strip(), dados.get("complemento") or "",
        dados.get("bairro") or "",
    ] if p and p.strip())
    return {
        "cnpj_basico": cnpj[:8], "cnpj": cnpj,
        "razao_social": dados.get("razao_social") or "",
        "nome_fantasia": dados.get("nome_fantasia") or "",
        "situacao": dados.get("descricao_situacao_cadastral") or "",
        "municipio": str(dados.get("municipio") or "").title(), "uf": dados.get("uf") or "",
        "endereco": endereco.title(), "cep": _digitos(dados.get("cep")),
        "telefone_1": tel1, "telefone_2": tel2,
        "whatsapp_provavel": next((t for t in (tel1, tel2) if e_celular(t)), ""),
        "email": str(dados.get("email") or "").strip().lower(),
        "decisor": decisor, "decisor_cargo": cargo, "socios": socios,
        "cnae_principal": f"{principal} - {dados.get('cnae_fiscal_descricao') or ''}" if principal else "",
        "cnaes_secundarios": "; ".join(f"{c['codigo']} - {c.get('descricao', '')}" for c in secundarios),
        "fonte": "Receita Federal (BrasilAPI)",
    }


def avaliar_qualidade(df: pd.DataFrame, limite_repeticao: int = 3) -> pd.DataFrame:
    """Marca contato de contador e dá a confiança de cada linha.

    alta   = tem decisor e um contato que não é de contador
    media  = tem contato que não é de contador, sem decisor
    baixa  = só contato de contador, ou nenhum contato
    """
    df = df.copy()
    for c in ("telefone_1", "telefone_2", "email", "decisor"):
        df[c] = df[c].fillna("").astype(str)
    valores = pd.concat([df["telefone_1"], df["telefone_2"], df["email"]])
    contagem = valores[valores != ""].value_counts()
    repetidos = set(contagem[contagem >= limite_repeticao].index)

    def _de_contador(v: str) -> bool:
        return bool(v) and (v in repetidos or bool(EMAIL_CONTABIL.search(v.split("@")[-1] if "@" in v else "")))

    flags = df[["telefone_1", "telefone_2", "email"]].map(_de_contador)
    df["contato_de_contador"] = flags.any(axis=1)
    tem_contato_util = ((df[["telefone_1", "telefone_2", "email"]] != "") & ~flags).any(axis=1)
    df["confianca"] = "baixa"
    df.loc[tem_contato_util, "confianca"] = "media"
    df.loc[tem_contato_util & (df["decisor"] != ""), "confianca"] = "alta"
    return df


def carregar_contatos(caminho: Path = ARQ_CONTATOS, receita: Path | None = ARQ_RECEITA) -> pd.DataFrame:
    """Contatos do robô (BrasilAPI) complementados pelos dados abertos da Receita.

    A Receita entra só onde falta: preenche e-mail/telefone vazios de quem o
    robô já consultou e acrescenta quem ele ainda não consultou (sem
    decisor). A confiança é recalculada sobre o conjunto.
    """
    base = (pd.read_csv(caminho, dtype=str, encoding="utf-8-sig").fillna("")
            if caminho.exists() else pd.DataFrame(columns=COLUNAS))
    base = base.reindex(columns=list(dict.fromkeys(COLUNAS + list(base.columns)))).fillna("")
    if receita is None or not Path(receita).exists():
        return base
    rec = pd.read_csv(receita, dtype=str, encoding="utf-8-sig").fillna("").drop_duplicates("cnpj_basico")
    campos = ["telefone_1", "telefone_2", "email"]
    if not base.empty:
        ref = rec.set_index("cnpj_basico")
        for c in campos:
            vazio = base[c].eq("")
            base.loc[vazio, c] = base.loc[vazio, "cnpj_basico"].map(ref[c]).fillna("")
    novos = rec[~rec["cnpj_basico"].isin(base["cnpj_basico"])].copy()
    novos["fonte"] = "Receita Federal (dados abertos)"
    todos = pd.concat([base, novos], ignore_index=True).reindex(columns=COLUNAS).fillna("")
    todos["whatsapp_provavel"] = [
        w or next((t for t in (a, b) if e_celular(t)), "")
        for w, a, b in zip(todos["whatsapp_provavel"], todos["telefone_1"], todos["telefone_2"])]
    return avaliar_qualidade(todos).astype(str).replace("nan", "")


def juntar_contatos(empresas: pd.DataFrame, contatos: pd.DataFrame,
                    chave: str = "cnpj_basico") -> pd.DataFrame:
    """Acrescenta as colunas de contato a qualquer tabela que tenha o CNPJ raiz."""
    cols = ["cnpj_basico", "telefone_1", "telefone_2", "whatsapp_provavel", "email",
            "decisor", "decisor_cargo", "cnaes_secundarios", "endereco", "confianca",
            "contato_de_contador", "atualizado_em"]
    if contatos.empty:
        return empresas.assign(**{c: "" for c in cols[1:]})
    ref = contatos[[c for c in cols if c in contatos.columns]].drop_duplicates("cnpj_basico")
    out = empresas.merge(ref, left_on=chave, right_on="cnpj_basico", how="left",
                         suffixes=("", "_contato"))
    if chave != "cnpj_basico" and "cnpj_basico" in out:
        out = out.drop(columns=["cnpj_basico"])
    return out
