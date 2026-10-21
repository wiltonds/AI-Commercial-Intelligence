"""Propensão por negócio (lookalike): quanto cada empresa se parece com quem já compra
SSI, STI, EP e EB.

Ideia
-----
O modelo aprende "que tipo de empresa compra cada negócio" a partir de quem já
comprou (Base Histórica de propostas aceitas + Visão 360) e dá uma nota de 0 a 100
(percentil) para todas as empresas de AL. NÃO usa município: a geografia entra na
camada de mercado do mapa, para não reproduzir o viés de "vende onde a unidade está".

Variáveis: CNAE (divisão como categoria; grupo e classe por target encoding fora da
amostra), porte, natureza jurídica, capital social, idade, nº de estabelecimentos,
nº de CNAEs secundários, se é indústria, e se já compra OUTRO negócio (cross-sell).

Validação honesta (backtest): treina só com quem comprou ATÉ a data de corte e mede
se as empresas que compraram pela primeira vez DEPOIS estavam no topo da lista.

Rodar na máquina local (precisa de data/privado/): python jobs/treinar_propensao.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NEGOCIOS = ["SSI", "STI", "EP", "EB"]
# "Negócio" da Base Histórica -> negócio comercial (confirmado com o Will em 21/10/2026:
# Educação Corporativa do SESI são os treinamentos de NR, vendidos junto com SST -> SSI)
MAPA_NEGOCIO = {
    "SSI": ["Segurança Do Trabalho", "Saúde", "Promoção À Saúde", "Promoção À Saúde - Assti",
            "Núcleo De Prevenção E Performance", "Educação Corporativa"],
    "EB": ["Programas E Parcerias Educacionais"],
    "EP": ["Aprendizagem Industrial Básica", "Aperfeiçoamento Profissional", "Habilitação Técnica De Nível Médio",
           "Qualificação Profissional", "Iniciação Profissional", "Demais Ações Educacionais (Ep)"],
    "STI": ["Metrologia", "Consultoria", "Inovação E Empreendedorismo", "Soluções Digitais"],
}
_INV = {v.lower(): k for k, vs in MAPA_NEGOCIO.items() for v in vs}
PORTE_ORD = {"MICRO EMPRESA": 1, "ME": 1, "4. MICRO": 1, "EMPRESA DE PEQUENO PORTE": 2, "EPP": 2, "3. PEQUENO": 2,
             "DEMAIS": 3, "2. MÉDIO": 3, "1. GRANDE": 4}


# ------------------------------------------------------------------ dados
def carregar_vendas(caminho) -> pd.DataFrame:
    """Base Histórica (export de propostas): só aceitas, só os 4 negócios, uma linha por item."""
    d = pd.read_excel(caminho, dtype={"CNPJ": str})
    d["negocio"] = d["Negócio"].astype(str).str.strip().str.lower().map(_INV)
    d = d[d["negocio"].notna() & d["Status"].astype(str).str.strip().eq("Aceita")].copy()
    d["cnpj_basico"] = d["CNPJ"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(14).str[:8]
    d["data"] = pd.to_datetime(d["Emissão"], errors="coerce")
    d["valor"] = pd.to_numeric(d["Valor Total Serviço"], errors="coerce").fillna(0)
    return d[["cnpj_basico", "negocio", "data", "valor", "Serviço"]].rename(columns={"Serviço": "servico"})


def montar_universo(mestre: pd.DataFrame, ampliada: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por CNPJ raiz com as variáveis do modelo (Ampliada tem mais campos; Mestre completa)."""
    a = ampliada.copy()
    a["cnpj_basico"] = a["cnpj_basico"].astype(str).str.zfill(8)
    a = pd.DataFrame({
        "cnpj_basico": a["cnpj_basico"],
        "cnae": a["cnae_principal"].fillna("").astype(str).str.replace(r"\D", "", regex=True).str.zfill(7),
        "porte": a["Porte"].fillna("").astype(str).str.upper().str.strip(),
        "natureza": a["natureza"].fillna("").astype(str),
        "capital": pd.to_numeric(a["capital_social"].astype(str).str.replace(".", "", regex=False)
                                 .str.replace(",", ".", regex=False), errors="coerce"),
        "inicio": pd.to_datetime(a["data_inicio_atividade"], format="%Y%m%d", errors="coerce"),
        "n_estab": pd.to_numeric(a["QTD_ESTABELECIMENTOS"], errors="coerce"),
        "n_cnae_sec": a["cnaes_secundarios"].fillna("").astype(str).str.count(",")
                      + a["cnaes_secundarios"].fillna("").astype(str).str.len().gt(0).astype(int),
        "industria": a["Tipo"].fillna("").astype(str).str.lower().str.startswith("ind"),
    })
    m = mestre.copy()
    m["cnpj_basico"] = m["cnpj"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(14).str[:8]
    m = pd.DataFrame({
        "cnpj_basico": m["cnpj_basico"],
        "cnae": m["SEBRAE_cnae_codigo_recuperado"].fillna("").astype(str).str.replace(r"\D", "", regex=True).str.zfill(7),
        "porte": m["Porte"].fillna("").astype(str).str.upper().str.strip(),
        "industria": True,
    })
    m = m[~m["cnpj_basico"].isin(a["cnpj_basico"])]
    u = pd.concat([a.drop_duplicates("cnpj_basico"), m.drop_duplicates("cnpj_basico")], ignore_index=True)
    u.loc[u["cnae"].eq("0000000"), "cnae"] = ""
    return u.reset_index(drop=True)


# ------------------------------------------------------------------ variáveis
def _target_encode(cat: pd.Series, y: np.ndarray, folds: int = 5, suave: float = 20, semente: int = 0) -> np.ndarray:
    """Taxa de compra suavizada por categoria, calculada fora da amostra (sem vazamento)."""
    prior = y.mean()
    out = np.full(len(cat), prior, dtype=float)
    idx = np.random.default_rng(semente).permutation(len(cat)) % folds
    cat = cat.reset_index(drop=True)
    for f in range(folds):
        tr = idx != f
        g = pd.DataFrame({"c": cat[tr], "y": y[tr]}).groupby("c")["y"].agg(["sum", "count"])
        taxa = (g["sum"] + prior * suave) / (g["count"] + suave)
        out[~tr] = cat[~tr].map(taxa).fillna(prior).to_numpy()
    return out


def _target_encode_aplicar(cat_tr: pd.Series, y: np.ndarray, cat_novo: pd.Series, suave: float = 20) -> np.ndarray:
    prior = y.mean()
    g = pd.DataFrame({"c": cat_tr.reset_index(drop=True), "y": y}).groupby("c")["y"].agg(["sum", "count"])
    taxa = (g["sum"] + prior * suave) / (g["count"] + suave)
    return cat_novo.map(taxa).fillna(prior).to_numpy()


def matriz(u: pd.DataFrame, hoje: pd.Timestamp, outros: pd.DataFrame | None = None) -> pd.DataFrame:
    """Variáveis numéricas que não dependem do rótulo (o target encoding é feito no treino)."""
    x = pd.DataFrame(index=u.index)
    x["divisao"] = pd.to_numeric(u["cnae"].str[:2], errors="coerce").fillna(-1).astype(int)
    x["porte"] = u["porte"].map(PORTE_ORD).fillna(0)
    x["log_capital"] = np.log1p(u.get("capital", pd.Series(np.nan, index=u.index)).clip(lower=0))
    x["idade"] = (hoje - u.get("inicio", pd.Series(pd.NaT, index=u.index))).dt.days / 365.25
    x["n_estab"] = u.get("n_estab", pd.Series(np.nan, index=u.index))
    x["n_cnae_sec"] = u.get("n_cnae_sec", pd.Series(np.nan, index=u.index))
    x["industria"] = u["industria"].astype(float)
    nat = u.get("natureza", pd.Series("", index=u.index)).fillna("")
    top = nat.value_counts().index[:15]
    x["natureza"] = nat.where(nat.isin(top), "outra").astype("category").cat.codes
    if outros is not None:
        for n in NEGOCIOS:
            x[f"compra_{n}"] = u["cnpj_basico"].isin(outros.get(n, set())).astype(float)
    return x


def _modelo():
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(max_iter=250, learning_rate=0.06, max_leaf_nodes=31, min_samples_leaf=40,
                                          l2_regularization=1.0, categorical_features=["divisao", "natureza"],
                                          random_state=0)


def ajustar_e_pontuar(u: pd.DataFrame, x: pd.DataFrame, positivos: set[str], negocio: str) -> np.ndarray:
    """Probabilidade de 'parecer comprador' para todas as empresas do universo."""
    y = u["cnpj_basico"].isin(positivos).to_numpy().astype(int)
    xx = x.drop(columns=[f"compra_{negocio}"], errors="ignore").copy()
    grupo, classe = u["cnae"].str[:3], u["cnae"].str[:5]
    # treino: encoding fora da amostra; pontuação: encoding com todos os dados de treino
    xt = xx.assign(te_grupo=_target_encode(grupo, y), te_classe=_target_encode(classe, y, semente=1))
    m = _modelo().fit(xt, y)
    xp = xx.assign(te_grupo=_target_encode_aplicar(grupo, y, grupo), te_classe=_target_encode_aplicar(classe, y, classe))
    return m.predict_proba(xp)[:, 1]


def avaliar_backtest(u: pd.DataFrame, x_corte: pd.DataFrame, pos_antes: set[str], pos_depois: set[str],
                     negocio: str) -> dict:
    """Treina com quem comprou até o corte; mede onde caíram os compradores NOVOS depois do corte."""
    from sklearn.metrics import roc_auc_score
    p = ajustar_e_pontuar(u, x_corte, pos_antes, negocio)
    cand = ~u["cnpj_basico"].isin(pos_antes)
    novos = u["cnpj_basico"].isin(pos_depois - pos_antes) & cand
    pc, nc = p[cand.to_numpy()], novos[cand].to_numpy()
    if nc.sum() == 0:
        return {"negocio": negocio, "novos": 0}
    ordem = np.argsort(-pc)
    rank = np.empty(len(pc)); rank[ordem] = np.arange(len(pc))
    pct = rank / len(pc)
    r = {"negocio": negocio, "treino_compradores": len(pos_antes & set(u["cnpj_basico"])),
         "candidatos": int(cand.sum()), "novos": int(nc.sum()), "auc": round(roc_auc_score(nc, pc), 3)}
    for k in (0.01, 0.05, 0.10, 0.20):
        acerto = float((pct[nc] < k).mean())
        r[f"top{int(k * 100)}_captura"] = round(acerto, 3)
        r[f"top{int(k * 100)}_lift"] = round(acerto / k, 1)
    return r


def motivo(u: pd.DataFrame, positivos: set[str]) -> pd.Series:
    """Texto curto: quantos compradores existem na mesma classe CNAE (ou grupo)."""
    comp = u[u["cnpj_basico"].isin(positivos)]
    por_classe = comp["cnae"].str[:5].value_counts()
    por_grupo = comp["cnae"].str[:3].value_counts()
    c = u["cnae"].str[:5].map(por_classe).fillna(0).astype(int)
    g = u["cnae"].str[:3].map(por_grupo).fillna(0).astype(int)
    return np.where(c >= 3, c.astype(str) + " clientes da mesma atividade (classe CNAE)",
                    np.where(g >= 3, g.astype(str) + " clientes do mesmo grupo CNAE", "perfil parecido (porte/natureza)"))


# ------------------------------------------------------------------ uso no painel
QUADRANTES = {"agora": "🔥 Abordar já", "planejar": "📅 Prospecção planejada", "pontual": "⚡ Oportunidade pontual",
              "demais": "—"}


def momento_por_negocio(sinais: pd.DataFrame, negocio: str) -> pd.DataFrame:
    """Maior 'momento' e o sinal mais forte de cada empresa entre os sinais que acionam o negócio."""
    if sinais.empty or "cnpj_basico" not in sinais:
        return pd.DataFrame(columns=["cnpj_basico", "momento", "sinal"])
    s = sinais.dropna(subset=["cnpj_basico"])
    s = s[s.get("negocios", pd.Series("", index=s.index)).fillna("").str.contains(negocio)]
    if s.empty:
        return pd.DataFrame(columns=["cnpj_basico", "momento", "sinal"])
    s = s.sort_values("score_momento", ascending=False).drop_duplicates("cnpj_basico")
    return pd.DataFrame({"cnpj_basico": s["cnpj_basico"].astype(str), "momento": s["score_momento"].astype(float),
                         "sinal": s.get("rotulo_tipo", s["tipo_sinal"]).astype(str) + ": "
                                  + s["descricao"].astype(str).str[:120]})


def prioridades(prop: pd.DataFrame, empresas: pd.DataFrame, sinais: pd.DataFrame, negocio: str,
                corte_fit: int = 90) -> pd.DataFrame:
    """Triangulação fit (lookalike) × momento (sinal) para quem AINDA NÃO compra o negócio.

    prioridade = 60% fit + 40% momento (momento 5 ou mais = 100%).
    """
    n = negocio
    p = prop[prop[f"compra_{n}"].eq(0)][["cnpj_basico", f"fit_{n}", f"clientes_classe_{n}", f"clientes_grupo_{n}"]
                                        + [f"compra_{o}" for o in NEGOCIOS if o != n]].copy()
    p.columns = ["cnpj_basico", "fit", "clientes_classe", "clientes_grupo"] + [f"compra_{o}" for o in NEGOCIOS if o != n]
    p = p.merge(momento_por_negocio(sinais, n), on="cnpj_basico", how="left")
    p["momento"] = p["momento"].fillna(0)
    p["prioridade"] = (0.6 * p["fit"] + 40 * (p["momento"] / 5).clip(upper=1)).round(1)
    alto = p["fit"] >= corte_fit
    tem = p["momento"] > 0
    p["quadrante"] = np.select([alto & tem, alto, tem], [QUADRANTES["agora"], QUADRANTES["planejar"],
                                                         QUADRANTES["pontual"]], QUADRANTES["demais"])
    outros = [o for o in NEGOCIOS if o != n]
    compra_outro = p[[f"compra_{o}" for o in outros]].astype(int)
    p["relacao"] = np.where(compra_outro.any(axis=1),
                            "Cliente de " + compra_outro.apply(lambda r: ", ".join(o for o, v in zip(outros, r) if v), axis=1)
                            + " (cross-sell)", "Sem compra registrada")
    p["motivo"] = np.where(p["clientes_classe"] >= 3,
                           "parecida com " + p["clientes_classe"].astype(str) + f" clientes {n} da mesma atividade",
                           np.where(p["clientes_grupo"] >= 3,
                                    "parecida com " + p["clientes_grupo"].astype(str) + f" clientes {n} do mesmo grupo CNAE",
                                    "perfil parecido com clientes (porte, natureza, tempo de empresa)"))
    e = empresas[["cnpj_basico", "razao_social", "municipio", "Porte", "tipo_empresa", "STATUS_RELACIONAMENTO_REAL"]]
    p = p.merge(e, on="cnpj_basico", how="left")
    return p.sort_values("prioridade", ascending=False).reset_index(drop=True)
