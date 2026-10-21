"""
coletar_cno.py — Job de sinais de obra nova (Cadastro Nacional de Obras).

Substitui a tabela fontes_externas.gov_cnoalagoas do DW (que parou de
atualizar) lendo direto da fonte: os dados abertos do CNO da Receita
Federal, publicados diariamente.

Fluxo de uma execução:
  1. obtém o cno.zip nacional (download ou arquivo local já baixado)
  2. lê em blocos e guarda só obras de AL + seus vínculos
  3. mantém obras ATIVAS iniciadas dentro da janela (padrão 180 dias)
  4. gera uma linha por (CNPJ, obra) — responsável e vínculos PJ
  5. pontua (peso por área x decaimento) — regra em config/fontes.yaml
  6. cruza com a Base Mestre pelo CNPJ raiz
  7. grava data/processed/SINAIS_CNO.csv e registra no LOG_FONTES.csv

Uso:
    python jobs/coletar_cno.py --arquivo C:\\Downloads\\cno.zip   # arquivo baixado à mão
    python jobs/coletar_cno.py --url <link direto do cno.zip>     # baixa sozinho
    python jobs/coletar_cno.py                                    # baixa pelo url_download do fontes.yaml (padrão)

O link de download do repositório da Receita muda de tempos em tempos
(hoje é um compartilhamento Nextcloud). Por isso o caminho mais robusto
é: página do dataset (fontes.yaml -> cno.url_pagina) > Recursos > ZIP >
cno.zip, e rodar com --arquivo. Quando o link estiver estável, grave-o
em url_download e agende sem argumentos.

Agendamento: 1x/dia (Agendador de Tarefas do Windows, cron ou o
scheduler que o Observatório definir).
"""

import argparse
import sys
from datetime import date
from pathlib import Path
from time import sleep

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.sinais.cno import (  # noqa: E402
    cruzar_com_base,
    extrair_sinais,
    filtrar_obras_recentes,
    ler_zip_cno,
    pontuar,
)
from src.sinais.fontes import carregar_catalogo, registrar_execucao  # noqa: E402
from src.tools.cnpj_raiz import consolidar_por_cnpj_raiz  # noqa: E402
from src.tools.company_data import BASE_PATH  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
ZIP_LOCAL = RAIZ / "data" / "raw" / "cno" / "cno.zip"
ARQ_SAIDA = RAIZ / "data" / "processed" / "SINAIS_CNO.csv"
FONTE_ID = "cno"

COLUNAS_SAIDA = [
    "score_momento", "cnpj_basico", "cnpj", "razao_social", "na_base_mestre",
    "STATUS_RELACIONAMENTO_REAL", "Porte", "CNAE PRIMARIO",
    "tipo_sinal", "descricao", "papel", "qualificacao", "qualificacao_desc",
    "municipio", "bairro", "area_total", "unidade_medida",
    "data_evento", "data_publicacao", "idade_dias", "peso", "validade_dias", "cno", "fonte",
]


# O repositório da Receita fica atrás de um WAF que recusa User-Agent
# "cru" (python-requests) e alterna 200/404 de forma errática. Headers
# de navegador + novas tentativas resolvem na prática.
HEADERS_NAVEGADOR = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.8,en-US;q=0.5,en;q=0.3",
}
TENTATIVAS = 4
ESPERA_SEG = 30  # multiplicada pelo nº da tentativa


def baixar(
    url: str, destino: Path, tentativas: int | None = None, espera: int | None = None,
    avisar=print, progresso=None,
) -> Path:
    tentativas = tentativas or TENTATIVAS
    espera = ESPERA_SEG if espera is None else espera
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".zip.part")
    ultimo_erro = None

    for tentativa in range(1, tentativas + 1):
        try:
            with requests.get(url, stream=True, timeout=120,
                              headers=HEADERS_NAVEGADOR, allow_redirects=True) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length") or 0)
                baixado = 0
                with open(temporario, "wb") as f:
                    for pedaco in r.iter_content(chunk_size=1 << 20):
                        f.write(pedaco)
                        baixado += len(pedaco)
                        if total and progresso:
                            progresso(baixado / total)
                        elif total and progresso is None:
                            print(f"\r  {baixado / 1e6:,.0f} de {total / 1e6:,.0f} MB", end="")
                if progresso is None:
                    print()

            with open(temporario, "rb") as f:
                if f.read(2) != b"PK":  # WAF devolve HTML "Request Rejected" com status 200
                    raise ValueError("resposta não é um zip (provável bloqueio do WAF)")

            temporario.replace(destino)
            return destino
        except (requests.RequestException, ValueError) as erro:
            ultimo_erro = erro
            avisar(f"tentativa {tentativa}/{tentativas} falhou: {erro}")
            if tentativa < tentativas:
                sleep(espera * tentativa)

    temporario.unlink(missing_ok=True)
    raise RuntimeError(
        f"Não foi possível baixar o cno.zip ({ultimo_erro}). Alternativa: baixe no "
        "navegador e rode com --arquivo <caminho do cno.zip>."
    )


def carregar_empresas() -> pd.DataFrame:
    df = pd.read_csv(BASE_PATH, dtype=str, low_memory=False, encoding="utf-8-sig")
    df["cnpj"] = df["cnpj"].str.replace(r"\D", "", regex=True).str.zfill(14)
    df["POSSUI_SESI"] = df.get("TEM_SESI", "").astype(str).str.upper().eq("TRUE")
    df["POSSUI_SENAI"] = df.get("TEM_SENAI", "").astype(str).str.upper().eq("TRUE")
    df["POSSUI_SEBRAE"] = False
    # consolidar_por_cnpj_raiz já deriva STATUS_RELACIONAMENTO_REAL
    empresas = consolidar_por_cnpj_raiz(df)
    return empresas


def rodar(
    arquivo: Path | None, url: str | None, hoje: date,
    avisar=print, progresso=None, manter_zip: bool = True,
) -> pd.DataFrame:
    regra = carregar_catalogo()[FONTE_ID]
    janela = int(regra["sinal"].get("janela_coleta_dias", 180))

    if arquivo is None:
        url = url or str(regra.get("url_download", ""))
        if not url.startswith("http"):
            raise SystemExit(
                "Sem link de download configurado. Baixe o cno.zip em\n"
                f"  {regra['url_pagina']}\n"
                "e rode:  python jobs/coletar_cno.py --arquivo <caminho do cno.zip>"
            )
        avisar(f"Baixando o CNO da Receita (~315 MB) ...")
        arquivo = baixar(url, ZIP_LOCAL, avisar=avisar, progresso=progresso)

    avisar("Lendo o arquivo nacional e filtrando Alagoas ...")
    obras, vinculos = ler_zip_cno(arquivo)
    if not manter_zip and arquivo == ZIP_LOCAL:
        ZIP_LOCAL.unlink(missing_ok=True)  # libera ~315 MB (servidor em nuvem)
    avisar(f"Obras em AL: {len(obras):,} | vínculos dessas obras: {len(vinculos):,}")

    recentes = filtrar_obras_recentes(obras, hoje, janela)
    avisar(f"Ativas nos últimos {janela} dias: {len(recentes):,}")

    sinais = extrair_sinais(recentes, vinculos, hoje)
    sinais = pontuar(sinais, hoje, regra["sinal"])
    sinais = cruzar_com_base(sinais, carregar_empresas())

    saida = sinais[[c for c in COLUNAS_SAIDA if c in sinais.columns]]
    ARQ_SAIDA.parent.mkdir(parents=True, exist_ok=True)
    saida.to_csv(ARQ_SAIDA, index=False, encoding="utf-8-sig")

    na_base = int(saida.loc[saida["na_base_mestre"], "cnpj_basico"].nunique())
    avisar(f"Salvo: {ARQ_SAIDA.name}")
    avisar(f"Sinais (CNPJ x obra): {len(saida):,} | empresas distintas: "
          f"{saida['cnpj_basico'].nunique():,} | já na Base Mestre: {na_base:,}")
    return saida


def executar(
    arquivo: Path | None = None, url: str | None = None, hoje: date | None = None,
    avisar=print, progresso=None, manter_zip: bool = True,
) -> pd.DataFrame:
    """Roda e registra no LOG_FONTES (sucesso ou falha) — usado pelo
    agendador (main) e pelo botão "Atualizar sinais" do app."""
    hoje = hoje or date.today()
    try:
        saida = rodar(arquivo, url, hoje, avisar=avisar, progresso=progresso,
                      manter_zip=manter_zip)
    except SystemExit:
        registrar_execucao(FONTE_ID, "sem_arquivo", 0, "download não configurado")
        raise
    except Exception as erro:
        registrar_execucao(FONTE_ID, "falha", 0, f"{type(erro).__name__}: {erro}")
        raise
    registrar_execucao(FONTE_ID, "sucesso", len(saida),
                       f"{saida['cnpj_basico'].nunique()} empresas")
    return saida


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--arquivo", type=Path, help="cno.zip já baixado")
    parser.add_argument("--url", help="link direto do cno.zip")
    parser.add_argument("--hoje", help="data de referência AAAA-MM-DD (testes)")
    args = parser.parse_args()

    hoje = date.fromisoformat(args.hoje) if args.hoje else date.today()
    executar(args.arquivo, args.url, hoje)


if __name__ == "__main__":
    main()
