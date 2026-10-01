"""
importar_colaboradores.py — Número de colaboradores de cada empresa (real ou estimado).

Lê a exportação de empresas da Solução 360 (aba com CNPJ e Contagem) e gera:
  data/privado/COLABORADORES_EXATO.csv   número real por empresa (fora do Git)
  data/processed/COLABORADORES.csv       faixa (real) ou intervalo (estimado), sem o número exato

O painel mostra o número exato quando o arquivo privado existe (máquina local) e
a faixa no painel online. Com --publicar-exato, o número exato vai também no
arquivo público (decisão sua: é dado interno de clientes).

Uso:
    python jobs/importar_colaboradores.py --arquivo data/privado/colaboradores.xlsx
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.colaboradores import ARQ_EXATO, ARQ_PUBLICO, calcular, ler_exportacao  # noqa: E402
from src.tools.company_data import BASE_PATH  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
ARQ_AMPLIADA = RAIZ / "data" / "processed" / "BASE_AMPLIADA_AL.csv"


def carregar_universo() -> pd.DataFrame:
    b = pd.read_csv(BASE_PATH, dtype=str, low_memory=False, encoding="utf-8-sig")
    b["raiz"] = b["CNPJ_BASICO"].astype(str).str.zfill(8)
    g = b.groupby("raiz")
    ind = pd.DataFrame({
        "cnpj_basico": g.size().index,
        "porte": g["Porte"].first().values,
        "div": g["SEBRAE_cnae_divisao"].first().fillna("0").astype(str).str.split(".").str[0].values,
        "classe": g["SEBRAE_cnae_codigo_recuperado"].first().fillna("").str.replace(r"\D", "", regex=True).str[:4].values,
        "unidades": g.size().values,
        "municipio": g["Municipio"].first().fillna("").values,
    })
    partes = [ind]
    if ARQ_AMPLIADA.exists():
        a = pd.read_csv(ARQ_AMPLIADA, dtype=str, encoding="utf-8-sig").fillna("")
        cnae = a["cnae_principal"].str.replace(r"\D", "", regex=True).str.zfill(7)
        partes.append(pd.DataFrame({"cnpj_basico": a["cnpj_basico"], "porte": a["Porte"], "div": cnae.str[:2],
                                    "classe": cnae.str[:4], "unidades": a.get("QTD_ESTABELECIMENTOS", "1"),
                                    "municipio": a["Municipio"]}))
    return pd.concat(partes, ignore_index=True).drop_duplicates("cnpj_basico")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo", default="data/privado/colaboradores.xlsx")
    ap.add_argument("--publicar-exato", action="store_true", help="inclui o número exato no arquivo público")
    a = ap.parse_args()
    real = ler_exportacao(Path(a.arquivo))
    univ = carregar_universo()
    out = calcular(univ, real)
    reais = out[out["origem_colaboradores"] == "Solução 360"]
    ARQ_EXATO.parent.mkdir(parents=True, exist_ok=True)
    reais[["cnpj_basico", "colaboradores"]].to_csv(ARQ_EXATO, index=False, encoding="utf-8-sig")
    cols = ["cnpj_basico", "origem_colaboradores", "faixa_colaboradores", "colab_min", "colab_max"]
    if a.publicar_exato:
        cols.insert(1, "colaboradores")
    out[cols].to_csv(ARQ_PUBLICO, index=False, encoding="utf-8-sig")
    print(f"Exportação lida: {len(real):,} CNPJs com colaboradores")
    print(f"Universo: {len(out):,} empresas | número real: {len(reais):,} ({len(reais) / len(out):.0%}) | "
          f"estimado: {int((out['origem_colaboradores'] == 'Estimado').sum()):,}")
    print("Número real por porte:", univ.assign(r=out["origem_colaboradores"].eq("Solução 360").values)
          .groupby("porte")["r"].mean().map(lambda x: f"{x:.0%}").to_dict())
    print(f"Salvo: {ARQ_PUBLICO.relative_to(RAIZ)} (faixa) e {ARQ_EXATO.relative_to(RAIZ)} (exato, local)")
    from src.tools.log_atualizacoes import registrar
    registrar("colaboradores", f"{len(reais):,} reais, {len(out) - len(reais):,} estimados")


if __name__ == "__main__":
    main()
