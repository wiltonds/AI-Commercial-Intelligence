"""
segunda_passada_contatos.py — Melhora o que o robô já coletou, sem nova consulta.

  * celular antigo (8 dígitos, cadastrado antes do nono dígito) ganha o 9
    e passa para a coluna WhatsApp
  * firma individual sem sócio: o titular (nome na razão social) vira o
    responsável, com cargo "Titular (firma individual)"

Uso:  python jobs/segunda_passada_contatos.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tools.contatos import ARQ_CONTATOS, COLUNAS, carregar_contatos, segunda_passada  # noqa: E402

antes = carregar_contatos(receita=None)
depois = segunda_passada(antes)
depois.reindex(columns=COLUNAS).fillna("").to_csv(ARQ_CONTATOS, index=False, encoding="utf-8-sig")
print(f"Empresas: {len(depois):,}")
print(f"WhatsApp provável: {(antes['whatsapp_provavel'] != '').sum():,} -> {(depois['whatsapp_provavel'] != '').sum():,}")
print(f"Com responsável:   {(antes['decisor'] != '').sum():,} -> {(depois['decisor'] != '').sum():,}")
print("Confiança:")
print(depois["confianca"].value_counts().to_string())
