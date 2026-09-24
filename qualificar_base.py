"""
qualificar_base.py — Qualifica a Base Mestre inteira para subir no CRM.

Roda o pipeline comercial já existente (LeadResearch → DataQuality → SDR →
OpportunityEngine → Supervisor) sobre TODAS as empresas e exporta uma tabela
de uma linha por empresa, pronta para o consultor e para importação no CRM.

NÃO reescreve lógica: reaproveita src/pipeline.py inteiro. A única regra nova
é o filtro PJ (decisão de escopo: projeto é PJ; produto clínico PF do SESI
não entra na recomendação de CNPJ).

Uso:
    python qualificar_base.py                 # base inteira
    python qualificar_base.py --limite 500    # amostra p/ teste
    python qualificar_base.py --min-prioridade 40  # só leads que valem a pena

Roda LOCAL — a base tem CNPJ e não deve sair da máquina.
"""

import argparse
import pandas as pd
from pathlib import Path

from src.pipeline import CommercialPipeline
from src.tools.company_data import CompanyDataTool
from src.tools.cnpj_raiz import consolidar_por_cnpj_raiz

SAIDA = Path(__file__).resolve().parent / "data" / "processed" / "BASE_QUALIFICADA_CRM.csv"

# Rótulo de honestidade: esta base é uma PRIMEIRA LEITURA direcional (CNAE +
# porte), não uma previsão validada por consumo. Vai em cada linha e no topo
# da tela, para o consultor saber o peso exato do que está lendo.
LEITURA = "DIRECIONAL — 1ª leitura por CNAE+porte; não validada por consumo"

# ------------------------------------------------------------------
# Filtro PJ — Naturezas SESI que são PF/clínico particular e NÃO
# entram no match de CNPJ (decisão de escopo confirmada).
# Núcleo ocupacional PJ do SSI (fica): higiene ocupacional, medicina
# do trabalho, consultas ocupacionais, documentação técnica-legal,
# segurança do trabalho. O resto dos "EXAMES E PROCEDIMENTOS" é PF.
# ------------------------------------------------------------------
NATUREZAS_PF_FORA = (
    "EXAMES E PROCEDIMENTOS - LABORATORIAIS",
    "EXAMES E PROCEDIMENTOS - ODONTOLOGIA",
    "EXAMES E PROCEDIMENTOS - ULTRASSONOGRAFIA",
    "EXAMES E PROCEDIMENTOS - RESSONANCIA",
    "EXAMES E PROCEDIMENTOS - RAIO X",
    "EXAMES E PROCEDIMENTOS - TOMOGRAFIA",
    "EXAMES E PROCEDIMENTOS - OFTALMOLOGIA",
    "EXAMES E PROCEDIMENTOS - GINECOLOGIA",
    "EXAMES E PROCEDIMENTOS - FONOAUDIOLOGIA",
    "EXAMES E PROCEDIMENTOS - OTORRINOLARINGOLOGIA",
    "EXAMES E PROCEDIMENTOS - DERMATOLOGIA",
    "EXAMES E PROCEDIMENTOS - UROLOGIA",
    "EXAMES E PROCEDIMENTOS - PNEUMOLOGIA",
    "EXAMES E PROCEDIMENTOS - GRÁFICOS",
    "EXAMES E PROCEDIMENTOS - APARELHOS ODONTOLOGICOS",
    "ODONTOLOGIA",
    "TEATRO SOCIOEDUCATIVO",
    "ESPORTES",
    "EVENTOS ESPORTIVOS",
    "REABILITAÇÃO",
    "NUTRIÇÃO",
    "VACINAS",
    "ENSINO FUNDAMENTAL",
    "ENSINO MÉDIO",
    "EDUCAÇÃO BÁSICA REGULAR",
    "MODALIDADE EDUCAÇÃO DE JOVENS E ADULTOS",
    "EDUCAÇÃO CONTINUADA EM EDUCAÇÃO",
)


def _e_pf(caminho_catalogo: str) -> bool:
    alvo = (caminho_catalogo or "").upper()
    return any(nat in alvo for nat in NATUREZAS_PF_FORA)


def qualificar(limite: int | None = None, min_prioridade: int = 0) -> pd.DataFrame:
    tool = CompanyDataTool()
    base = tool._load()                       # DataFrame da base mestre
    base = consolidar_por_cnpj_raiz(base)     # 1 linha por empresa (não por filial)

    if limite:
        base = base.head(limite)

    pipeline = CommercialPipeline()
    linhas = []

    for cnpj in base["cnpj"]:
        resultado = pipeline.executar(cnpj)
        if resultado is None:
            continue

        lead = resultado["lead"]
        prioridade = resultado["qualificacao"]["score"]
        if prioridade < min_prioridade:
            continue

        qualidade = resultado["qualidade_dados"]["score"]
        oportunidades = resultado["oportunidades"]   # já é lista de Opportunity

        # filtro PJ: descarta recomendações de produto PF/clínico
        oportunidades = [o for o in oportunidades if not _e_pf(o.caminho_catalogo)]

        # tratamento: se já é cliente => CROSS-SELL; senão => AQUISIÇÃO
        if lead.tem_sesi or lead.tem_senai:
            tratamento = "CROSS-SELL"
        else:
            tratamento = "AQUISIÇÃO (inferência)"

        top = oportunidades[:3]   # 3 melhores produtos aprovados pelo Supervisor

        linhas.append({
            "leitura": LEITURA,
            "cnpj": lead.cnpj,
            "razao_social": lead.razao_social,
            "municipio": lead.municipio,
            "porte": lead.porte,
            "setor": lead.setor,
            "status_relacionamento": lead.status_relacionamento,
            "tratamento": tratamento,
            "prioridade_comercial": prioridade,
            "qualidade_dados": qualidade,
            "sebrae_elegivel": bool(lead.sebrae_elegivel),
            "n_recomendacoes": len(oportunidades),
            "top_produtos": " | ".join(
                f"{o.solucao} [{o.area}, fit {o.score_fit}]" for o in top
            ),
            "top_codigos": " | ".join(str(o.produto_codigo) for o in top),
            "motivo": top[0].motivo if top else "Sem recomendação aprovada (PJ).",
        })

    df = pd.DataFrame(linhas)
    if len(df):
        df = df.sort_values(
            ["tratamento", "prioridade_comercial"], ascending=[True, False]
        )
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=None)
    ap.add_argument("--min-prioridade", type=int, default=0)
    args = ap.parse_args()

    print("Qualificando base... (roda o pipeline por empresa; pode demorar)")
    df = qualificar(limite=args.limite, min_prioridade=args.min_prioridade)

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SAIDA, index=False, encoding="utf-8-sig")

    print(f"\nEmpresas qualificadas: {len(df):,}")
    if len(df):
        print(df["tratamento"].value_counts().to_string())
        print(f"\nArquivo: {SAIDA}")
        print("Colunas prontas p/ importar no CRM (uma linha por empresa).")
        print(f"\n[LEITURA] {LEITURA}")
        print("Trate como ponto de partida para o consultor, não como previsão fechada.")


if __name__ == "__main__":
    main()
