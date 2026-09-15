from src.tools.portfolio import PortfolioTool


portfolio = PortfolioTool()

catalogo = portfolio.catalogo()

print("\n" + "=" * 70)
print("CATÁLOGO")
print("=" * 70)

print("Total de soluções:", len(catalogo))

print("\nPrimeiras 10:")

for item in catalogo[:10]:
    print("\nENTIDADE:", item["entidade"])
    print("NOME:", item["nome"])
    print("CAMINHO:", item["caminho_texto"])


# ==============================================================
# BUSCA: MANUTENÇÃO
# ==============================================================

print("\n" + "=" * 70)
print("BUSCA: MANUTENÇÃO")
print("=" * 70)

resultados = portfolio.buscar(
    "MANUTENÇÃO",
    entidade="SENAI",
    limite=10,
)

for item in resultados:
    print("\n", item["nome"])
    print(" →", item["caminho_texto"])


# ==============================================================
# BUSCA: QUALIDADE
# ==============================================================

print("\n" + "=" * 70)
print("BUSCA: QUALIDADE")
print("=" * 70)

resultados = portfolio.buscar(
    "QUALIDADE",
    entidade="SENAI",
    limite=15,
)

for item in resultados:
    print("\n", item["nome"])
    print(" →", item["caminho_texto"])


# ==============================================================
# BUSCA: ALIMENTOS
# ==============================================================

print("\n" + "=" * 70)
print("BUSCA: ALIMENTOS")
print("=" * 70)

resultados = portfolio.buscar(
    "ALIMENTOS",
    entidade="SENAI",
    limite=15,
)

for item in resultados:
    print("\n", item["nome"])
    print(" →", item["caminho_texto"])


# ==============================================================
# BUSCA: SEGURANÇA
# ==============================================================

print("\n" + "=" * 70)
print("BUSCA: SEGURANÇA")
print("=" * 70)

resultados = portfolio.buscar(
    "SEGURANÇA",
    entidade="SESI",
    limite=15,
)

for item in resultados:
    print("\n", item["nome"])
    print(" →", item["caminho_texto"])
print("\n" + "=" * 70)
print("SOLUÇÕES RELEVANTES PARA: ALIMENTOS")
print("=" * 70)

termos = [
    ("QUALIDADE", "SENAI"),
    ("ALIMENTOS", "SENAI"),
    ("SEGURANÇA", "SESI"),
    ("ERGONOMIA", "SESI"),
    ("MANUTENÇÃO", "SENAI"),
]

for termo, entidade in termos:

    print(f"\n[{entidade}] {termo}")

    resultados = portfolio.buscar(
        termo,
        entidade=entidade,
        limite=5,
    )

    for item in resultados:
        print(f"  • {item['nome']}")
        print(f"    {item['caminho_texto']}")