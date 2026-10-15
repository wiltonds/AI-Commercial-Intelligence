"""
extrair_enderecos.py — Endereço (bairro, CEP) de todos os estabelecimentos ativos de AL
e capital social / natureza jurídica de cada empresa, direto dos dados abertos da Receita.

Por que existe: a Minuta de Carteirização define a carteira de empresa nova pelo
endereço da SEDE (em Maceió, pelo bairro). O carregar_base_ampliada.py lê esses
mesmos arquivos, mas não guarda bairro/CEP — e a Base Mestre (indústrias) não tem
endereço. Este job grava o endereço de todos os estabelecimentos, matriz e filiais.

Saída (fora do Git — tem endereço de empresário individual/MEI):
  data/contatos/ENDERECOS_AL.csv
      cnpj, cnpj_basico, matriz (S/N), logradouro, numero, complemento, bairro, cep,
      municipio, capital_social, natureza_juridica

Uso (mesma pasta de zips do carregar_base_ampliada.py):
    python jobs/extrair_enderecos.py --pasta "C:/caminho/dos/zips"
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.receita_cnpj import ler_codigos, ler_empresas, ler_estabelecimentos  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
ARQ_SAIDA = RAIZ / "data" / "contatos" / "ENDERECOS_AL.csv"


def montar(pasta: Path, uf: str = "AL") -> pd.DataFrame:
    zips_estab = sorted(pasta.glob("Estabelecimentos*.zip"))
    zips_emp = sorted(pasta.glob("Empresas*.zip"))
    if not zips_estab:
        raise FileNotFoundError(f"Sem Estabelecimentos*.zip em {pasta}")
    partes = []
    for z in zips_estab:
        p = ler_estabelecimentos(z, uf)
        print(f"  {z.name}: {len(p):,} estabelecimentos ativos em {uf}")
        partes.append(p)
    est = pd.concat(partes, ignore_index=True)
    est["cnpj"] = est["cnpj_basico"] + est["cnpj_ordem"] + est["cnpj_dv"]
    est["matriz"] = (est["matriz_filial"] == "1").map({True: "S", False: "N"})
    est["logradouro"] = (est["tipo_logradouro"].str.strip() + " " + est["logradouro"].str.strip()).str.strip().str.title()
    for c in ("numero", "complemento"):
        est[c] = est[c].str.strip()
    est["bairro"] = est["bairro"].str.strip().str.title()
    est["cep"] = est["cep"].str.strip()
    est["municipio"] = est["municipio_codigo"].map(ler_codigos(pasta / "Municipios.zip")).fillna("").str.title()

    out = est[["cnpj", "cnpj_basico", "matriz", "logradouro", "numero", "complemento", "bairro", "cep", "municipio"]]
    if zips_emp:
        raizes = set(out["cnpj_basico"])
        emp = pd.concat([ler_empresas(z, raizes) for z in zips_emp], ignore_index=True).drop_duplicates("cnpj_basico")
        nat = ler_codigos(pasta / "Naturezas.zip")
        emp["natureza_juridica"] = emp["natureza_juridica"].map(nat).fillna(emp["natureza_juridica"])
        out = out.merge(emp[["cnpj_basico", "capital_social", "natureza_juridica"]], on="cnpj_basico", how="left")
    return out.sort_values(["cnpj_basico", "matriz"], ascending=[True, False]).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pasta", required=True, help="pasta com os .zip da Receita (Estabelecimentos, Empresas, Municipios, Naturezas)")
    ap.add_argument("--uf", default="AL")
    a = ap.parse_args()
    out = montar(Path(a.pasta), a.uf)
    ARQ_SAIDA.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(ARQ_SAIDA, index=False, encoding="utf-8-sig")
    print(f"\nSalvo: {ARQ_SAIDA.relative_to(RAIZ)}  ({len(out):,} estabelecimentos, "
          f"{out['cnpj_basico'].nunique():,} empresas, {int((out['bairro'] != '').sum()):,} com bairro)")
    try:
        from src.tools.log_atualizacoes import registrar
        registrar("enderecos", f"{len(out):,} estabelecimentos de {a.uf}; pasta {Path(a.pasta).name}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
