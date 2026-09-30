"""
mapear_hubs.py — Escritórios de contabilidade e grupos que conectam muitas empresas.

Usa o que já foi coletado (sem nova consulta):
  contatos do robô + da Receita  -> canais (mesmo e-mail/domínio ou telefone em várias empresas)
  quadro societário (robô)       -> grupos (mesmo sócio em várias empresas)
  Base Mestre + base ampliada    -> quem é cliente, segmento

Gera, fora do Git (tem contatos e nomes): data/privado/HUBS_CANAIS.xlsx
  aba Canais    escritórios/contatos compartilhados, do que abre mais empresas sem compra
  aba Grupos    sócios presentes em várias empresas
  aba Empresas  cada hub com as empresas por trás dele

Uso:  python jobs/mapear_hubs.py [--minimo-canal 5] [--minimo-grupo 3]
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.company_data import BASE_PATH  # noqa: E402
from src.tools.contatos import carregar_contatos  # noqa: E402
from src.tools.hubs import chave_email, mapear_canais, mapear_grupos  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
ARQ_AMPLIADA = RAIZ / "data" / "processed" / "BASE_AMPLIADA_AL.csv"
SAIDA = RAIZ / "data" / "privado" / "HUBS_CANAIS.xlsx"


def carregar_universo() -> pd.DataFrame:
    b = pd.read_csv(BASE_PATH, dtype=str, low_memory=False, encoding="utf-8-sig")
    ind = pd.DataFrame({"cnpj_basico": b["CNPJ_BASICO"].str.zfill(8), "razao_social": b["razao_social"],
                        "segmento": b.get("SEBRAE_setor", pd.Series("", index=b.index)).fillna("Indústria"),
                        "situacao": b.get("SITUACAO_CLIENTE", pd.Series("Sem compra", index=b.index)).fillna("Sem compra"),
                        "tipo_empresa": "Indústria"})
    partes = [ind]
    if ARQ_AMPLIADA.exists():
        a = pd.read_csv(ARQ_AMPLIADA, dtype=str, encoding="utf-8-sig").fillna("")
        partes.append(pd.DataFrame({"cnpj_basico": a["cnpj_basico"], "razao_social": a["razao_social"],
                                    "segmento": a.get("CNAE PRIMARIO", ""), "tipo_empresa": a["Tipo"],
                                    "situacao": a.get("SITUACAO_CLIENTE", pd.Series("Sem compra", index=a.index)).replace("", "Sem compra")}))
    return pd.concat(partes, ignore_index=True).drop_duplicates("cnpj_basico")


def membros(contatos: pd.DataFrame, universo: pd.DataFrame, canais: pd.DataFrame, grupos: pd.DataFrame) -> pd.DataFrame:
    u = universo.set_index("cnpj_basico")
    linhas = []
    hubs_c = set(canais["hub"]) if not canais.empty else set()
    for x in contatos.to_dict("records"):
        for chave in {chave_email(x.get("email", "")), str(x.get("telefone_1", "")), str(x.get("telefone_2", ""))}:
            if chave in hubs_c:
                linhas.append({"hub": chave, "tipo": "canal", "cnpj_basico": x["cnpj_basico"]})
    if not grupos.empty:
        for x in contatos.to_dict("records"):
            for s in str(x.get("socios", "")).split(";"):
                nome = s.split("(")[0].strip().title()
                if nome in set(grupos["hub"]):
                    linhas.append({"hub": nome, "tipo": "grupo", "cnpj_basico": x["cnpj_basico"]})
    m = pd.DataFrame(linhas).drop_duplicates()
    if m.empty:
        return m
    return m.join(u, on="cnpj_basico", how="inner").sort_values(["hub", "situacao"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--minimo-canal", type=int, default=5)
    ap.add_argument("--minimo-grupo", type=int, default=3)
    a = ap.parse_args()
    contatos = carregar_contatos()                         # robô + Receita
    universo = carregar_universo()
    canais = mapear_canais(contatos, universo, a.minimo_canal)
    grupos = mapear_grupos(contatos, universo, a.minimo_grupo)
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(SAIDA, engine="openpyxl") as w:
        canais.to_excel(w, sheet_name="Canais", index=False)
        grupos.to_excel(w, sheet_name="Grupos", index=False)
        membros(contatos, universo, canais, grupos).to_excel(w, sheet_name="Empresas", index=False)
    print(f"Canais (contato em {a.minimo_canal}+ empresas): {len(canais):,}"
          + (f" | cobrem {int(canais['empresas'].sum()):,} vínculos, {int(canais['sem_compra'].sum()):,} sem compra" if not canais.empty else ""))
    if not canais.empty:
        print(canais.head(10)[["hub", "empresas", "ja_clientes", "sem_compra", "provavel_contabilidade"]].to_string(index=False))
    print(f"\nGrupos (sócio em {a.minimo_grupo}+ empresas): {len(grupos):,}")
    if not grupos.empty:
        print(grupos.head(5)[["hub", "empresas", "ja_clientes", "sem_compra"]].to_string(index=False))
    print(f"\nSalvo: {SAIDA}")
    from src.tools.log_atualizacoes import registrar
    registrar("hubs", f"{len(canais)} canais, {len(grupos)} grupos")


if __name__ == "__main__":
    main()
