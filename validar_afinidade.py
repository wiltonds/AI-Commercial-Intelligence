"""
validar_afinidade.py — A MATRIZ de afinidade tem sinal? Mede contra dado real.

Antes de industrializar a recomendação (qualificar_base.py) e subir pro CRM,
esta é a pergunta do modo algorisolófico: a afinidade que estamos usando
PREVÊ o comportamento real, ou é palpite?

Usa o gabarito que já existe: os clientes atuais (TEM_SESI / TEM_SENAI).
Para cada setor (e setor × porte), compara a taxa de clientes contra a média
geral da base = LIFT.
  lift > 1  -> setor vira cliente MAIS que a média  (afinidade tem sinal)
  lift ~ 1  -> setor igual à média                  (sem sinal — MATRIZ é ruído ali)
  lift < 1  -> setor vira cliente MENOS que a média

Bônus: a própria coluna taxa_cliente É a primeira MATRIZ empírica
(P(cliente | setor, porte) observado) — pronta para substituir os pesos
hardcoded, sem esperar o consumo 25/26.

Roda LOCAL (base tem CNPJ).
    python validar_afinidade.py
    python validar_afinidade.py --entidade SESI --min-amostra 30
"""

import argparse
import pandas as pd
from pathlib import Path

from src.tools.company_data import CompanyDataTool
from src.tools.cnpj_raiz import consolidar_por_cnpj_raiz

SAIDA = Path(__file__).resolve().parent / "data" / "processed"


def _coluna_cliente(entidade: str) -> str:
    return {"SESI": "TEM_SESI", "SENAI": "TEM_SENAI"}[entidade.upper()]


def validar(entidade: str = "SENAI", min_amostra: int = 20) -> dict:
    col = _coluna_cliente(entidade)
    base = consolidar_por_cnpj_raiz(CompanyDataTool()._load())

    base[col] = base[col].fillna(False).astype(bool)
    base_rate = base[col].mean()  # média geral de clientes na base

    # ---- penetração por SETOR ----
    por_setor = (
        base.groupby("SETOR")
        .agg(n=("cnpj", "size"), clientes=(col, "sum"))
        .reset_index()
    )
    por_setor["taxa_cliente"] = por_setor["clientes"] / por_setor["n"]
    por_setor["lift"] = por_setor["taxa_cliente"] / base_rate if base_rate else 0
    por_setor["amostra_confiavel"] = por_setor["n"] >= min_amostra
    por_setor = por_setor.sort_values("lift", ascending=False)

    # ---- penetração por SETOR × PORTE ----
    por_setor_porte = (
        base.groupby(["SETOR", "Porte"])
        .agg(n=("cnpj", "size"), clientes=(col, "sum"))
        .reset_index()
    )
    por_setor_porte["taxa_cliente"] = (
        por_setor_porte["clientes"] / por_setor_porte["n"]
    )
    por_setor_porte["lift"] = (
        por_setor_porte["taxa_cliente"] / base_rate if base_rate else 0
    )
    por_setor_porte["amostra_confiavel"] = por_setor_porte["n"] >= min_amostra

    return {
        "entidade": entidade,
        "base_rate": base_rate,
        "n_total": len(base),
        "n_clientes": int(base[col].sum()),
        "por_setor": por_setor,
        "por_setor_porte": por_setor_porte,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entidade", default="SENAI", choices=["SESI", "SENAI"])
    ap.add_argument("--min-amostra", type=int, default=20)
    args = ap.parse_args()

    r = validar(args.entidade, args.min_amostra)

    print(f"\n=== VALIDAÇÃO DE AFINIDADE — {r['entidade']} ===")
    print(f"Base: {r['n_total']:,} empresas | clientes: {r['n_clientes']:,} "
          f"| taxa média (base rate): {r['base_rate']:.1%}")

    if r["base_rate"] < 0.01:
        print("\n[ALERTA] Taxa de clientes quase zero na base inteira.")
        print("Isso NÃO valida afinidade — reforça a suspeita de pull do CRM incompleto.")
        print("Resolver a cobertura ANTES de confiar em qualquer lift.\n")

    setor = r["por_setor"]
    print("\n--- LIFT por setor (só amostra confiável) ---")
    conf = setor[setor["amostra_confiavel"]]
    print(conf[["SETOR", "n", "clientes", "taxa_cliente", "lift"]]
          .to_string(index=False,
                     formatters={"taxa_cliente": "{:.1%}".format,
                                 "lift": "{:.2f}x".format}))

    fracos = setor[(setor["amostra_confiavel"]) & (setor["lift"].between(0.8, 1.2))]
    if len(fracos):
        print(f"\n[SEM SINAL] {len(fracos)} setores com lift ~1 "
              f"(afinidade não distingue da média): "
              f"{', '.join(fracos['SETOR'].head(8))}")

    SAIDA.mkdir(parents=True, exist_ok=True)
    arq = SAIDA / f"AFINIDADE_EMPIRICA_{r['entidade']}.csv"
    r["por_setor_porte"].to_csv(arq, index=False, encoding="utf-8-sig")
    print(f"\nMATRIZ empírica (setor × porte) salva: {arq}")
    print("-> Esta taxa_cliente observada pode substituir os pesos hardcoded da MATRIZ.")


if __name__ == "__main__":
    main()
