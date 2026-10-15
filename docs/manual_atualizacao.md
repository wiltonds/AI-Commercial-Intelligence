# Manual de atualização dos dados

O que precisa ser baixado, onde colocar e o que rodar para o painel comercial ficar em dia.
A lista oficial das entradas está em [`config/entradas.yaml`](../config/entradas.yaml); o que cada
job lê e grava, em [mapa_do_sistema.md](mapa_do_sistema.md); o significado de cada coluna, em
[dicionario_dados.md](dicionario_dados.md).

Todos os comandos rodam **na pasta raiz do projeto**, no terminal (PowerShell), com o ambiente
Python do projeto ativo.

## Por onde começar: o que está vencido?

```
python jobs/checar_entradas.py
```

Mostra cada entrada com a data da última atualização e a situação
(**em dia**, **vence em N dias**, **VENCIDO**, **NUNCA REGISTRADO**). Para cada item que precisa
de atenção, diz **o que baixar, onde colocar e o que rodar**. Com `--detalhe`, mostra isso para
todas. A mesma informação aparece no painel, na página **🗓️ Rotina de Dados** (Modo técnico).

A data vem do log `data/processed/LOG_ATUALIZACOES.csv`, que cada job grava ao terminar — não da
data do arquivo no disco, que o Git altera a cada `pull`.

## As entradas

| Entrada | Quem fornece | O que baixar | Onde colocar | Frequência | Confidencial |
|---|---|---|---|---|---|
| Tabela DN da CNI | CNI (BI_Project) | `dim_cnae_AAAAMM.csv`, linhas `eh_cnae_industrial_dn = SIM` | `config/referencia/tabela_dn_cni.csv` | Quando a CNI revisar | Não |
| Receita Federal (CNPJ) | Receita (público) | `Estabelecimentos0..9`, `Empresas0..9`, **`Simples`**, `Municipios`, `Cnaes`, `Naturezas` (.zip) — [link](https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9) | Uma pasta local (ex.: `Downloads/receita_AAAAMM`) — ~6,5 GB, fora do projeto | Mensal | Não |
| Base Mestre | BI_Project | `BASE_MESTRE_COMERCIAL.csv` novo, quando gerado | `data/processed/` | Quando houver | Não |
| Propostas SESI/SENAI | Sistema comercial | Exportação completa de propostas (.xlsx), todos os status, desde 2018 | `data/privado/propostas.xlsx` | Mensal | **Sim** |
| Minuta de Carteirização | Política SESI/SENAI | Tabela bairro/município → unidade | `config/referencia/carteira_minuta.csv` | Quando a política mudar | Não |
| Colaboradores | Solução 360 | Exportação de empresas (CNPJ + contagem) | `data/privado/colaboradores.xlsx` | Trimestral | **Sim** |
| Contatos (robô) | Automático (BrasilAPI) | Nada | — | A cada 90 dias | **Sim** |
| Presença digital | Automático (Serper, precisa de chave) | Nada | — | Semestral | **Sim** |

> **Simples.zip** é o que permite tirar o **MEI optante** da base (regra comercial: MEI não é atendido;
> microempresa é). Sem ele, o job usa uma aproximação (Empresário Individual microempresa) e avisa no terminal.

### Colunas obrigatórias da exportação de propostas

`CNPJ`, `Razão Social`, `Entidade` (SESI / SENAI / IEL / FIEA), `Categoria`, `Unidade`,
`Porte` (porte FIEA, ex. `2. Médio`), `Porte Receita`, `Status` (só `Aceita` conta como venda),
`Emissão`, `Aprovação`, `Valor total`, `Natureza Produto`.

Se o sistema mudar o nome de alguma coluna, o job para com erro dizendo qual coluna faltou — ajuste
a exportação ou o código em `src/tools/relacionamento.py`.

## Rotina mensal (nesta ordem)

A ordem importa: o relacionamento é gravado **dentro** das bases, então tudo o que recria as bases
(Receita, BI_Project) vem **antes** das propostas; carteira e prioridade vêm **depois** das propostas.

**1. Receita** (competência nova, zips numa pasta local):
```
python jobs/carregar_base_ampliada.py --pasta "C:/caminho/receita_AAAAMM"
python jobs/incorporar_industrias_novas.py --competencia AAAA-MM
python jobs/extrair_enderecos.py --pasta "C:/caminho/receita_AAAAMM"
```
Gera as não indústrias (todos os portes, sem MEI), coloca as indústrias novas na Base Mestre, a
lista `data/contatos/INDUSTRIAS_NOVAS_AAAAMM.xlsx` para o comercial e o endereço de cada empresa.
O `carregar_base_ampliada` também aceita `--mes AAAA-MM` para tentar baixar os zips sozinho.
Cada um leva de 10 a 30 minutos (lê ~6 GB).

**2. Propostas** (exportação nova em `data/privado/propostas.xlsx`):
```
python jobs/atualizar_relacionamento.py --arquivo data/privado/propostas.xlsx
```

**3. Carteira por unidade e prioridade do Mercado:**
```
python jobs/distribuir_carteira.py --historico data/privado/propostas.xlsx
python jobs/calcular_potencial.py
```
O `distribuir_carteira` mostra no final quantas empresas ficaram em "conferir" (bairro da Receita
que não bate com a minuta nem pelo CEP) — veja o detalhe em `data/privado/CARTEIRA_UNIDADES_DETALHE.csv`.

**4. Enriquecimento** (só quando `checar_entradas` indicar):
```
python jobs/enriquecer_contatos.py --limite 14000 --delay 1.5
python jobs/segunda_passada_contatos.py
python jobs/importar_colaboradores.py --arquivo data/privado/colaboradores.xlsx
python jobs/mapear_hubs.py
```

**5. Publicar:**
```
.\jobs\publicar_dados.ps1
```
Envia os arquivos de `data/processed/` para o GitHub e prepara o backup de `data/privado` e
`data/contatos` para o Teams/SharePoint (abre a pasta `Downloads\PARA_O_TEAMS` — arraste o .zip).
O painel online percebe os arquivos novos sozinho em 1–3 minutos; **não precisa reiniciar o app**.

**6. Conferir:** abra o painel e veja se os números das páginas Clientes e Mercado fazem sentido
com o que o terminal mostrou nos passos anteriores.

Se o BI_Project gerar uma **Base Mestre nova**, substitua o arquivo e repita
`incorporar_industrias_novas`, o passo 2 e o passo 3 — a versão nova não traz o relacionamento das
propostas nem as indústrias incorporadas.

## O que vai para o Git e o que não vai

O repositório e o painel são **públicos**. Regra: vai para o Git o que alimenta o painel e **não
identifica pessoa nem expõe valor comercial**. A razão social de Empresário Individual vem da Receita
com o CPF no fim — os jobs **retiram o CPF** antes de gravar qualquer arquivo público
(`src/tools/lgpd.py`).

| Vai para o Git (e para o painel online) | Fica só na máquina local (backup no Teams) |
|---|---|
| `data/processed/BASE_MESTRE_COMERCIAL.csv` e `BASE_AMPLIADA_AL.csv` (sem contato, sem CPF) | `data/privado/` — propostas, valores e linhas compradas por empresa, detalhe da carteira (histórico de unidade), clientes fora da base, colaboradores exatos |
| `CARTEIRA_UNIDADES.csv` (só a unidade, sem motivo nem histórico) | `data/contatos/` — contatos do robô e da Receita, endereços (`ENDERECOS_AL.csv`), listas para o comercial |
| `POTENCIAL_MERCADO.csv` (sem bairro de Empresário Individual), `MEI_BASE_MESTRE.csv` | `.env` (chaves de API) |
| `PORTE_FIEA.csv`, `PRODUTOS_RANKING.csv`, `ATENDIMENTO_POR_ANO.csv`, `VISAO_360.csv` (agregados) | Zips da Receita (grandes demais e públicos — baixe de novo quando precisar) |
| `LOG_ATUALIZACOES.csv`, `config/` | |

A lista exata do que é publicado está no topo de `jobs/publicar_dados.ps1`. Para incluir um arquivo
novo no painel, acrescente-o ali — nunca um arquivo de `data/privado` ou `data/contatos`.

## Regras editáveis (sem mexer em código)

| Arquivo | O que controla |
|---|---|
| `config/referencia/relacionamento.yaml` | Meses para "cliente ativo" (24), status que contam como venda, entidades |
| `config/referencia/filtro_nao_industria.yaml` | Quais naturezas/CNAEs de não indústria saem da base (condomínios, partidos...) |
| `config/referencia/tabela_dn_cni.csv` | O que é indústria |
| `config/referencia/carteira_minuta.csv` | Bairro de Maceió / município → unidade SESI e SENAI |
| `config/referencia/linhas_negocio.yaml` | Linhas de negócio da Visão 360 (SSI, EB, STI, EP) |
| `config/entradas.yaml` | A lista de entradas e as frequências esperadas |

## Quando algo dá errado

| Sintoma | O que fazer |
|---|---|
| Job para com "faltam as colunas [...]" | A exportação mudou de formato — confira os nomes das colunas acima |
| Clientes da não indústria aparecem com "0 compram hoje" | O passo 1 rodou depois do passo 2: rode de novo o `atualizar_relacionamento` |
| Muitas empresas em "conferir" na carteira | Bairros novos/escritos diferente na Receita: veja `data/privado/CARTEIRA_UNIDADES_DETALHE.csv` e acrescente a grafia em `ALIAS_BAIRRO` (`src/tools/carteira.py`) |
| Painel online fora do ar ("Oh no.") | share.streamlit.io → app → *Manage app*: leia o log; *Reboot app* costuma resolver travamento de deploy |
| Painel online com número antigo | Confira se o `publicar_dados.ps1` terminou com "publicado"; o app recarrega em 1–3 minutos |
| Depois de mudar código | `python -m pytest` — todos os testes precisam passar antes do push |
