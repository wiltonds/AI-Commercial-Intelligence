"""
checar_entradas.py — O que precisa ser atualizado para o painel ficar em dia?

Lê config/entradas.yaml e o log de atualizações que cada job grava, e mostra,
na ordem da rotina mensal, o que está em dia, vencido ou nunca foi rodado —
com o que baixar e o comando de cada item vencido.

Uso:
    python jobs/checar_entradas.py
    python jobs/checar_entradas.py --detalhe     # mostra também como obter e as colunas exigidas
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.log_atualizacoes import ultimas  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
ARQ_ENTRADAS = RAIZ / "config" / "entradas.yaml"


def avaliar(entradas: dict, log: dict, agora: datetime, raiz: Path = RAIZ) -> list[dict]:
    linhas = []
    for chave, e in sorted(entradas.items(), key=lambda kv: kv[1].get("ordem", 99)):
        freq = int(e.get("frequencia_dias", 30))
        if chave == "tabela_dn":                       # referência: vale se o arquivo existe
            existe = (raiz / "config" / "referencia" / "tabela_dn_cni.csv").exists()
            status, quando, idade = ("OK (referência)" if existe else "FALTANDO"), "-", None
        elif chave == "publicacao":
            status, quando, idade = "MANUAL", "-", None
        elif chave not in log:
            status, quando, idade = "NUNCA REGISTRADO", "-", None
        else:
            data = datetime.fromisoformat(log[chave]["data"])
            idade = (agora - data).days
            quando = data.strftime("%d/%m/%Y")
            if idade > freq:
                status = f"VENCIDO há {idade - freq} dias"
            elif idade > freq - 7:
                status = f"vence em {freq - idade} dias"
            else:
                status = "em dia"
        linhas.append({"chave": chave, "nome": e["nome"], "status": status, "ultima": quando,
                       "freq": freq, "comando": " ".join(str(e.get("comando", "")).split()),
                       "como_obter": " ".join(str(e.get("como_obter", "")).split()),
                       "colunas": e.get("colunas") or [], "onde": e.get("onde_colocar", ""),
                       "atencao": status.startswith(("VENCIDO", "NUNCA", "FALTANDO"))})
    return linhas


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--detalhe", action="store_true")
    args = parser.parse_args()
    entradas = yaml.safe_load(open(ARQ_ENTRADAS, encoding="utf-8"))["entradas"]
    linhas = avaliar(entradas, ultimas(), datetime.now())

    print(f"{'Entrada':52} {'Última':11} {'A cada':>7}  Situação")
    print("-" * 100)
    for x in linhas:
        marca = "!!" if x["atencao"] else "  "
        print(f"{marca}{x['nome'][:50]:50} {x['ultima']:11} {str(x['freq']) + 'd':>7}  {x['status']}")
    pendentes = [x for x in linhas if x["atencao"] or args.detalhe]
    for x in pendentes:
        print(f"\n>> {x['nome']}")
        print(f"   Obter:   {x['como_obter']}")
        if x["colunas"]:
            print(f"   Colunas: {', '.join(map(str, x['colunas']))}")
        print(f"   Colocar: {x['onde']}")
        print(f"   Rodar:   {x['comando']}")
    if not any(x["atencao"] for x in linhas):
        print("\nTudo em dia.")


if __name__ == "__main__":
    main()
