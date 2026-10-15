"""Potencial de conversão das empresas SEM relacionamento ("parecidas com nossos clientes").

Como funciona
-------------
1. Universo: indústrias (Base Mestre) + não indústrias (Base Ampliada), uma linha por CNPJ raiz.
2. Alvo: já comprou de SESI ou SENAI (proposta aceita) = 1; nunca comprou = 0.
3. Um modelo (gradient boosting) aprende o perfil de quem compra usando SÓ dado público
   de cadastro: categoria, CNAE, porte Receita, município, capital social, natureza
   jurídica, nº de estabelecimentos e idade da empresa.
4. Cada empresa sem relacionamento recebe a probabilidade calculada "fora da amostra"
   (validação cruzada), para o modelo não dar nota a quem ele mesmo decorou.
5. Regras de negócio por cima da nota: falência / recuperação judicial e sede fora de AL
   viram alerta (não somem: o comercial decide).

O resultado é público (só dado de empresa, nada de pessoa): nota, faixa, motivo e alerta.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

FAIXAS = [(0.30, "Muito alto"), (0.15, "Alto"), (0.05, "Médio"), (0.0, "Baixo")]
ORDEM_FAIXAS = ["Muito alto", "Alto", "Médio", "Baixo"]

SECOES_CNAE = [
    (1, 3, "Agropecuária"), (5, 9, "Indústria extrativa"), (10, 33, "Indústria de transformação"),
    (35, 35, "Eletricidade e gás"), (36, 39, "Água, esgoto e resíduos"), (41, 43, "Construção"),
    (45, 47, "Comércio"), (49, 53, "Transporte e armazenagem"), (55, 56, "Alojamento e alimentação"),
    (58, 63, "Informação e comunicação"), (64, 66, "Financeiro e seguros"), (68, 68, "Imobiliário"),
    (69, 75, "Atividades profissionais e técnicas"), (77, 82, "Serviços administrativos"),
    (84, 84, "Administração pública"), (85, 85, "Educação"), (86, 88, "Saúde e serviços sociais"),
    (90, 93, "Artes, cultura e esporte"), (94, 96, "Outros serviços"), (97, 99, "Outros"),
]

RE_ALERTA_JURIDICO = re.compile(r"FALID|FALENCIA|FALÊNCIA|RECUPERA[CÇ][AÃ]O JUDICIAL|EM LIQUIDA[CÇ][AÃ]O", re.I)


def segmento_cnae(divisao) -> str:
    try:
        d = int(float(str(divisao)[:2]))
    except (TypeError, ValueError):
        return "Não classificado"
    for lo, hi, nome in SECOES_CNAE:
        if lo <= d <= hi:
            return nome
    return "Não classificado"


def faixa(p: float) -> str:
    if pd.isna(p):
        return ""
    for corte, nome in FAIXAS:
        if p >= corte:
            return nome
    return "Baixo"


def numero_br(texto) -> float:
    """'1.234.567,89' ou '1234567,89' -> 1234567.89."""
    s = str(texto or "").strip()
    if not s:
        return np.nan
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return np.nan


def grupo_natureza(natureza: str) -> str:
    n = str(natureza or "")
    for chave, nome in [("Anônima", "S.A."), ("Limitada", "Ltda"), ("Individual", "Individual"),
                        ("Unipessoal", "Individual"), ("Cooperativa", "Cooperativa"),
                        ("Associação", "Associação/Fundação"), ("Fundação", "Associação/Fundação"),
                        ("Pública", "Pública/Mista"), ("Economia Mista", "Pública/Mista"),
                        ("Município", "Pública/Mista"), ("Estado", "Pública/Mista")]:
        if chave in n:
            return nome
    return "Outra" if n else ""


def alertas(razao_social: str, sede_em_al: bool) -> str:
    out = []
    if RE_ALERTA_JURIDICO.search(str(razao_social or "")):
        out.append("Falência/recuperação judicial")
    if not sede_em_al:
        out.append("Sede fora de AL (conta nacional)")
    return " · ".join(out)


def _features(u: pd.DataFrame) -> pd.DataFrame:
    hoje = pd.Timestamp.today()
    abertura = pd.to_datetime(u.get("data_abertura", pd.Series("", index=u.index)), format="%Y%m%d", errors="coerce")
    return pd.DataFrame({
        "industria": (u["Categoria"] == "Indústria").astype(int).values,
        "divisao": pd.to_numeric(u["divisao"], errors="coerce").values,
        "cnae4": pd.to_numeric(u["cnae"].astype(str).str[:4], errors="coerce").values,
        "porte": u["Porte Receita"].map({"MICRO EMPRESA": 0, "PEQUENO PORTE": 1, "DEMAIS": 2}).values,
        "log_capital": np.log1p(u["capital"]).values,
        "n_estab": pd.to_numeric(u["n_estab"], errors="coerce").values,
        "maceio": u["Município"].astype(str).str.upper().str.startswith("MACEI").astype(int).values,
        "idade": ((hoje - abertura).dt.days / 365.25).values,
        "natureza": u["natureza_grupo"].astype("category").cat.codes.values,
        "municipio": u["Município"].astype("category").cat.codes.values,
    })


def calcular_probabilidades(u: pd.DataFrame, folds: int = 5, seed: int = 1) -> tuple[np.ndarray, float]:
    """Probabilidade fora da amostra para todas as linhas + AUC da validação."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold

    X = _features(u)
    y = u["cliente"].astype(int).values
    cat = [X.columns.get_loc("natureza"), X.columns.get_loc("municipio")]
    p = np.zeros(len(u))
    for tr, te in StratifiedKFold(folds, shuffle=True, random_state=seed).split(X, y):
        m = HistGradientBoostingClassifier(max_depth=4, max_iter=300, learning_rate=0.05,
                                           categorical_features=cat, random_state=seed)
        p[te] = m.fit(X.iloc[tr], y[tr]).predict_proba(X.iloc[te])[:, 1]
    return p, float(roc_auc_score(y, p))


def motivos(u: pd.DataFrame) -> pd.Series:
    """Texto curto do porquê: taxa de adesão do perfil + sinais da empresa."""
    perfil = ["Categoria", "Segmento", "Porte Receita"]
    taxa = u.groupby(perfil)["cliente"].transform("mean")
    base = u.groupby(perfil)["cliente"].transform("size")
    out = []
    for t, n, seg, porte, est, cap in zip(taxa, base, u["Segmento"], u["Porte Receita"], u["n_estab"], u["capital"]):
        partes = []
        if n >= 20 and seg != "Não classificado":
            partes.append(f"{t * 100:.0f}% das {n:,} empresas de {seg} ({str(porte).title()}) já compram"
                          .replace(",", "."))
        if pd.notna(est) and est >= 2:
            partes.append(f"{int(est)} estabelecimentos")
        if pd.notna(cap) and cap >= 1_000_000:
            partes.append(f"capital R$ {cap / 1e6:,.1f} mi".replace(",", "X").replace(".", ",").replace("X", "."))
        out.append(" · ".join(partes) or "perfil raro na base: nota pelo conjunto dos dados")
    return pd.Series(out, index=u.index)


def pontuar(u: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """u: uma linha por empresa com Categoria, Segmento, divisao, cnae, Porte Receita, Município,
    capital, n_estab, natureza_grupo, data_abertura, razao_social, sede_em_al, cliente.
    Devolve cnpj_basico, nota (0–10), potencial, motivo, alerta (nota só para quem não é cliente)."""
    p, auc = calcular_probabilidades(u)
    sem = ~u["cliente"].astype(bool).values
    out = pd.DataFrame({"cnpj_basico": u["cnpj_basico"].values})
    out["nota"] = np.where(sem, np.round(p * 10, 1), np.nan)
    out["potencial"] = [faixa(x) if s else "" for x, s in zip(p, sem)]
    out["motivo"] = np.where(sem, motivos(u).values, "")
    out["alerta"] = [alertas(r, s) for r, s in zip(u["razao_social"], u["sede_em_al"])]
    return out, auc
