# Inteligência Comercial SESI | SENAI — Alagoas

Painel que mostra ao time comercial **quem já é cliente, quem procurar e por onde começar**, para
indústrias e não indústrias de Alagoas, separado pela unidade SESI/SENAI responsável por cada empresa.

- **Painel online:** https://inteligenciacomerical.streamlit.app
- **Código:** este repositório (público — leia [O que é público e o que não é](#o-que-é-público-e-o-que-não-é))

> **Comece por aqui.** Este arquivo explica o que o projeto faz, de onde vêm os dados, quais regras
> são aplicadas e onde mudar cada coisa. O passo a passo de atualização está em
> [docs/manual_atualizacao.md](docs/manual_atualizacao.md) e o mapa completo (fonte → job → arquivo →
> página) em [docs/mapa_do_sistema.md](docs/mapa_do_sistema.md).

---

## O que o painel responde

As duas primeiras páginas são para o consultor comercial. As outras ficam no menu ou atrás do botão
**Modo técnico**.

| Página | Pergunta que responde |
|---|---|
| 👥 **Clientes** | Quem já comprou de SESI ou SENAI? Quem parou de comprar (para recuperar)? Quem compra de uma casa só (para oferecer a outra)? |
| 🎯 **Mercado — Potencial** | Das empresas que **nunca compraram**, quais se parecem mais com nossos clientes? Por quê? Em qual unidade? |
| 📊 Visão Geral | Tamanho do mercado industrial e a cobertura SESI/SENAI |
| 📈 Share & Relacionamento | Quanto do mercado já atendemos, produtos mais vendidos, atendimento por ano |
| 🏛️ SESI \| SENAI | Oportunidades por linha de negócio de cada casa |
| 🔗 Canais e Conexões | Escritórios e grupos que conectam muitas empresas de uma vez |
| 🔎 Explorador de Empresas | Busca de qualquer empresa, com contato (só na máquina local) e cartão "Visão 360" |
| 🎯 Base Qualificada (CRM) | Produto sugerido por empresa, para subir no CRM ([motor de recomendação](docs/motor_de_recomendacao.md)) |
| 🗓️ Rotina de Dados *(técnico)* | O que está em dia, vencido ou faltando atualizar |

Em **Clientes** e **Mercado**, a primeira escolha é **🏭 Indústria** ou **🏪 Não indústria**; depois vêm
os filtros (unidade SESI, unidade SENAI, município, bairro, atividade, porte, busca por nome/CNPJ).

---

## Como os dados chegam ao painel

```
 FONTES (de fora)                      JOBS (scripts em jobs/)               ARQUIVOS (data/processed/)          PAINEL
 ───────────────────────────────────   ─────────────────────────────────    ────────────────────────────────   ───────────────
 Receita Federal (zips mensais) ──┬──► carregar_base_ampliada.py ────────►  BASE_AMPLIADA_AL.csv, MEI_*.csv ─┐
                                  ├──► incorporar_industrias_novas.py ───►  BASE_MESTRE_COMERCIAL.csv ───────┤
                                  └──► extrair_enderecos.py ─────────────►  (data/contatos/ENDERECOS_AL.csv) ┤
 Base Mestre (BI_Project / FIEA) ────► (substitui o arquivo)                                                 │
 Propostas SESI/SENAI (export) ──────► atualizar_relacionamento.py ──────►  cliente, situação, última       ├─► app.py
                                                                            compra (dentro das bases),       │   (Streamlit)
                                                                            VISAO_360.csv, PORTE_FIEA.csv... │
 Minuta de Carteirização ────────────► distribuir_carteira.py ───────────►  CARTEIRA_UNIDADES.csv ───────────┤
 (config/referencia)                   calcular_potencial.py ────────────►  POTENCIAL_MERCADO.csv ───────────┤
 BrasilAPI / Serper (robôs) ─────────► enriquecer_contatos.py / _digital ►  (data/contatos/ — só local) ─────┘
                                                                                     │
                                       publicar_dados.ps1 ── leva data/processed ao GitHub ──► painel online
```

Cada job tem, no topo do arquivo, um texto explicando **o que lê, o que grava e como rodar**.
Todos gravam a data em que rodaram em `data/processed/LOG_ATUALIZACOES.csv` — é por ali que
`python jobs/checar_entradas.py` e a página **Rotina de Dados** sabem o que está vencido.

---

## Bases de dados usadas

| Base | De onde vem | Onde fica | Atualização | Confidencial? |
|---|---|---|---|---|
| **Cadastro de CNPJ** (Estabelecimentos, Empresas, Simples, tabelas de códigos) | Receita Federal — dados abertos ([link](https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9)) | Pasta local de zips (~6,5 GB), fora do repositório | Mensal | Não (público) |
| **Base Mestre de indústrias** | BI_Project (FIEA) | `data/processed/BASE_MESTRE_COMERCIAL.csv` | Quando o BI_Project gerar | Não |
| **Tabela DN da CNI** (o que é indústria) | CNI, via BI_Project | `config/referencia/tabela_dn_cni.csv` | Quando a CNI revisar | Não |
| **Propostas SESI/SENAI** | Sistema comercial (exportação completa, todos os status, desde 2018) | `data/privado/propostas.xlsx` | Mensal | **Sim** |
| **Minuta de Carteirização** (bairro/município → unidade) | Política de carteirização SESI/SENAI | `config/referencia/carteira_minuta.csv` | Quando a política mudar | Não |
| **Contatos** (telefone, e-mail, responsável) | Robô BrasilAPI + cadastro da Receita | `data/contatos/` | A cada 90 dias | **Sim** (LGPD) |
| **Presença digital** (site, Instagram) | Google via Serper (precisa de chave) | `data/contatos/` | Semestral | **Sim** |
| **Nº de colaboradores** | Solução 360 | `data/privado/colaboradores.xlsx` | Trimestral | **Sim** |
| **Catálogo de produtos** | Portfólio SESI/SENAI | `knowledge/portfolio/portfolio_compact.json` | Quando o portfólio mudar | Não |

O significado de cada coluna da Base Mestre está em [docs/dicionario_dados.md](docs/dicionario_dados.md).

---

## Regras de negócio (o que o painel considera)

| Regra | Como funciona | Onde mudar |
|---|---|---|
| **Indústria** | CNAE principal na Tabela DN da CNI. Empresa com CNAE industrial que não está na Base Mestre também conta como indústria. | `config/referencia/tabela_dn_cni.csv` |
| **Quem entra na não indústria** | Empresas **ativas** de AL, de todos os portes (ME, EPP, Demais), **menos o MEI optante**. Saem órgãos públicos, condomínios, partidos, igrejas e holdings. | `config/referencia/filtro_nao_industria.yaml` |
| **Cliente** | Teve proposta com status **Aceita**. **Ativo** = comprou nos últimos 24 meses; **Inativo** = antes disso. | `config/referencia/relacionamento.yaml` |
| **Unidade responsável** | Cliente fica na unidade do histórico; com histórico em duas unidades, vale a sede. Empresa nova vai pelo **bairro** da sede (Maceió) ou **município** (interior); se o bairro da Receita não bate com a minuta, vale o bairro dos vizinhos de mesmo CEP. **Sede fora de AL** fica com quem atender primeiro. Benedito Bentes foi desativado: a carteira foi para o Poço. | `config/referencia/carteira_minuta.csv` e `src/tools/carteira.py` |
| **Prioridade (Mercado)** | Nota 0–10 de semelhança com quem já compra (modelo treinado só com dado público: atividade, porte, cidade, capital, filiais, idade). Muito alto ≥ 30% das parecidas compram; Alto 15–30%; Médio 5–15%; Baixo < 5%. **Não é previsão de venda**, é ordem de procura. | `src/tools/potencial.py` |
| **Alertas** | Falência/recuperação judicial, sede fora de AL e **não ativa na Receita** (empresa da Base Mestre que fechou ou saiu de AL). Ficam escondidos por padrão na lista do Mercado. | `src/tools/potencial.py` |
| **Porte** | Duas réguas que **nunca se misturam**: Receita (faturamento: Micro, Pequena, Média ou grande) e FIEA (colaboradores: Micro 0–19, EPP 20–99, Média 100–499, Demais 500+). Empresa sem nº de colaboradores no cadastro fica "A confirmar". | `src/tools/universo_comercial.py` |
| **Dado pessoal** | A razão social do Empresário Individual vem com CPF da Receita: o CPF é **retirado** de todo arquivo público. Endereço de pessoa física e contatos nunca vão para o Git. | `src/tools/lgpd.py` |

---

## Atualizar os dados (resumo)

```
python jobs/checar_entradas.py          # o que está vencido e o que rodar
```

Rotina mensal, nesta ordem (detalhes em [docs/manual_atualizacao.md](docs/manual_atualizacao.md)):

1. Receita: `carregar_base_ampliada.py` → `incorporar_industrias_novas.py` → `extrair_enderecos.py`
2. Propostas: `atualizar_relacionamento.py`
3. Carteira e prioridade: `distribuir_carteira.py` → `calcular_potencial.py`
4. Publicar: `.\jobs\publicar_dados.ps1` — o painel online percebe os arquivos novos sozinho.

---

## Estrutura de pastas

```
app.py                  painel (Streamlit): menu, filtros globais e as páginas antigas
src/paginas/            páginas novas do painel (comercial.py = Clientes e Mercado)
src/tools/              regras e cálculos (carteira, potencial, relacionamento, LGPD...)
src/agents/, src/intelligence/, src/domain/   motor de recomendação de produto (IA)
jobs/                   scripts que atualizam os dados (rodar na raiz do projeto)
config/                 regras editáveis sem mexer em código + lista de entradas (entradas.yaml)
data/processed/         arquivos que o painel lê (vão para o GitHub)
data/privado/           propostas, valores, detalhes da carteira (NUNCA vão para o Git)
data/contatos/          contatos e endereços (NUNCA vão para o Git)
data/raw/               bases de origem antigas (referência)
knowledge/              catálogo de produtos SESI/SENAI
docs/                   documentação
tests/                  testes automáticos (pytest)
```

---

## O que é público e o que não é

O repositório e o painel online são **públicos**. Regra: vai para o Git só o que alimenta o painel e
**não identifica pessoa nem expõe valor comercial**.

- **Vai:** `data/processed/` (bases sem contato e sem CPF, carteira só com a unidade, prioridade, agregados), `config/`, código.
- **Não vai:** `data/privado/` (propostas, valores, histórico de unidade), `data/contatos/` (telefones, e-mails, sócios, endereços), `.env` (chaves).

As pastas que não vão para o Git são guardadas como backup no Teams/SharePoint pelo
`jobs/backup_teams.ps1`, chamado pelo `publicar_dados.ps1`.

---

## Rodar na sua máquina

```bash
pip install -r requirements.txt
streamlit run app.py
python -m pytest            # testes
```

Chaves (opcionais), num arquivo `.env` a partir do `.env.example`: `ANTHROPIC_API_KEY` (texto de
abordagem por IA) e `SERPER_API_KEY` (presença digital). O painel funciona sem elas.

---

## Documentação

| Documento | Para quê |
|---|---|
| [docs/manual_atualizacao.md](docs/manual_atualizacao.md) | Passo a passo mensal: o que baixar, onde colocar, o que rodar |
| [docs/mapa_do_sistema.md](docs/mapa_do_sistema.md) | Cada job: o que lê, o que grava, qual página usa |
| [docs/dicionario_dados.md](docs/dicionario_dados.md) | Coluna por coluna da Base Mestre e dos outros arquivos |
| [docs/arquitetura_dados.md](docs/arquitetura_dados.md) | Da Receita até o painel: funil, curadoria, consolidação por CNPJ raiz |
| [docs/guia_observatorio.md](docs/guia_observatorio.md) | Como levar o processamento para o Data Warehouse e automatizar |
| [docs/motor_de_recomendacao.md](docs/motor_de_recomendacao.md) | Como funciona a recomendação de produto por IA |
| [docs/catalogo_sti.md](docs/catalogo_sti.md) | Catálogo de serviços técnicos |
| [config/entradas.yaml](config/entradas.yaml) | Lista oficial das entradas de dados e de quanto em quanto tempo vencem |
| [docs/portfolio_en.md](docs/portfolio_en.md) | Apresentação do projeto em inglês |
