"""
coletar_bndes.py — Financiamentos do BNDES contratados por empresas de AL.

Baixa do portal de dados abertos do BNDES os arquivos de operações (não
automáticas e, com --automaticas, as feitas via bancos: FINAME/BNDES Máquinas,
giro etc.), fica com as empresas privadas de AL dos últimos 24 meses (uma linha
por empresa, com segmento: indústria, construção, comércio e serviços...) e grava
data/processed/SINAIS_BNDES.csv, ligado à base pelo CNPJ.

O BNDES atualiza mensalmente; o GitHub Actions roda às segundas.

Uso:
    python jobs/coletar_bndes.py
    python jobs/coletar_bndes.py --arquivo operacoes.csv     # arquivo baixado à mão
    python jobs/coletar_bndes.py --forcar                    # baixa mesmo sem atualização
    python jobs/coletar_bndes.py --automaticas               # inclui as via bancos (arquivo grande, usado no Actions)
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src.sinais.bndes import API_CKAN, achar_recursos, ler_operacoes, para_sinais  # noqa: E402
from src.sinais.fontes import registrar_execucao  # noqa: E402
from src.sinais.noticias import carregar_empresas  # noqa: E402

FONTE_ID = "bndes"
SAIDA = RAIZ / "data" / "processed" / "SINAIS_BNDES.csv"
# operações de AL já filtradas (pequeno) e a versão dos arquivos do BNDES de onde vieram:
# se o BNDES não publicou nada novo, o robô não baixa o 1,2 GB de novo, só recalcula os sinais.
CACHE = RAIZ / "data" / "processed" / "BNDES_OPERACOES_AL.csv"
VERSAO = RAIZ / "data" / "processed" / "BNDES_VERSAO.json"


def _sessao():
    import requests

    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (Radar de Oportunidades SENAI-AL)"
    return s


def baixar_com_retomada(sessao, url: str, destino: Path, tentativas: int = 30) -> None:
    """Baixa arquivo grande retomando de onde parou (HTTP Range) quando a conexão cai.

    O arquivo das automáticas passa de 1 GB e o servidor do BNDES costuma cortar
    a conexão no meio do caminho.
    """
    import time

    import requests

    total = None
    for tentativa in range(1, tentativas + 1):
        feito = destino.stat().st_size if destino.exists() else 0
        if total is not None and feito >= total:
            return
        cab = {"Range": f"bytes={feito}-"} if feito else {}
        try:
            with sessao.get(url, headers=cab, timeout=(30, 120), stream=True) as r:
                if r.status_code == 416:          # já tem tudo
                    return
                r.raise_for_status()
                if feito and r.status_code != 206:  # servidor ignorou o Range: recomeça
                    feito = 0
                if total is None:
                    tam = r.headers.get("Content-Range", "").rsplit("/", 1)[-1] if r.status_code == 206 \
                        else r.headers.get("Content-Length")
                    total = int(tam) if tam and tam.isdigit() else None
                with open(destino, "ab" if feito else "wb") as f:
                    for parte in r.iter_content(chunk_size=1 << 20):
                        f.write(parte)
            if total is None or destino.stat().st_size >= total:
                return
        except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as erro:
            print(f"    conexão caiu em {destino.stat().st_size / 1e6:,.0f} MB "
                  f"(tentativa {tentativa}): {type(erro).__name__}", flush=True)
            time.sleep(min(5 * tentativa, 30))
    raise RuntimeError(f"download incompleto após {tentativas} tentativas: {url}")


def versoes_publicadas(pacote: dict, urls: list[tuple[str, str]]) -> dict:
    """Data da última atualização de cada arquivo, segundo o portal do BNDES."""
    meta = {r["url"]: r for r in pacote["result"]["resources"]}
    return {url: str(meta.get(url, {}).get("last_modified") or meta.get(url, {}).get("metadata_modified")
                     or meta.get(url, {}).get("size") or "") for _, url in urls}


def _fontes(arquivo: str | None, automaticas: bool, pasta: Path, pacote: dict | None = None):
    """(origem, caminho) de cada CSV. Baixa em streaming para o disco: o arquivo
    das automáticas tem centenas de MB e não cabe com folga na memória."""
    if arquivo:
        yield ("automática" if automaticas else "não automática"), Path(arquivo)
        return
    s = _sessao()
    pacote = pacote or s.get(API_CKAN, timeout=60).json()
    # o pequeno (não automáticas) primeiro: se o grande falhar, este já está garantido
    urls = sorted(achar_recursos(pacote, automaticas), key=lambda o: o[0] != "não automática")
    if not urls:
        raise RuntimeError("nenhum arquivo de operações encontrado no pacote do BNDES")
    for i, (origem, url) in enumerate(urls):
        destino = pasta / f"bndes_{i}{Path(url).suffix.lower() or '.csv'}"
        print(f"  baixando {url.rsplit('/', 1)[-1]} ({origem}) ...", flush=True)
        baixar_com_retomada(s, url, destino)
        print(f"    {destino.stat().st_size / 1e6:,.0f} MB", flush=True)
        if destino.suffix == ".zip":
            with zipfile.ZipFile(destino) as z:
                for nome in z.namelist():
                    if nome.lower().endswith(".csv"):
                        yield origem, Path(z.extract(nome, pasta))
        else:
            yield origem, destino


def _ler_tudo(fontes) -> tuple[pd.DataFrame, list[str]]:
    """Lê cada arquivo; se um falhar (ex.: download do grande), segue com os outros."""
    partes, erros = [], []
    while True:
        try:
            origem, caminho = next(fontes)
        except StopIteration:
            break
        except Exception as erro:  # falha no download de um arquivo: o gerador acaba, guarda o erro
            erros.append(f"{type(erro).__name__}: {str(erro)[:200]}")
            break
        try:
            partes.append(ler_operacoes(caminho, origem))
        except Exception as erro:
            erros.append(f"{origem}: {type(erro).__name__}: {str(erro)[:200]}")
    if not partes:
        raise RuntimeError("; ".join(erros) or "nenhum arquivo lido")
    return pd.concat(partes, ignore_index=True), erros


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arquivo")
    ap.add_argument("--automaticas", action="store_true")
    ap.add_argument("--forcar", action="store_true", help="baixa mesmo sem atualização no BNDES")
    a = ap.parse_args()
    erros, nota = [], ""
    try:
        pacote, versao = None, {}
        if not a.arquivo:
            pacote = _sessao().get(API_CKAN, timeout=60).json()
            versao = versoes_publicadas(pacote, achar_recursos(pacote, a.automaticas))
        anterior = json.loads(VERSAO.read_text(encoding="utf-8")) if VERSAO.exists() else {}
        sem_novidade = (not a.arquivo and not a.forcar and CACHE.exists() and versao
                        and all(versao.get(u) and versao[u] == anterior.get(u) for u in versao))
        if sem_novidade:
            print("BNDES sem atualização desde a última coleta: recalculando os sinais com o que já temos.")
            ops = pd.read_csv(CACHE, dtype=str, encoding="utf-8-sig", keep_default_na=False)
            ops["data_contratacao"] = pd.to_datetime(ops["data_contratacao"], errors="coerce")
            ops["valor"] = pd.to_numeric(ops["valor"], errors="coerce")
            nota = " · BNDES sem atualização, sem download"
        else:
            with tempfile.TemporaryDirectory() as tmp:
                ops, erros = _ler_tudo(_fontes(a.arquivo, a.automaticas, Path(tmp), pacote))
            # guarda só os últimos 3 anos de AL: arquivo pequeno, cabe no repositório
            ops = ops[ops["data_contratacao"] >= pd.Timestamp(date.today()) - pd.DateOffset(years=3)]
            ops.to_csv(CACHE, index=False, encoding="utf-8-sig")
            if versao and not erros:  # só marca a versão se baixou tudo
                VERSAO.write_text(json.dumps(versao, ensure_ascii=False, indent=1), encoding="utf-8")
        sinais = para_sinais(ops, carregar_empresas(), date.today())
        sinais.to_csv(SAIDA, index=False, encoding="utf-8-sig")
    except Exception as erro:
        registrar_execucao(FONTE_ID, "falha", 0, f"{type(erro).__name__}: {erro}")
        raise
    n_emp = sinais["cnpj_basico"].nunique() if not sinais.empty else 0
    seg = sinais["segmento"].value_counts().to_dict() if not sinais.empty else {}
    resumo = ", ".join(f"{k} {v}" for k, v in seg.items())
    msg = f"{n_emp} empresas de AL com financiamento em 24 meses ({resumo}){nota}"
    if erros:
        msg += " · PARCIAL, arquivo não lido: " + "; ".join(erros)
    registrar_execucao(FONTE_ID, "sucesso", len(sinais), msg)
    print(f"Pronto: {len(sinais)} empresas de AL.{nota}")


if __name__ == "__main__":
    main()
