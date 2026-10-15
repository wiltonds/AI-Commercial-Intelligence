"""
carregar_base_ampliada.py — Não indústrias de AL + colaboradores + contatos da Receita.

Lê os dados abertos do CNPJ (Receita Federal, carga mensal) e gera:

  data/processed/BASE_AMPLIADA_AL.csv
      empresas ativas de AL FORA da Base Mestre, de qualquer porte Receita
      (ME, EPP, DEMAIS), MENOS os optantes do MEI (regra comercial: MEI não é
      atendido; microempresa é), uma linha por CNPJ raiz — sem contatos.
      Tipo "Não indústria" (CNAE fora da Tabela DN da CNI) ou "Indústria
      fora da Base Mestre" (CNAE na Tabela DN, mas ausente da base — lacuna).
      Órgãos públicos ficam fora (recorte B2B).

  data/processed/MEI_BASE_MESTRE.csv
      CNPJ raiz da Base Mestre que são MEI optante (dado público do Simples),
      para o painel tirar essas empresas da fila de prospecção.

  data/contatos/CONTATOS_RECEITA.csv   (fora do Git — LGPD)
      telefones e e-mail cadastrais das empresas acima E das indústrias
      da Base Mestre. É o e-mail que a BrasilAPI não entrega.

Colaboradores: não há fonte pública com nº de empregados por CNPJ. A
faixa sai do Porte FIEA da base de relacionamento SESI/SENAI, quando a
empresa está lá; nos demais casos fica "Sem informação".

Uso:
    python jobs/carregar_base_ampliada.py --pasta "C:/caminho/dos/zips"
    python jobs/carregar_base_ampliada.py --mes 2026-09     # tenta baixar

A pasta precisa ter Estabelecimentos0..9.zip, Empresas0..9.zip, Simples.zip
(para tirar os MEI) e, para os nomes, Municipios.zip, Cnaes.zip e Naturezas.zip — os mesmos arquivos
que o BI_Project baixa. Se o download automático falhar, baixe pelo
navegador em https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9
e use --pasta.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.company_data import BASE_PATH  # noqa: E402
from src.tools.lgpd import limpar_cpf  # noqa: E402
from src.tools.receita_cnpj import (  # noqa: E402
    PORTE,
    carregar_filtro,
    carregar_porte_fiea,
    carregar_regua_industria,
    consolidar_por_raiz,
    faixa_colaboradores,
    formatar_tel,
    ler_codigos,
    ler_empresas,
    ler_estabelecimentos,
    ler_mei,
    manter_para_venda,
    tipo_empresa,
)

RAIZ = Path(__file__).resolve().parent.parent
ARQ_SAIDA = RAIZ / "data" / "processed" / "BASE_AMPLIADA_AL.csv"
ARQ_CONTATOS = RAIZ / "data" / "contatos" / "CONTATOS_RECEITA.csv"
ARQ_MEI_MESTRE = RAIZ / "data" / "processed" / "MEI_BASE_MESTRE.csv"
ARQ_RELACIONAMENTO = RAIZ / "data" / "raw" / "BASE_CONSOLIDADA_SESI_SENAI.xlsx"
URL_DAV = "https://arquivos.receitafederal.gov.br/public.php/dav/files/YggdBLfdninEJX9/{mes}/{arquivo}"
ARQUIVOS = ([f"Estabelecimentos{i}.zip" for i in range(10)] + [f"Empresas{i}.zip" for i in range(10)]
            + ["Simples.zip", "Municipios.zip", "Cnaes.zip", "Naturezas.zip"])
# Regra comercial: atendemos ME, EPP e DEMAIS; só o MEI optante fica fora.
PORTES_ALVO = {"DEMAIS", "PEQUENO PORTE", "MICRO EMPRESA"}
NATUREZA_EMPRESARIO_INDIVIDUAL = "2135"
NATUREZAS_B2B = ("2", "3")        # 2xxx entidades empresariais, 3xxx sem fins lucrativos


def baixar(mes: str, pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    for nome in ARQUIVOS:
        destino = pasta / nome
        if destino.exists() and destino.stat().st_size > 0:
            continue
        url = URL_DAV.format(mes=mes, arquivo=nome)
        print(f"Baixando {nome} ...")
        with requests.get(url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(destino.with_suffix(".parcial"), "wb") as f:
                for bloco in r.iter_content(1 << 20):
                    f.write(bloco)
        destino.with_suffix(".parcial").rename(destino)


def montar(pasta: Path, uf: str = "AL") -> tuple[pd.DataFrame, pd.DataFrame]:
    zips_estab = sorted(pasta.glob("Estabelecimentos*.zip"))
    zips_emp = sorted(pasta.glob("Empresas*.zip"))
    if not zips_estab or not zips_emp:
        raise FileNotFoundError(f"Sem Estabelecimentos*.zip / Empresas*.zip em {pasta}")

    partes = []
    for z in zips_estab:
        parte = ler_estabelecimentos(z, uf)
        print(f"  {z.name}: {len(parte):,} estabelecimentos ativos em {uf}")
        partes.append(parte)
    estab = consolidar_por_raiz(pd.concat(partes, ignore_index=True))
    print(f"Empresas ativas em {uf} (por CNPJ raiz): {len(estab):,}")

    raizes = set(estab["cnpj_basico"])
    emp = pd.concat([ler_empresas(z, raizes) for z in zips_emp], ignore_index=True)
    df = estab.merge(emp.drop_duplicates("cnpj_basico"), on="cnpj_basico", how="left")

    municipios = ler_codigos(pasta / "Municipios.zip")
    cnaes = ler_codigos(pasta / "Cnaes.zip")
    naturezas = ler_codigos(pasta / "Naturezas.zip")

    mestre = pd.read_csv(BASE_PATH, dtype=str, usecols=["CNPJ_BASICO"], encoding="utf-8-sig")
    raizes_mestre = set(mestre["CNPJ_BASICO"].str.zfill(8))

    regua, origem_regua = carregar_regua_industria(base_mestre=BASE_PATH)
    print(f"Régua de indústria: {origem_regua}")
    df["na_base_mestre"] = df["cnpj_basico"].isin(raizes_mestre)
    df["Tipo"] = [tipo_empresa(c, m, regua) for c, m in zip(df["cnae_principal"], df["na_base_mestre"])]
    df["Porte"] = df["porte_codigo"].map(PORTE).fillna("NÃO INFORMADO")
    df["Municipio"] = df["municipio_codigo"].map(municipios).fillna("").str.title()
    df["CNAE PRIMARIO"] = df["cnae_principal"].map(cnaes).fillna("")
    df["natureza"] = df["natureza_juridica"].map(naturezas).fillna(df["natureza_juridica"])

    simples = pasta / "Simples.zip"
    if simples.exists():
        mei = ler_mei(simples, raizes)
        df["mei"] = df["cnpj_basico"].isin(mei)
        print(f"MEI optantes em {uf} (fora do recorte): {len(mei):,}")
    else:
        # Sem o Simples.zip não dá para saber quem é MEI: aproximação pelo Empresário
        # Individual microempresa (quase todo MEI é EI; alguns EI não MEI saem junto).
        df["mei"] = (df["natureza_juridica"] == NATUREZA_EMPRESARIO_INDIVIDUAL) & (df["Porte"] == "MICRO EMPRESA")
        print("ATENÇÃO: sem Simples.zip — MEI aproximado por Empresário Individual ME. Baixe o Simples.zip.")

    fiea = carregar_porte_fiea(ARQ_RELACIONAMENTO).set_index("cnpj_basico")
    df["porte_fiea"] = df["cnpj_basico"].map(fiea["porte_fiea"]).fillna("")
    df["POSSUI_SESI"] = df["cnpj_basico"].map(fiea["sesi"]).fillna(False).astype(bool)
    df["POSSUI_SENAI"] = df["cnpj_basico"].map(fiea["senai"]).fillna(False).astype(bool)

    # contatos da Receita: indústrias da Base Mestre + não indústrias do recorte
    alvo = (~df["na_base_mestre"] & df["Porte"].isin(PORTES_ALVO) & ~df["mei"]
            & df["natureza_juridica"].str[:1].isin(NATUREZAS_B2B))
    alvo &= manter_para_venda(df, carregar_filtro())
    contatos = df[(df["na_base_mestre"] & ~df["mei"]) | alvo].assign(
        telefone_1=lambda d: [formatar_tel(a, b) for a, b in zip(d["ddd_1"], d["telefone_1"])],
        telefone_2=lambda d: [formatar_tel(a, b) for a, b in zip(d["ddd_2"], d["telefone_2"])],
        email=lambda d: d["email"].str.strip().str.lower(),
    )[["cnpj_basico", "cnpj", "telefone_1", "telefone_2", "email"]]

    amp = df[alvo].copy()
    amp["razao_social"] = amp["razao_social"].fillna(amp["nome_fantasia"])
    amp["Colaboradores (faixa)"] = [faixa_colaboradores(t, p) for t, p in zip(amp["Tipo"], amp["porte_fiea"])]
    amp["Origem colaboradores"] = amp["Colaboradores (faixa)"].map(
        lambda f: "Porte FIEA (base de relacionamento)" if f else "Sem informação")
    colunas = ["cnpj", "cnpj_basico", "razao_social", "nome_fantasia", "Tipo", "Municipio", "Porte",
               "porte_fiea", "Colaboradores (faixa)", "Origem colaboradores", "cnae_principal", "CNAE PRIMARIO",
               "cnaes_secundarios", "natureza", "capital_social", "data_inicio_atividade",
               "QTD_ESTABELECIMENTOS", "POSSUI_SESI", "POSSUI_SENAI"]
    amp = amp[colunas].sort_values(["Porte", "razao_social"]).reset_index(drop=True)
    mei_mestre = df.loc[df["na_base_mestre"] & df["mei"], ["cnpj_basico"]].reset_index(drop=True)
    return amp, contatos, mei_mestre


def refiltrar() -> None:
    """Reaplica o filtro de venda no arquivo já gerado (sem reprocessar a Receita)."""
    amp = pd.read_csv(ARQ_SAIDA, dtype=str, encoding="utf-8-sig").fillna("")
    antes = len(amp)
    amp = amp[manter_para_venda(amp, carregar_filtro())]
    limpar_cpf(amp).to_csv(ARQ_SAIDA, index=False, encoding="utf-8-sig")   # repositório público: sem CPF
    if ARQ_CONTATOS.exists():
        mestre = pd.read_csv(BASE_PATH, dtype=str, usecols=["CNPJ_BASICO"], encoding="utf-8-sig")
        manter = set(mestre["CNPJ_BASICO"].str.zfill(8)) | set(amp["cnpj_basico"])
        cont = pd.read_csv(ARQ_CONTATOS, dtype=str, encoding="utf-8-sig").fillna("")
        cont[cont["cnpj_basico"].isin(manter)].to_csv(ARQ_CONTATOS, index=False, encoding="utf-8-sig")
    print(f"Refiltrado: {antes:,} -> {len(amp):,} empresas")
    print(pd.crosstab(amp["Tipo"], amp["Porte"]).to_string())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pasta", help="pasta com os .zip da Receita")
    parser.add_argument("--mes", help="AAAA-MM para baixar os arquivos (ex.: 2026-09)")
    parser.add_argument("--refiltrar", action="store_true",
                        help="só reaplica config/referencia/filtro_nao_industria.yaml no arquivo já gerado")
    args = parser.parse_args()
    if args.refiltrar:
        refiltrar()
        return
    if not (args.pasta or args.mes):
        parser.error("informe --pasta ou --mes")
    pasta = Path(args.pasta) if args.pasta else RAIZ / "data" / "raw" / "receita" / args.mes
    if args.mes:
        baixar(args.mes, pasta)

    amp, contatos, mei_mestre = montar(pasta)
    ARQ_SAIDA.parent.mkdir(parents=True, exist_ok=True)
    limpar_cpf(amp).to_csv(ARQ_SAIDA, index=False, encoding="utf-8-sig")   # repositório público: sem CPF
    mei_mestre.to_csv(ARQ_MEI_MESTRE, index=False, encoding="utf-8-sig")
    print(f"Base Mestre: {len(mei_mestre):,} empresas são MEI optante (saem da fila de prospecção)")
    ARQ_CONTATOS.parent.mkdir(parents=True, exist_ok=True)
    contatos.to_csv(ARQ_CONTATOS, index=False, encoding="utf-8-sig")

    print(f"\nSalvo: {ARQ_SAIDA.relative_to(RAIZ)}  ({len(amp):,} não indústrias)")
    print(pd.crosstab(amp["Tipo"], amp["Porte"]).to_string())
    print(f"Com faixa de colaboradores: {int((amp['Origem colaboradores'] != 'Sem informação').sum()):,}")
    from src.tools.log_atualizacoes import registrar
    registrar("receita_cnpj", f"{len(amp):,} fora da Base Mestre; pasta {pasta.name}")
    print(f"Salvo: {ARQ_CONTATOS.relative_to(RAIZ)}  ({len(contatos):,} empresas, "
          f"{int((contatos['email'] != '').sum()):,} com e-mail)")


if __name__ == "__main__":
    main()
