"""
atualizar_relacionamento.py — Atualiza quem é cliente a partir da exportação de propostas.

Uso:
    python jobs/atualizar_relacionamento.py --arquivo "C:/.../Relacionamento_SESI_e_SENAI.xlsx"

O que faz:
  1. Base Mestre: recalcula TEM_SESI / TEM_SENAI / STATUS_RELACIONAMENTO por
     CNPJ raiz e acrescenta SITUACAO_CLIENTE (Ativo / Inativo / Sem compra),
     ULTIMA_COMPRA (SESI, SENAI, geral), PRIMEIRA_COMPRA e CNPJ_ATENDIDO
     (esta unidade comprou?). Todas as páginas do painel passam a usar isso.
  2. Base ampliada (não indústrias): mesmas marcações.
  3. Porte FIEA: o mais recente informado nas propostas, para a faixa de
     colaboradores (data/processed/PORTE_FIEA.csv).
  4. Agregados para o painel (sem dado de empresa):
       data/processed/PRODUTOS_RANKING.csv      produtos mais vendidos
       data/processed/ATENDIMENTO_POR_ANO.csv   empresas atendidas por ano
  5. Confidenciais (fora do Git, pasta data/privado/):
       RELACIONAMENTO_POR_EMPRESA.csv  valores, nº de propostas e linhas compradas
       CLIENTES_FORA_DA_BASE.csv       quem comprou e não está em nenhuma base
"""

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.company_data import BASE_PATH  # noqa: E402
from src.tools.receita_cnpj import faixa_colaboradores  # noqa: E402
from src.tools.relacionamento import (  # noqa: E402
    aplicar_na_base,
    carregar_config,
    carregar_propostas,
    porte_fiea_por_raiz,
    resumo_por_cnpj,
    resumo_por_raiz,
    atendimento_por_ano,
    ranking_produtos,
    vendas,
)

RAIZ = Path(__file__).resolve().parent.parent
PROC = RAIZ / "data" / "processed"
PRIVADO = RAIZ / "data" / "privado"
ARQ_AMPLIADA = PROC / "BASE_AMPLIADA_AL.csv"


def _clientes(df: pd.DataFrame) -> set[str]:
    m = df["TEM_SESI"].astype(str).eq("True") | df["TEM_SENAI"].astype(str).eq("True")
    return set(df.loc[m, "CNPJ_BASICO"].astype(str).str.zfill(8))


def atualizar_ampliada(por_raiz: pd.DataFrame, porte: pd.DataFrame) -> int:
    if not ARQ_AMPLIADA.exists():
        return 0
    a = pd.read_csv(ARQ_AMPLIADA, dtype=str, encoding="utf-8-sig").fillna("")
    r = por_raiz.set_index("cnpj_basico")
    a["POSSUI_SESI"] = a["cnpj_basico"].map(r["TEM_SESI"]).fillna(False).astype(bool).astype(str)
    a["POSSUI_SENAI"] = a["cnpj_basico"].map(r["TEM_SENAI"]).fillna(False).astype(bool).astype(str)
    for col in ("SITUACAO_CLIENTE", "ULTIMA_COMPRA"):
        a[col] = a["cnpj_basico"].map(r[col]).astype("object").where(lambda s: s.notna(), "")
    a["SITUACAO_CLIENTE"] = a["SITUACAO_CLIENTE"].replace("", "Sem compra")
    novo = a["cnpj_basico"].map(porte.set_index("cnpj_basico")["porte_fiea"]).fillna("")
    a["porte_fiea"] = novo.where(novo != "", a.get("porte_fiea", ""))
    a["Colaboradores (faixa)"] = [faixa_colaboradores(t, p) for t, p in zip(a["Tipo"], a["porte_fiea"])]
    a["Origem colaboradores"] = a["Colaboradores (faixa)"].map(
        lambda f: "Porte FIEA (propostas/relacionamento)" if f else "Sem informação")
    a.to_csv(ARQ_AMPLIADA, index=False, encoding="utf-8-sig")
    return int((a["POSSUI_SESI"].eq("True") | a["POSSUI_SENAI"].eq("True")).sum())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--arquivo", required=True, help="exportação de propostas (.xlsx)")
    parser.add_argument("--hoje", help="data de referência AAAA-MM-DD (padrão: hoje)")
    args = parser.parse_args()
    hoje = pd.Timestamp(args.hoje or date.today())
    cfg = carregar_config()

    prop = carregar_propostas(Path(args.arquivo))
    v = vendas(prop, cfg)
    por_raiz = resumo_por_raiz(v, hoje, int(cfg["meses_ativo"]))
    por_cnpj = resumo_por_cnpj(v, hoje, int(cfg["meses_ativo"]))
    porte = porte_fiea_por_raiz(prop)
    print(f"Propostas: {len(prop):,} | vendas ({', '.join(cfg['status_venda'])}): {len(v):,} | "
          f"empresas que compraram: {len(por_raiz):,} | CNPJs: {len(por_cnpj):,}")

    base = pd.read_csv(BASE_PATH, dtype=str, low_memory=False, encoding="utf-8-sig")
    antes = _clientes(base)
    nova = aplicar_na_base(base, por_raiz, por_cnpj)
    depois = _clientes(nova)
    nova.to_csv(BASE_PATH, index=False, encoding="utf-8-sig")
    raizes_base = set(nova["CNPJ_BASICO"].astype(str).str.zfill(8))
    emp = nova.drop_duplicates("CNPJ_BASICO")
    print(f"\nBase Mestre ({len(raizes_base):,} empresas)")
    print(f"  clientes: {len(antes):,} -> {len(depois):,}  (novos: {len(depois - antes):,} | "
          f"deixaram de constar: {len(antes - depois):,})")
    print("  situação:", emp["SITUACAO_CLIENTE"].value_counts().to_dict())
    print(f"  CNPJs (unidades) que compraram: {int((nova['CNPJ_ATENDIDO'] == 'Sim').sum()):,}")

    n_amp = atualizar_ampliada(por_raiz, porte)
    print(f"\nBase ampliada: {n_amp:,} não indústrias clientes")

    PROC.mkdir(parents=True, exist_ok=True)
    porte.to_csv(PROC / "PORTE_FIEA.csv", index=False, encoding="utf-8-sig")
    ranking_produtos(v, raizes_base, hoje, int(cfg["meses_ativo"])).to_csv(
        PROC / "PRODUTOS_RANKING.csv", index=False, encoding="utf-8-sig")
    atendimento_por_ano(v, raizes_base).to_csv(PROC / "ATENDIMENTO_POR_ANO.csv", index=False, encoding="utf-8-sig")

    PRIVADO.mkdir(parents=True, exist_ok=True)
    por_raiz.to_csv(PRIVADO / "RELACIONAMENTO_POR_EMPRESA.csv", index=False, encoding="utf-8-sig")
    raizes_amp = (set(pd.read_csv(ARQ_AMPLIADA, dtype=str, usecols=["cnpj_basico"])["cnpj_basico"])
                  if ARQ_AMPLIADA.exists() else set())
    fora = por_raiz[~por_raiz["cnpj_basico"].isin(raizes_base | raizes_amp)]
    info = (v.sort_values("data").drop_duplicates("cnpj_basico", keep="last")
            .set_index("cnpj_basico")[["cnpj", "Razão Social", "Categoria", "Porte Receita"]])
    fora.join(info, on="cnpj_basico").to_csv(PRIVADO / "CLIENTES_FORA_DA_BASE.csv", index=False, encoding="utf-8-sig")
    print(f"Clientes fora de todas as bases: {len(fora):,} (data/privado/CLIENTES_FORA_DA_BASE.csv)")
    print(f"Porte FIEA conhecido: {len(porte):,} empresas")
    from src.tools.log_atualizacoes import registrar
    registrar("propostas", f"{len(prop):,} propostas; clientes na Base Mestre: {len(depois):,}")


if __name__ == "__main__":
    main()
