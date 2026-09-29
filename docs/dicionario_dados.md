# Dicionário de Dados — BASE_MESTRE_COMERCIAL.csv

Complementa [arquitetura_dados.md](arquitetura_dados.md). Perfil real da base atual (14.903 linhas), coluna a coluna, para desenhar o schema do Data Warehouse. Campos marcados com ⚠️ têm algum problema de qualidade ou redundância — ver a seção final antes de copiar o schema 1:1.

## Identificação

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `cnpj` | texto (14 díg.) | CNPJ completo do estabelecimento — chave da linha |
| `CNPJ_NORMALIZADO` | texto (14 díg.) | ⚠️ Idem a `cnpj`, já com zero-padding — redundante |
| `CNPJ_BASICO` | texto (8 díg.) | 8 primeiros dígitos do CNPJ — a raiz usada na consolidação (Etapa 1.3) |
| `razao_social` | texto | Razão social na Receita Federal |
| `situacao_atual` | texto | Situação cadastral — hoje só tem o valor `ATIVA` (base já filtrada) |

## Classificação e localização

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `SETOR` | texto | Sempre `INDÚSTRIA`. ⚠️ acentuação corrompida no arquivo fonte |
| `CNAE PRIMARIO` | texto | Descrição textual do CNAE principal |
| `CNAE_DIVISAO` | texto | ⚠️ Não confiável — só assume os valores 0 ou 10 em toda a base. Usar `SEBRAE_cnae_divisao` como fonte de verdade |
| `EH_INDUSTRIA` | booleano | Sempre `True` — resultado já aplicado da curadoria (Etapa 1.2), não recalculado aqui |
| `Porte` | texto | `MICRO EMPRESA` / `PEQUENO PORTE` / `DEMAIS` — classificação Receita/SEBRAE, não distingue MEI |
| `Municipio` | texto | Município de Alagoas |

## Relacionamento SESI/SENAI

Desde 09/2026 as colunas de cliente vêm da **exportação de propostas** (`jobs/atualizar_relacionamento.py`, regras em `config/referencia/relacionamento.yaml`): cliente = pelo menos uma proposta com status `Aceita` da entidade. As colunas valem para a **empresa** (CNPJ raiz): se qualquer unidade comprou, todas as linhas da raiz ficam marcadas — exceto `CNPJ_ATENDIDO`, que é da unidade.

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `TEM_SESI` / `TEM_SENAI` | booleano | A empresa tem ao menos uma proposta aceita da entidade (qualquer data desde 2018) |
| `TEM_SESI_SENAI` | booleano | `TEM_SESI AND TEM_SENAI` |
| `STATUS_RELACIONAMENTO` | texto | `SEM RELACIONAMENTO` / `SOMENTE SESI` / `SOMENTE SENAI` / `SESI + SENAI` |
| `SITUACAO_CLIENTE` | texto | `Ativo` (última compra nos últimos 24 meses) / `Inativo` (comprou antes disso) / `Sem compra` |
| `ULTIMA_COMPRA`, `ULTIMA_COMPRA_SESI`, `ULTIMA_COMPRA_SENAI` | data | Data da última proposta aceita (aprovação; emissão se não houver) |
| `PRIMEIRA_COMPRA` | data | Primeira proposta aceita |
| `CNPJ_ATENDIDO` | Sim/Não | **Esta unidade** (CNPJ de 14 dígitos) teve proposta aceita |
| `SESI` / `SENAI` | texto | ⚠️ Legado das planilhas manuais (CNPJ de match) — não são mais atualizados; use `TEM_SESI`/`TEM_SENAI` |
| `ORIGEM_REGISTRO` | texto | `Base Mestre (BI_Project)` ou `Receita AAAA-MM (incorporada)` para indústrias acrescentadas por `jobs/incorporar_industrias_novas.py` |

⚠️ O histórico do SESI no sistema de propostas começa em 2024; compras SESI anteriores não aparecem.

## Enriquecimento SEBRAE

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `SEBRAE_cnpj` | texto | CNPJ do lado SEBRAE do cruzamento — 9 registros sem correspondência (nulo) |
| `SEBRAE_razao_social`, `SEBRAE_situacao_atual`, `SEBRAE_SETOR`, `SEBRAE_CNAE PRIMARIO`, `SEBRAE_Porte`, `SEBRAE_Municipio` | texto | Espelham os campos equivalentes sem prefixo, do lado SEBRAE — quase sempre idênticos |
| `SEBRAE_SESI`, `SEBRAE_SENAI` | texto | ⚠️ Idênticas a `SESI`/`SENAI` — sobra de merge |
| `SEBRAE_cnae_codigo_recuperado` | texto | Código CNAE no formato oficial (`0000-0/00`) |
| `SEBRAE_cnae_norm` | texto | Código CNAE normalizado numérico |
| `SEBRAE_cnae_divisao` | texto | ✅ Divisão CNAE confiável (2 dígitos) — usar esta, não `CNAE_DIVISAO` |
| `SEBRAE_secao` | texto | Seção CNAE (letra, ex. `C`, `F`) |
| `SEBRAE_setor`, `SEBRAE_subsetor` | texto | Setor/subsetor econômico (nomenclatura SEBRAE) |
| `SEBRAE_e_industria` | booleano | Classificação de indústria pela régua do SEBRAE (pode divergir de `EH_INDUSTRIA`) |
| `SEBRAE_auditoria` | booleano | Sempre `False` na base atual |
| `SEBRAE_elegivel_sebrae`, `SEBRAE_ELEGIVEL` | texto (`SIM`/`NAO`) | ⚠️ colunas idênticas (case diferente) |
| `SEBRAE_oportunidade_comercial`, `SEBRAE_OPORTUNIDADE_ORIGINAL` | texto | ⚠️ colunas idênticas |
| `ENCONTRADO_SEBRAE` | booleano | Houve correspondência com a base SEBRAE (9 sem match) |
| `STATUS_SEBRAE`, `SEBRAE_OPORTUNIDADE`, `OPORTUNIDADE_SEBRAE` | texto | ⚠️ três colunas idênticas: `NÃO ATENDIDA` / `FORA DO ESCOPO SEBRAE` / `SEM INFORMAÇÃO` |

## Sinalizadores de oportunidade comercial

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `OPORTUNIDADE_SESI`, `OPORTUNIDADE_SENAI` | texto (`SIM`/`NÃO`) | Espelham o inverso de `TEM_SESI`/`TEM_SENAI` |
| `OPORTUNIDADE_GERAL` | texto | `PROSPECT` / `CLIENTE` |
| `OPORTUNIDADE_CROSS_SELL` | texto | `SENAI` / `SESI` / `NÃO` — qual produto oferecer a quem já é cliente do outro |

## Computados no dashboard (não persistidos no CSV — `app.py`, recalculados a cada carga)

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `POSSUI_SESI`, `POSSUI_SENAI`, `POSSUI_SESI_SENAI`, `POSSUI_SEBRAE` | booleano | Recalculados a partir de `TEM_SESI`/`TEM_SENAI`/colunas `SEBRAE_*`, com parsing tolerante (`TRUE`/`SIM`/`1`/...) |
| `STATUS_RELACIONAMENTO_REAL` | texto | Recalculado a partir de `POSSUI_SESI`/`POSSUI_SENAI` — não usa `STATUS_RELACIONAMENTO` do CSV |

## Computados na consolidação por CNPJ raiz (não persistidos — `src/tools/cnpj_raiz.py`)

| Campo | Tipo | Descrição |
| --- | --- | --- |
| `QTD_ESTABELECIMENTOS` | inteiro | Número de CNPJ completos sob a mesma raiz |
| `QTD_FILIAIS` | inteiro | `QTD_ESTABELECIMENTOS - 1` |
| `TEM_FILIAL` | booleano | `QTD_FILIAIS > 0` |
| `CLIENTE_SESI_SENAI` | booleano | `POSSUI_SESI OR POSSUI_SENAI`, herdado de qualquer estabelecimento do grupo |
| `TIPO_EMPRESA` | texto | `Unidade única` / `Multiestabelecimento` |
| `Municipios` | texto | Lista dos municípios distintos entre os estabelecimentos do grupo |

## Pontos de atenção para o schema do DW

- Encoding corrompido em campos de texto acentuado (`SETOR`, `SEBRAE_SETOR`, `STATUS_SEBRAE` e outros aparecem com carácter inválido no lugar de Ú/Ã/Ç) — ajustar o charset de leitura na ingestão.
- `CNAE_DIVISAO` da base principal não é confiável (só 0 ou 10); usar `SEBRAE_cnae_divisao`.
- 6 pares/trios de colunas 100% redundantes por causa de merges sucessivos (marcados ⚠️ acima) — escolher uma versão canônica por grupo e descartar o resto no schema do DW.
- `SESI`/`SENAI` guardam um CNPJ de match, não um booleano — a flag real é `TEM_SESI`/`TEM_SENAI`.
- Nenhuma coluna distingue CNPJ optante do MEI porque a exclusão já acontece antes desta base existir: raiz com `opcao_mei = S` (cruzado contra o arquivo Simples da Receita) sai do universo em `construir_base_mestre.py`, fora deste repositório. Não é uma lacuna — é uma regra já aplicada a montante.
- 9 registros (de 14.903) não têm correspondência na base SEBRAE — todos os campos `SEBRAE_*` vêm nulos para eles.

## Outros arquivos do painel

| Arquivo | Uma linha por | Gerado por | Principais colunas |
| --- | --- | --- | --- |
| `data/processed/BASE_AMPLIADA_AL.csv` | Empresa (raiz) fora da Base Mestre, média/grande, ativa em AL | `carregar_base_ampliada.py` | `Tipo` (Não indústria / Indústria fora da Base Mestre), `Porte`, `porte_fiea`, `natureza`, `cnae_principal`, `POSSUI_SESI`, `POSSUI_SENAI`, `SITUACAO_CLIENTE`, `ULTIMA_COMPRA` |
| `data/processed/PORTE_FIEA.csv` | Empresa (raiz) | `atualizar_relacionamento.py` | `porte_fiea` mais recente informado nas propostas |
| `data/processed/PRODUTOS_RANKING.csv` | Produto × entidade × (na base industrial?) | `atualizar_relacionamento.py` | `empresas`, `empresas_recentes` (24 meses), `propostas`, `valor` — agregado |
| `data/processed/ATENDIMENTO_POR_ANO.csv` | Ano × entidade | `atualizar_relacionamento.py` | `empresas` distintas atendidas — agregado |
| `data/processed/LOG_ATUALIZACOES.csv` | Execução de job | todos os jobs | `entrada`, `data`, `resumo` — usado por `checar_entradas.py` |
| `data/contatos/CONTATOS_EMPRESAS.csv` 🔒 | Empresa (raiz) | `enriquecer_contatos.py`, `segunda_passada_contatos.py`, `enriquecer_digital.py` | telefones, `whatsapp_provavel`, `email`, `decisor`, `confianca`, `site`, `instagram`, `email_site` |
| `data/contatos/CONTATOS_RECEITA.csv` 🔒 | Empresa (raiz) | `carregar_base_ampliada.py` | telefone e e-mail cadastrais da Receita |
| `data/privado/RELACIONAMENTO_POR_EMPRESA.csv` 🔒 | Empresa (raiz) que comprou | `atualizar_relacionamento.py` | `VALOR_ACEITO_TOTAL`, `QTD_PROPOSTAS_ACEITAS`, `LINHAS_COMPRADAS`, `QTD_CNPJS_ATENDIDOS` |

🔒 = confidencial, fora do Git por padrão. O que atualiza cada arquivo e em que ordem: [manual_atualizacao.md](manual_atualizacao.md).
