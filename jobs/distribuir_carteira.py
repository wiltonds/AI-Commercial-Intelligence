"""
distribuir_carteira.py — Unidade responsável (SESI e SENAI) de cada empresa, pela Minuta de Carteirização.

Entradas:
  data/contatos/ENDERECOS_AL.csv          endereço da sede (jobs/extrair_enderecos.py)
  --historico <arquivo.xlsx> [...]        exportação(ões) de propostas com as colunas
                                          CNPJ, Entidade, Unidade, Status (usa só "Aceita")
  config/referencia/carteira_minuta.csv   tabela da minuta (bairro de Maceió / município -> unidade)

Saída:
  data/privado/CARTEIRA_UNIDADES_DETALHE.csv   tudo, inclusive em quais unidades a empresa comprou
                                               (vem das propostas: fica FORA do Git)
  data/processed/CARTEIRA_UNIDADES.csv         só o que o painel usa: cnpj_basico, unidade_sesi,
                                               unidade_senai, unidades (sem motivo: repositório público)

Sem --historico, todo mundo é tratado como empresa nova (só endereço da sede): serve para
prospecção, mas os clientes atuais podem ficar na unidade errada até a exportação ser passada.

Uso:
    python jobs/distribuir_carteira.py --historico data/privado/propostas_unidades.xlsx
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.carteira import distribuir  # noqa: E402
from src.tools.company_data import BASE_PATH  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
ARQ_END = RAIZ / "data" / "contatos" / "ENDERECOS_AL.csv"
ARQ_AMPLIADA = RAIZ / "data" / "processed" / "BASE_AMPLIADA_AL.csv"
ARQ_SAIDA = RAIZ / "data" / "processed" / "CARTEIRA_UNIDADES.csv"
ARQ_DETALHE = RAIZ / "data" / "privado" / "CARTEIRA_UNIDADES_DETALHE.csv"


def ler_historico(arquivos: list[str]) -> pd.DataFrame:
    partes = []
    for a in arquivos:
        d = pd.read_excel(a, dtype=str) if a.lower().endswith((".xlsx", ".xls")) else pd.read_csv(a, dtype=str, encoding="utf-8-sig")
        faltam = {"CNPJ", "Entidade", "Unidade"} - set(d.columns)
        if faltam:
            raise SystemExit(f"{a}: faltam as colunas {sorted(faltam)}")
        if "Status" in d.columns:
            d = d[d["Status"].fillna("").str.strip().str.lower() == "aceita"]
        d["cnpj_basico"] = d["CNPJ"].str.replace(r"\D", "", regex=True).str.zfill(14).str[:8]
        partes.append(d[["cnpj_basico", "Entidade", "Unidade"]])
    return pd.concat(partes, ignore_index=True) if partes else None


def universo() -> set[str]:
    r = set(pd.read_csv(BASE_PATH, dtype=str, usecols=["CNPJ_BASICO"], encoding="utf-8-sig")["CNPJ_BASICO"].str.zfill(8))
    if ARQ_AMPLIADA.exists():
        r |= set(pd.read_csv(ARQ_AMPLIADA, dtype=str, usecols=["cnpj_basico"], encoding="utf-8-sig")["cnpj_basico"].str.zfill(8))
    return r


def _origem(motivo: str) -> str:
    m = str(motivo)
    if m.startswith("histórico"):
        return "cliente"
    if m.startswith("empresa nova"):
        return "empresa nova"
    if m.startswith("sede fora"):
        return "sede fora de AL"
    return "conferir"


COLS_PUBLICO = ["cnpj_basico", "unidade_sesi", "unidade_senai", "unidades"]


def publico(out: pd.DataFrame) -> pd.DataFrame:
    """Versão do painel (repositório público): só a unidade. Motivos e histórico ficam no DETALHE."""
    return out[COLS_PUBLICO].copy()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--historico", nargs="*", default=[], help="exportações de propostas com a coluna Unidade")
    a = ap.parse_args()
    if not ARQ_END.exists():
        raise SystemExit(f"Falta {ARQ_END.relative_to(RAIZ)} — rode antes jobs/extrair_enderecos.py")
    end = pd.read_csv(ARQ_END, dtype=str, encoding="utf-8-sig").fillna("")
    hist = ler_historico(a.historico) if a.historico else None
    out = distribuir(end, hist, universo())
    ARQ_DETALHE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(ARQ_DETALHE, index=False, encoding="utf-8-sig")
    publico(out).to_csv(ARQ_SAIDA, index=False, encoding="utf-8-sig")
    print(f"Salvo: {ARQ_DETALHE.relative_to(RAIZ)}  (completo, fora do Git)")
    print(f"Salvo: {ARQ_SAIDA.relative_to(RAIZ)}  ({len(out):,} empresas, versão do painel)")
    print(pd.crosstab(out["unidade_sesi"].replace("", "(sem)"), out["unidade_senai"].replace("", "(sem)")).to_string())
    print("\nOrigem (só no DETALHE):")
    print(pd.DataFrame({"SESI": out["motivo_sesi"].map(_origem).value_counts(),
                        "SENAI": out["motivo_senai"].map(_origem).value_counts()}).fillna(0).astype(int).to_string())
    print(f"bairro pelo CEP: {int(out['endereco_sede'].str.startswith('bairro pelo CEP').sum()):,} empresas")
    if hist is None:
        print("\nATENÇÃO: sem --historico. Clientes atuais foram distribuídos só pelo endereço da sede.")
    try:
        from src.tools.log_atualizacoes import registrar
        registrar("carteira_unidades", f"{len(out):,} empresas; histórico: {'sim' if hist is not None else 'não'}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
