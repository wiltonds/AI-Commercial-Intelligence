import json
from pathlib import Path
from pprint import pprint

path = Path("knowledge/portfolio/portfolio_compact.json")

with open(path, "r", encoding="utf-8") as f:
    portfolio = json.load(f)


def mostrar_nos(no, nivel=0, max_nivel=3):

    indent = "  " * nivel

    if not isinstance(no, dict):
        print(indent, no)
        return

    print(f"{indent}n = {no.get('n')}")
    print(f"{indent}t = {no.get('t')}")

    children = no.get("ch", [])

    print(f"{indent}children = {len(children)}")

    if nivel < max_nivel:

        for filho in children[:5]:

            print()
            print(f"{indent}--- filho ---")

            mostrar_nos(filho, nivel + 1, max_nivel)


print("\n" + "=" * 70)
print("AMOSTRA DA ÁRVORE SESI")
print("=" * 70)

mostrar_nos(portfolio["trees"]["SESI"])


print("\n" + "=" * 70)
print("AMOSTRA DA ÁRVORE SENAI")
print("=" * 70)

mostrar_nos(portfolio["trees"]["SENAI"])


print("\n" + "=" * 70)
print("ESTATÍSTICAS")
print("=" * 70)

pprint(portfolio["stats"])