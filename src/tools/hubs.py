"""Hubs: quem conecta muitas empresas de uma vez.

Um modelo que aprende com o passado enxerga EMPRESAS. Parte grande da
oportunidade está nas CONEXÕES: o escritório de contabilidade que atende
300 empresas, o sócio que controla 6 CNPJs. Abordar o hub abre a carteira.

Dois tipos, a partir dos dados que já coletamos:
  * canal (contato compartilhado): o mesmo e-mail/domínio ou telefone
    cadastrado em várias empresas — em geral, o escritório de contabilidade.
    Antes era tratado como ruído ("contato de contador"); aqui vira canal.
  * grupo (sócio em comum): a mesma pessoa no quadro societário de várias
    empresas — uma decisão, vários CNPJs.
"""
from __future__ import annotations

import re

import pandas as pd

GENERICOS = {"gmail.com", "hotmail.com", "yahoo.com.br", "yahoo.com", "outlook.com", "live.com", "bol.com.br",
             "uol.com.br", "terra.com.br", "icloud.com", "ig.com.br", "hotmail.com.br", "globo.com", "msn.com"}
CONTABIL = re.compile(r"contab|contador|contabil|escritorio|assessoria|consultoria|fiscal|cont\b", re.I)


def chave_email(email: str) -> str:
    """Domínio próprio agrupa o escritório inteiro; e-mail genérico (gmail...) só agrupa o mesmo endereço."""
    email = str(email or "").strip().lower()
    if "@" not in email:
        return ""
    dominio = email.split("@", 1)[1]
    return email if dominio in GENERICOS else "@" + dominio


def mapear_canais(contatos: pd.DataFrame, empresas: pd.DataFrame, minimo: int = 5) -> pd.DataFrame:
    """Um hub por e-mail/domínio ou telefone compartilhado por `minimo`+ empresas."""
    c = contatos.copy()
    registros = []
    for col, tipo in (("email", "e-mail"), ("telefone_1", "telefone"), ("telefone_2", "telefone")):
        if col not in c:
            continue
        chave = c[col].map(chave_email) if col == "email" else c[col].fillna("").astype(str)
        registros.append(pd.DataFrame({"hub": chave, "via": tipo, "cnpj_basico": c["cnpj_basico"]}))
    todos = pd.concat(registros, ignore_index=True)
    todos = todos[todos["hub"] != ""].drop_duplicates(["hub", "cnpj_basico"])
    return _resumir(todos, empresas, minimo, "canal")


def mapear_grupos(contatos: pd.DataFrame, empresas: pd.DataFrame, minimo: int = 3) -> pd.DataFrame:
    """Um hub por sócio (pessoa) presente no quadro de `minimo`+ empresas."""
    if "socios" not in contatos:
        return pd.DataFrame()
    linhas = []
    for raiz, socios in zip(contatos["cnpj_basico"], contatos["socios"].fillna("")):
        for s in str(socios).split(";"):
            nome = re.sub(r"\s*\(.*\)\s*$", "", s).strip()
            if len(nome.split()) >= 2 and not re.search(r"\b(ltda|s/?a|eireli|holding)\b", nome, re.I):
                linhas.append({"hub": nome.title(), "via": "sócio", "cnpj_basico": raiz})
    if not linhas:
        return pd.DataFrame()
    return _resumir(pd.DataFrame(linhas).drop_duplicates(["hub", "cnpj_basico"]), empresas, minimo, "grupo")


def _resumir(ligacoes: pd.DataFrame, empresas: pd.DataFrame, minimo: int, tipo: str) -> pd.DataFrame:
    e = empresas.drop_duplicates("cnpj_basico").set_index("cnpj_basico")
    lig = ligacoes.join(e, on="cnpj_basico", how="inner")          # só empresas do universo
    cont = lig.groupby("hub")["cnpj_basico"].nunique()
    lig = lig[lig["hub"].isin(cont[cont >= minimo].index)]
    if lig.empty:
        return pd.DataFrame()
    cliente = lig["situacao"].isin(["Ativo", "Inativo"])
    g = lig.assign(cliente=cliente, ativo=lig["situacao"].eq("Ativo")).groupby("hub")
    out = pd.DataFrame({
        "tipo": tipo,
        "via": g["via"].first(),
        "empresas": g["cnpj_basico"].nunique(),
        "ja_clientes": g["cliente"].sum(),
        "clientes_ativos": g["ativo"].sum(),
        "sem_compra": g.apply(lambda x: x.loc[~x["cliente"], "cnpj_basico"].nunique(), include_groups=False),
        "segmentos": g["segmento"].agg(lambda s: "; ".join(s.value_counts().head(3).index)),
        "exemplos": g["razao_social"].agg(lambda s: "; ".join(s.head(3))),
    })
    out["porta_de_entrada"] = out["ja_clientes"] > 0          # já temos relação com alguém da carteira
    out["provavel_contabilidade"] = out.index.to_series().str.contains(CONTABIL) if tipo == "canal" else False
    return out.reset_index().sort_values(["sem_compra", "empresas"], ascending=False)
