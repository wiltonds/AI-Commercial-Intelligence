# Tabelas de referência

`tabela_dn_cni.csv` — Tabela DN da CNI (1.298 CNAEs que o Sistema conta como
indústria). Copie do `BI_Project` para cá. Formato: primeira coluna com o
código CNAE (aceita `4520-0/01`, `4520001` ou `4520001.0`); as demais colunas
são ignoradas.

Sem este arquivo, `jobs/carregar_base_ampliada.py` usa uma aproximação: os
CNAEs principais que já aparecem na Base Mestre (que foi montada com a
própria Tabela DN). O terminal avisa qual régua foi usada.
