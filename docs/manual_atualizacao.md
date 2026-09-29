# Manual de atualização dos dados

O que precisa ser baixado, onde colocar e o que rodar para o painel comercial
ficar em dia. A lista oficial das entradas está em
[`config/entradas.yaml`](../config/entradas.yaml); o significado de cada coluna,
em [dicionario_dados.md](dicionario_dados.md).

## Por onde começar: o que está vencido?

```
python jobs/checar_entradas.py
```

Mostra cada entrada com a data da última atualização e a situação
(**em dia**, **vence em N dias**, **VENCIDO**, **NUNCA REGISTRADO**). Para cada
item que precisa de atenção, diz **o que baixar, onde colocar e o que rodar**.
Com `--detalhe`, mostra isso para todas as entradas.

A data vem do log `data/processed/LOG_ATUALIZACOES.csv`, que cada job grava ao
terminar — não da data do arquivo no disco, que o Git altera a cada `pull`.

## As entradas

| # | Entrada | Quem fornece | O que baixar | Onde colocar | Frequência | Confidencial |
|---|---|---|---|---|---|---|
| 0 | Tabela DN da CNI | CNI (BI_Project) | `dim_cnae_AAAAMM.csv`, linhas `eh_cnae_industrial_dn = SIM` | `config/referencia/tabela_dn_cni.csv` | Quando a CNI revisar | Não |
| 1 | Receita Federal (CNPJ) | Receita (público) | `Estabelecimentos0..9`, `Empresas0..9`, `Municipios`, `Cnaes`, `Naturezas` (.zip) | Pasta local (ex.: `BI_Project/downloads_AAAAMM`) | Mensal | Não |
| 1 | Base Mestre | BI_Project | `BASE_MESTRE_COMERCIAL.csv` novo, quando gerado | `data/processed/` | Quando houver | Não |
| 2 | Propostas SESI/SENAI | Sistema comercial | Exportação completa de propostas (.xlsx), todos os status, desde 2018 | `data/privado/propostas.xlsx` | Mensal | **Sim** |
| 3 | Contatos (robô) | Automático (BrasilAPI) | Nada | — | A cada 90 dias | **Sim** |
| 4 | Presença digital | Automático (Serper, precisa de chave) | Nada | — | Semestral | **Sim** |

### Colunas obrigatórias da exportação de propostas

`CNPJ`, `Razão Social`, `Entidade` (SESI / SENAI / IEL / FIEA), `Categoria`,
`Porte` (porte FIEA, ex. `2. Médio`), `Porte Receita`, `Status` (só `Aceita`
conta como venda), `Emissão`, `Aprovação`, `Valor total`, `Natureza Produto`.

Se o sistema mudar o nome de alguma coluna, o job para com erro dizendo qual
coluna faltou — ajuste a exportação ou o código em `src/tools/relacionamento.py`.

## Rotina mensal (nesta ordem)

A ordem importa: o relacionamento é gravado **dentro** da Base Mestre, então
tudo o que muda a base (Receita, BI_Project) vem antes das propostas.

1. **Receita** (competência nova):
   ```
   python jobs/carregar_base_ampliada.py --pasta "<pasta dos zips>" --mes AAAA-MM
   python jobs/incorporar_industrias_novas.py --competencia AAAA-MM
   ```
   Gera as não indústrias, coloca as indústrias novas na Base Mestre e a lista
   `data/contatos/INDUSTRIAS_NOVAS_AAAAMM.xlsx` para o comercial.
2. **Propostas** (exportação nova em `data/privado/propostas.xlsx`):
   ```
   python jobs/atualizar_relacionamento.py --arquivo data/privado/propostas.xlsx
   ```
3. **Contatos** (só quando `checar_entradas` indicar):
   ```
   python jobs/enriquecer_contatos.py --limite 14000 --delay 1.5
   python jobs/segunda_passada_contatos.py
   ```
4. **Publicar**:
   ```
   .\jobs\publicar_dados.ps1
   ```
   e **Reboot app** no Streamlit.

Se o BI_Project gerar uma **Base Mestre nova**, substitua o arquivo e repita os
passos 1 (só o `incorporar_industrias_novas`) e 2 — a versão nova não traz o
relacionamento das propostas nem as indústrias incorporadas.

## O que vai para o Git e o que não vai

O repositório é público. Regra: vai para o Git o que alimenta o painel e não
identifica pessoa nem expõe valor comercial.

| Vai para o Git (e para o painel online) | Fica só na máquina local |
|---|---|
| `data/processed/BASE_MESTRE_COMERCIAL.csv` (com cliente, situação e última compra) | `data/privado/` — exportação de propostas, valores e linhas compradas por empresa, clientes fora da base |
| `data/processed/BASE_AMPLIADA_AL.csv` (não indústrias, sem contatos) | `data/contatos/` — por padrão; os arquivos de contato só sobem quando publicados de propósito (`add -f`) |
| `PORTE_FIEA.csv`, `PRODUTOS_RANKING.csv`, `ATENDIMENTO_POR_ANO.csv` (agregados) | Planilhas geradas para o comercial (`INDUSTRIAS_NOVAS_*.xlsx`) |
| `LOG_ATUALIZACOES.csv` | |
| `config/` (Tabela DN, filtros, regras de cliente) | |

## Regras editáveis (sem mexer em código)

| Arquivo | O que controla |
|---|---|
| `config/referencia/relacionamento.yaml` | Meses para "cliente ativo" (24), status que contam como venda, entidades |
| `config/referencia/filtro_nao_industria.yaml` | Quais naturezas/CNAEs de não indústria saem da base (condomínios, partidos...) |
| `config/referencia/tabela_dn_cni.csv` | O que é indústria |
| `config/entradas.yaml` | Esta lista de entradas e as frequências esperadas |
