"""Carteira por unidade — quem é a Unidade Responsável (UR) de cada empresa no SESI e no SENAI.

Segue a Minuta da Política de Carteirização (config/referencia/carteira_minuta.csv):

  1. Empresa com histórico na entidade  -> fica na unidade do histórico (regra de preservação).
  2. Histórico com mais de uma unidade   -> vale o endereço da sede.
  3. Empresa sem histórico (nova)        -> vale o endereço da sede: bairro em Maceió, município fora dela.
  4. Sede fora de AL                     -> "A definir (1º serviço)" — exceção da minuta.

Unidades vigentes (out/2026):
  SESI : Farol (= "Cambona" da minuta), Tabuleiro, Agreste/Sertão (= "Arapiraca" da minuta)
  SENAI: Poço, Agreste/Sertão — Benedito Bentes foi desativado e a carteira dele vai para o Poço.

Cada CNPJ raiz recebe DUAS unidades (uma SESI, uma SENAI): a mesma empresa pode ser
carteira do SESI Farol e do SENAI Poço ao mesmo tempo.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
ARQ_MINUTA = RAIZ / "config" / "referencia" / "carteira_minuta.csv"
UNIDADES_SESI = ["Farol", "Tabuleiro", "Agreste/Sertão"]
UNIDADES_SENAI = ["Poço", "Agreste/Sertão"]
A_DEFINIR = "A definir (1º serviço)"

# grafias que aparecem no cadastro da Receita e não batem com a tabela da minuta
ALIAS_BAIRRO = {
    "STELLA MARIS": "JATIUCA", "STELA MARIS": "JATIUCA", "TABULEIRO": "TABULEIRO DO MARTINS",
    "TABULEIRO DOS MARTINS": "TABULEIRO DO MARTINS", "TAB DOS MARTINS": "TABULEIRO DO MARTINS",
    "TAB. DOS MARTINS": "TABULEIRO DO MARTINS", "TAB DO MARTINS": "TABULEIRO DO MARTINS",
    "TAB.DOS MARTINS": "TABULEIRO DO MARTINS", "TAB. DO MARTINS": "TABULEIRO DO MARTINS",
    "TAB.DO MARTINS": "TABULEIRO DO MARTINS", "T DOS MARTINS": "TABULEIRO DO MARTINS",
    "T MARTINS": "TABULEIRO DO MARTINS", "DISTRITO INDUSTRIAL": "TABULEIRO DO MARTINS",
    "POLO INDUSTRIAL": "TABULEIRO DO MARTINS", "GRUTA": "GRUTA DE LOURDES", "GRUTA DE LURDES": "GRUTA DE LOURDES",
    "MANGABEIRA": "MANGABEIRAS", "PONTA GROSA": "PONTA GROSSA", "PAJUARA": "PAJUCARA", "BARRO DURRO": "BARRO DURO",
    "AREA RURAL": "ZONA RURAL", "AREA RURAL DE MACEIO": "ZONA RURAL", "PONTAL": "PONTAL DA BARRA",
    "TRAPICHE": "TRAPICHE DA BARRA", "VERGEL": "VERGEL DO LAGO", "JACITINHO": "JACINTINHO",
    "CHA DE JAQUEIRA": "CHA DA JAQUEIRA", "SANTOS DUMOND": "SANTOS DUMONT", "CIDADE UNIVESITARIA": "CIDADE UNIVERSITARIA",
    "CIDADE UNIVERSITRIA": "CIDADE UNIVERSITARIA", "CID UNIVERSITARIA": "CIDADE UNIVERSITARIA",
    "CID. UNIVERSITARIA": "CIDADE UNIVERSITARIA", "BENDITO BENTES": "BENEDITO BENTES", "STO AMARO": "SANTO AMARO",
    "P VERDE": "PONTA VERDE", "PORTA VERDE": "PONTA VERDE", "JAITUCA": "JATIUCA", "FARL": "FAROL",
    # conferidos em out/2026 (data/privado/bairros_conferir.csv)
    "JACERECICA": "JACARECICA", "ANATARES": "ANTARES", "CRUS DAS ALMAS": "CRUZ DAS ALMAS",
    "MAGABEIRAS": "MANGABEIRAS", "JARDIM PETRPOLIS": "JARDIM PETROPOLIS", "GRUTAS DE LOURDES": "GRUTA DE LOURDES",
    "CONJUNTO BENEDITO BENTES I": "BENEDITO BENTES", "TABULEIRO MARTINS": "TABULEIRO DO MARTINS",
    "TABULEIRO DOS MARTIN": "TABULEIRO DO MARTINS", "TABULEIRO DOS MATINS": "TABULEIRO DO MARTINS",
    "TABUELEIRO DOS MARTINS": "TABULEIRO DO MARTINS", "TABUL DOS MARTINS": "TABULEIRO DO MARTINS",
}

# Fallback por CEP: quando o bairro da Receita não bate exato com a minuta, vale o bairro em que caem
# os outros estabelecimentos de Maceió com o mesmo CEP — e o CEP vence o nome se os dois discordarem.
CEP_MIN_APOIO = 2   # estabelecimentos com bairro exato no mesmo CEP, e maioria absoluta entre eles


def norm(texto) -> str:
    # apóstrofos saem ANTES do NFKD: "´" vira espaço + acento no NFKD ("D´AGUA" -> "D AGUA")
    t = re.sub(r"['´`‘’]", "", str(texto or ""))
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t.upper().replace("-", " ")).strip()


def carregar_minuta(caminho: Path = ARQ_MINUTA) -> tuple[dict, dict]:
    t = pd.read_csv(caminho, dtype=str, encoding="utf-8").fillna("")
    bairros = {r.chave: (r.unidade_sesi, r.unidade_senai) for r in t[t.tipo == "bairro_maceio"].itertuples()}
    municipios = {r.chave: (r.unidade_sesi, r.unidade_senai) for r in t[t.tipo == "municipio"].itertuples()}
    return bairros, municipios


def _limpar_bairro(bairro: str) -> str:
    x = re.sub(r"^(BAIRRO|B\.)\s+", "", norm(bairro))
    return re.sub(r"\s*\(.*\)$", "", x).strip()


def cep_generico(cep) -> bool:
    """CEP que não localiza bairro: inválido ou terminado em 000 (geral da cidade / grande logradouro)."""
    c = re.sub(r"\D", "", str(cep or ""))
    return len(c) != 8 or c.endswith("000")


def mapa_cep_bairro(enderecos: pd.DataFrame, bairros: dict) -> dict:
    """CEP de Maceió -> bairro da minuta, pela maioria dos estabelecimentos cujo bairro bate exato com a tabela."""
    if "cep" not in enderecos.columns or enderecos.empty:
        return {}
    e = enderecos[enderecos["municipio"].map(norm) == "MACEIO"]
    t = pd.DataFrame({"cep": e["cep"].astype(str).str.replace(r"\D", "", regex=True),
                      "bairro": e["bairro"].map(_limpar_bairro)})
    t = t[t["bairro"].isin(bairros.keys()) & ~t["cep"].map(cep_generico)]
    mapa = {}
    for cep, g in t.groupby("cep")["bairro"]:
        v = g.value_counts()
        if v.iloc[0] >= CEP_MIN_APOIO and v.iloc[0] * 2 > len(g):
            mapa[cep] = v.index[0]
    return mapa


def bairro_minuta(bairro: str, bairros: dict) -> str:
    x = _limpar_bairro(bairro)
    if x in bairros:
        return x
    if ALIAS_BAIRRO.get(x) in bairros:
        return ALIAS_BAIRRO[x]
    for k in sorted(bairros, key=len, reverse=True):
        if x.startswith(k + " ") or x.endswith(" " + k):
            return k
    return ""


def unidade_pela_sede(municipio: str, bairro: str, bairros: dict, municipios: dict,
                      cep: str = "", ceps: dict | None = None) -> tuple[str, str, str]:
    """(unidade SESI, unidade SENAI, de onde saiu). Vazio quando não dá para decidir.

    Em Maceió: bairro exato da minuta > bairro pelo CEP (ceps = mapa_cep_bairro) > alias/aproximação do nome."""
    m = norm(municipio)
    if not m:
        return "", "", "sem endereço"
    if m == "MACEIO":
        pelo_cep = "" if cep_generico(cep) else (ceps or {}).get(re.sub(r"\D", "", str(cep)), "")
        if _limpar_bairro(bairro) in bairros or not pelo_cep:
            b = bairro_minuta(bairro, bairros)
            if not b:
                return "", "", f"bairro '{bairro}' fora da tabela da minuta"
            sesi, senai = bairros[b]
            return sesi, senai, f"sede no bairro {b.title()} (Maceió)"
        sesi, senai = bairros[pelo_cep]
        return sesi, senai, f"bairro pelo CEP {cep}: {pelo_cep.title()} (Maceió; na Receita '{bairro}')"
    if m in municipios:
        sesi, senai = municipios[m]
        return sesi, senai, f"sede em {municipio.title()}"
    return "", "", f"município '{municipio}' fora da tabela da minuta"


def unidade_do_historico(entidade: str, unidade: str) -> str:
    """Nome da unidade vigente a partir do texto da exportação de propostas. '' = não reconhecida."""
    e, u = norm(entidade), norm(unidade)
    if "ARAPIRACA" in u or "AGRESTE" in u:
        return "Agreste/Sertão"
    if e == "SESI":
        if "FAROL" in u or "CAMBONA" in u:
            return "Farol"
        if "TABULEIRO" in u:
            return "Tabuleiro"
    if e == "SENAI":
        if "POCO" in u or "BENEDITO" in u or "B BENTES" in u:
            return "Poço"
    return ""


def _decidir(hist: list[str], sede: str, fora_al: bool, validas: list[str]) -> tuple[str, str]:
    hist = sorted({h for h in hist if h in validas})
    if len(hist) == 1:
        return hist[0], "histórico (preservação)"
    if len(hist) > 1:
        if sede in hist:
            return sede, f"histórico em {', '.join(hist)} — vale a sede"
        return sede or hist[0], f"histórico em {', '.join(hist)} — sede fora delas, conferir"
    if sede:
        return sede, "empresa nova — endereço da sede"
    if fora_al:
        return A_DEFINIR, "sede fora de AL — exceção da minuta"
    return "", "sem endereço: conferir"


def distribuir(enderecos: pd.DataFrame, historico: pd.DataFrame | None, raizes: set[str] | None = None) -> pd.DataFrame:
    """enderecos: ENDERECOS_AL (cnpj, cnpj_basico, matriz, bairro, municipio).
    historico: propostas aceitas (cnpj_basico, Entidade, Unidade). Devolve uma linha por CNPJ raiz."""
    bairros, municipios = carregar_minuta()
    ceps = mapa_cep_bairro(enderecos, bairros)   # de todos os estabelecimentos, matriz e filial
    e = enderecos.copy()
    if "cep" not in e.columns:
        e["cep"] = ""
    e["cnpj_basico"] = e["cnpj_basico"].astype(str).str.zfill(8)
    e = e.sort_values(["cnpj_basico", "matriz"], ascending=[True, False]).drop_duplicates("cnpj_basico")
    hist = pd.DataFrame(columns=["cnpj_basico", "Entidade", "unidade"])
    if historico is not None and len(historico):
        h = historico.copy()
        h["cnpj_basico"] = h["cnpj_basico"].astype(str).str.zfill(8)
        h["unidade"] = [unidade_do_historico(a, b) for a, b in zip(h["Entidade"], h["Unidade"])]
        hist = h[h["unidade"] != ""][["cnpj_basico", "Entidade", "unidade"]]
    todas = set(e["cnpj_basico"]) | set(hist["cnpj_basico"])
    if raizes is not None:
        todas &= set(raizes) | set(hist["cnpj_basico"])
    e = e.set_index("cnpj_basico")
    hs = {k: g for k, g in hist.groupby("cnpj_basico")}
    linhas = []
    for r in sorted(todas):
        if r in e.index:
            mun, bai, matriz = e.at[r, "municipio"], e.at[r, "bairro"], e.at[r, "matriz"]
            sesi_s, senai_s, origem = unidade_pela_sede(mun, bai, bairros, municipios, e.at[r, "cep"], ceps)
            fora = matriz != "S"   # só filial em AL -> matriz fora do estado
            if fora:
                sesi_s, senai_s, origem = "", "", "matriz fora de AL (filial em " + str(mun).title() + ")"
        else:
            mun = bai = ""
            sesi_s = senai_s = ""
            origem, fora = "sem estabelecimento ativo em AL na Receita", True
        g = hs.get(r)
        h_sesi = list(g[g["Entidade"].str.upper() == "SESI"]["unidade"]) if g is not None else []
        h_senai = list(g[g["Entidade"].str.upper() == "SENAI"]["unidade"]) if g is not None else []
        u_sesi, m_sesi = _decidir(h_sesi, sesi_s, fora, UNIDADES_SESI)
        u_senai, m_senai = _decidir(h_senai, senai_s, fora, UNIDADES_SENAI)
        unidades = sorted({u for u in (u_sesi, u_senai) if u and u != A_DEFINIR})
        linhas.append({
            "cnpj_basico": r, "municipio_sede": str(mun).title(), "bairro_sede": str(bai).title(),
            "endereco_sede": origem,
            "historico_sesi": ", ".join(sorted(set(h_sesi))), "historico_senai": ", ".join(sorted(set(h_senai))),
            "unidade_sesi": u_sesi, "motivo_sesi": m_sesi, "unidade_senai": u_senai, "motivo_senai": m_senai,
            "unidades": " | ".join(unidades),
        })
    return pd.DataFrame(linhas)


ARQ_CARTEIRA = RAIZ / "data" / "processed" / "CARTEIRA_UNIDADES.csv"
COLS_CARTEIRA = ["unidade_sesi", "unidade_senai", "unidades"]   # motivos só no DETALHE (data/privado)


def carregar_carteira(df: pd.DataFrame, col_raiz: str = "cnpj_basico", caminho: Path = ARQ_CARTEIRA) -> pd.DataFrame:
    """Junta as colunas de carteira na base do painel. Sem o arquivo, cria as colunas vazias."""
    out = df.copy()
    if not Path(caminho).exists():
        for c in COLS_CARTEIRA:
            out[c] = ""
        return out
    c = pd.read_csv(caminho, dtype=str, encoding="utf-8-sig").fillna("")
    c = c.drop_duplicates("cnpj_basico").set_index("cnpj_basico")
    raiz = out[col_raiz].astype(str).str.zfill(8)
    for col in COLS_CARTEIRA:
        out[col] = raiz.map(c[col]).fillna("") if col in c else ""
    return out


def filtrar_por_unidade(df: pd.DataFrame, unidades: list[str]) -> pd.DataFrame:
    """Empresas cuja unidade responsável (SESI ou SENAI) está entre as escolhidas."""
    if not unidades or "unidades" not in df.columns:
        return df
    alvo = set(unidades)
    return df[df["unidades"].fillna("").map(lambda s: bool(alvo & {u.strip() for u in s.split("|") if u.strip()}))]
