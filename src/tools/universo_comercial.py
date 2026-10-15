"""Universo comercial único (indústria + não indústria), uma linha por CNPJ raiz,
separado em dois públicos com tratamentos diferentes:

* Clientes (com relacionamento): já compraram de SESI ou SENAI — reter e expandir.
* Mercado (sem relacionamento): nunca compraram — conquistar, pela nota de potencial.

Duas réguas de porte que NUNCA se misturam:
* Porte Receita (faturamento): ME / EPP / DEMAIS, para todos.
* Porte FIEA (colaboradores): Micro / EPP / Média / Demais. Cliente usa o do cadastro
  (propostas + base de relacionamento); empresa nova fica "A confirmar" até ter o
  número de colaboradores (Apollo, comercial...). Nada de estimar pela Receita.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.tools.potencial import ORDEM_FAIXAS, segmento_cnae

RAIZ = Path(__file__).resolve().parents[2]
ARQ_POTENCIAL = RAIZ / "data" / "processed" / "POTENCIAL_MERCADO.csv"
ARQ_MEI = RAIZ / "data" / "processed" / "MEI_BASE_MESTRE.csv"

CLIENTE, MERCADO = "Cliente", "Sem relacionamento"
A_CONFIRMAR = "A confirmar"
ORDEM_PORTE_FIEA = ["Micro", "EPP", "Média", "Demais", A_CONFIRMAR]
ORDEM_PORTE_RECEITA = ["MICRO EMPRESA", "PEQUENO PORTE", "DEMAIS"]
MAPA_PORTE_FIEA = {"micro": "Micro", "pequena": "EPP", "epp": "EPP", "pequeno": "EPP",
                   "média": "Média", "media": "Média", "grande": "Demais", "demais": "Demais"}
COLUNAS = ["cnpj_basico", "Razão social", "Categoria", "Segmento", "CNAE", "Município", "Bairro",
           "Porte Receita", "Porte FIEA", "Unidade SESI", "Unidade SENAI", "unidades",
           "Relacionamento", "Situação", "Entidade", "Última compra",
           "Nota", "Potencial", "Motivo", "Alerta"]


def porte_fiea_padrao(valor: str) -> str:
    v = str(valor or "").strip().lower()
    return MAPA_PORTE_FIEA.get(v, A_CONFIRMAR) if v else A_CONFIRMAR


def _bool(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s
    return s.fillna("").astype(str).str.strip().str.upper().isin(["TRUE", "1", "SIM", "S", "VERDADEIRO"])


def _entidade(sesi: pd.Series, senai: pd.Series) -> pd.Series:
    out = pd.Series("—", index=sesi.index)
    out[sesi & ~senai] = "SESI"
    out[~sesi & senai] = "SENAI"
    out[sesi & senai] = "SESI + SENAI"
    return out


def _cnae_codigo(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce").map(lambda v: f"{int(v):07d}" if pd.notna(v) else "")


TIPO_LACUNA = "Indústria fora da Base Mestre"   # Base Ampliada: CNAE da tabela da CNI, fora do cadastro FIEA


def _bloco(df: pd.DataFrame, categoria, raiz: str, razao: str, cnae_cod: pd.Series, cnae_desc: str,
           porte: str, municipio: str, sesi: pd.Series, senai: pd.Series) -> pd.DataFrame:
    sesi, senai = _bool(sesi), _bool(senai)
    situacao = df.get("SITUACAO_CLIENTE", pd.Series("", index=df.index)).fillna("").replace("", "Sem compra")
    cliente = situacao.isin(["Ativo", "Inativo"]) | sesi | senai
    out = pd.DataFrame({
        "cnpj_basico": df[raiz].astype(str).str.replace(r"\D", "", regex=True).str.zfill(8).values,
        "Razão social": df[razao].values,
        "Categoria": categoria if isinstance(categoria, str) else pd.Series(categoria).values,
        "Segmento": cnae_cod.str[:2].map(segmento_cnae).values,
        "CNAE": [f"{c[:4]}-{c[4:5]}/{c[5:]} · {d}" if c else d for c, d in zip(cnae_cod, df[cnae_desc].fillna(""))],
        "Município": df[municipio].values,
        "Porte Receita": df[porte].values,
        "Relacionamento": [CLIENTE if c else MERCADO for c in cliente],
        "Situação": situacao.where(situacao != "Sem compra", "Sem compra").values,
        "Entidade": _entidade(sesi, senai).values,
        "Última compra": df.get("ULTIMA_COMPRA", pd.Series("", index=df.index)).fillna("").values,
    })
    for c in ["unidade_sesi", "unidade_senai", "unidades"]:
        out[c] = df[c].fillna("").values if c in df.columns else ""
    return out


def carregar_mei(caminho: Path = ARQ_MEI) -> set[str]:
    """CNPJ raiz que são MEI optante (jobs/carregar_base_ampliada.py, a partir do Simples da Receita)."""
    if not Path(caminho).exists():
        return set()
    return set(pd.read_csv(caminho, dtype=str, encoding="utf-8-sig")["cnpj_basico"].str.zfill(8))


def montar(mestre: pd.DataFrame, ampliada: pd.DataFrame, porte_fiea: pd.DataFrame,
           potencial: pd.DataFrame | None = None, mei: set[str] | None = None) -> pd.DataFrame:
    """mestre: Base Mestre consolidada por raiz (com colunas da carteira);
    ampliada: Base Ampliada (não indústrias, com colunas da carteira);
    porte_fiea: cnpj_basico, porte_fiea (cadastro); potencial: POTENCIAL_MERCADO.csv."""
    partes = []
    if not mestre.empty:
        cod = _cnae_codigo(mestre.get("SEBRAE_cnae_norm", pd.Series(index=mestre.index, dtype=str)))
        partes.append(_bloco(mestre, "Indústria", "CNPJ_BASICO", "razao_social", cod, "CNAE PRIMARIO",
                             "Porte", "Municipio", mestre.get("POSSUI_SESI", mestre.get("TEM_SESI")),
                             mestre.get("POSSUI_SENAI", mestre.get("TEM_SENAI"))))
    if not ampliada.empty:
        cod = ampliada["cnae_principal"].fillna("").astype(str).str.replace(r"\D", "", regex=True).str.zfill(7)
        # a lacuna ("Indústria fora da Base Mestre") tem CNAE industrial: entra como Indústria
        tipo = ampliada.get("Tipo", pd.Series("", index=ampliada.index)).fillna("")
        categoria = tipo.eq(TIPO_LACUNA).map({True: "Indústria", False: "Não indústria"})
        partes.append(_bloco(ampliada, categoria, "cnpj_basico", "razao_social", cod, "CNAE PRIMARIO",
                             "Porte", "Municipio", ampliada["POSSUI_SESI"], ampliada["POSSUI_SENAI"]))
    u = pd.concat(partes, ignore_index=True).drop_duplicates("cnpj_basico")
    u = u.rename(columns={"unidade_sesi": "Unidade SESI", "unidade_senai": "Unidade SENAI"})
    if mei:
        u = u[~(u["cnpj_basico"].isin(mei) & (u["Relacionamento"] == MERCADO))]

    # Porte FIEA: só do cadastro (clientes). Empresa nova = "A confirmar".
    pf = porte_fiea.drop_duplicates("cnpj_basico").set_index("cnpj_basico")["porte_fiea"] \
        if porte_fiea is not None and not porte_fiea.empty else pd.Series(dtype=str)
    u["Porte FIEA"] = u["cnpj_basico"].map(pf).map(porte_fiea_padrao)

    pot = potencial if potencial is not None else pd.DataFrame()
    if not pot.empty:
        pot = pot.assign(cnpj_basico=pot["cnpj_basico"].astype(str).str.zfill(8)).drop_duplicates("cnpj_basico")
        pot = pot.set_index("cnpj_basico")
        u["Bairro"] = u["cnpj_basico"].map(pot["bairro"]).fillna("")
        u["Nota"] = pd.to_numeric(u["cnpj_basico"].map(pot["nota"]), errors="coerce")
        u["Potencial"] = u["cnpj_basico"].map(pot["potencial"]).fillna("")
        u["Motivo"] = u["cnpj_basico"].map(pot["motivo"]).fillna("")
        u["Alerta"] = u["cnpj_basico"].map(pot["alerta"]).fillna("")
    else:
        u["Bairro"], u["Nota"], u["Potencial"], u["Motivo"], u["Alerta"] = "", float("nan"), "", "", ""
    # Nota e potencial só fazem sentido para quem ainda não é cliente.
    eh_cliente = u["Relacionamento"] == CLIENTE
    u.loc[eh_cliente, ["Potencial", "Motivo"]] = ""
    u.loc[eh_cliente, "Nota"] = float("nan")
    return u[COLUNAS]


def carregar_potencial(caminho: Path = ARQ_POTENCIAL) -> pd.DataFrame:
    if not Path(caminho).exists():
        return pd.DataFrame()
    return pd.read_csv(caminho, dtype={"cnpj_basico": str}, encoding="utf-8-sig").fillna(
        {"bairro": "", "potencial": "", "motivo": "", "alerta": ""})


def opcoes(serie: pd.Series, ordem: list[str] | None = None) -> list[str]:
    presentes = [v for v in serie.dropna().unique() if str(v).strip()]
    if ordem:
        return [o for o in ordem if o in presentes] + sorted(v for v in presentes if v not in ordem)
    return sorted(presentes)


def filtrar(u: pd.DataFrame, *, unidades_sesi=None, unidades_senai=None, categorias=None, segmentos=None,
            regua="FIEA", portes=None, municipios=None, bairros=None, busca="") -> pd.DataFrame:
    m = pd.Series(True, index=u.index)
    if unidades_sesi:
        m &= u["Unidade SESI"].isin(unidades_sesi)
    if unidades_senai:
        m &= u["Unidade SENAI"].isin(unidades_senai)
    if categorias:
        m &= u["Categoria"].isin(categorias)
    if segmentos:
        m &= u["Segmento"].isin(segmentos)
    if portes:
        m &= u["Porte FIEA" if regua == "FIEA" else "Porte Receita"].isin(portes)
    if municipios:
        m &= u["Município"].isin(municipios)
    if bairros:
        m &= u["Bairro"].isin(bairros)
    if busca:
        b = busca.strip().upper()
        m &= u["Razão social"].astype(str).str.upper().str.contains(b, regex=False) | u["cnpj_basico"].str.startswith(
            "".join(ch for ch in b if ch.isdigit()) or "§")
    return u[m]


__all__ = ["montar", "filtrar", "opcoes", "carregar_potencial", "carregar_mei", "CLIENTE", "MERCADO", "ORDEM_FAIXAS",
           "ORDEM_PORTE_FIEA", "ORDEM_PORTE_RECEITA", "A_CONFIRMAR"]
