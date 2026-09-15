from pprint import pprint
from src.pipeline import CommercialPipeline


pipeline = CommercialPipeline()

cnpj = "24470149000100"

resultado = pipeline.executar(cnpj)

if resultado is None:
    print("Empresa não encontrada.")

else:
    print("\n" + "=" * 70)
    print("DIAGNÓSTICO COMERCIAL")
    print("=" * 70)

    print("\n[LEAD]")
    pprint(resultado["lead"].model_dump())

    print("\n[QUALIDADE DOS DADOS]")
    pprint(resultado["qualidade_dados"])

    print("\n[QUALIFICAÇÃO SDR]")
    pprint(resultado["qualificacao"])

    print("\n[OPORTUNIDADES]")

    for i, oportunidade in enumerate(
        resultado["oportunidades"],
        start=1,
    ):
        print(f"\n--- Oportunidade {i} ---")
        pprint(oportunidade.model_dump())