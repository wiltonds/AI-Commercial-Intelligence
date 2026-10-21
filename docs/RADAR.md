# Radar de Oportunidades

Painel separado (`radar_app.py`) para acompanhar **todo dia** o mercado industrial de Alagoas e transformar
sinais públicos em oportunidades para SSI, STI, EP e EB. Lê os mesmos dados do painel de Inteligência Comercial
(Base Mestre, Visão 360). Não guarda dono nem status de negociação: isso fica no Moskit.

## Telas
| Tela | Pergunta que responde |
|---|---|
| Hoje | O que mudou no mercado e por onde começar? |
| Sinais | Todos os sinais com evidência (link), filtros e download para o comercial/Moskit |
| Mercado | Onde a indústria pesa (IBGE), quanto já atendemos, onde está o mercado não atendido (por setor CNI e município) |
| Negócios e metas 2027 | Por negócio: clientes, reativar, cross-sell, prospectar, sinais ativos e meta 2027 |
| Saúde das fontes | Cada fonte está em dia? |

## Fontes
| Fonte | Job | Onde roda | Frequência |
|---|---|---|---|
| Notícias e sites oficiais (Google News RSS) | `jobs/coletar_noticias.py` | GitHub Actions | diária |
| IBGE / SIDRA (PIB, VAB da indústria, população) | `jobs/coletar_ibge.py` | GitHub Actions | semanal |
| CNO – obras novas (Receita) | `jobs/coletar_cno.py` | notebook (a Receita bloqueia servidor) | diária |
| Base Mestre, Visão 360, propostas | jobs do painel comercial | notebook | mensal |

Tudo por regra, **sem custo de IA nem de API**. O que procurar e como classificar está em `config/radar.yaml`;
o que oferecer para cada tipo de sinal, em `config/ofertas.yaml`; o catálogo de fontes, em `config/fontes.yaml`.

## Metas 2027
Salve o planejamento em `data/privado/METAS_2027.xlsx` (fora do Git) com as colunas
`negocio` (SSI, STI, EP, EB), `produto`, `unidade`, `mes` (1–12) e `meta` (R$).
Para mostrar no painel online sem expor o detalhe, publique só o resumo em `data/processed/METAS_2027_RESUMO.csv`.

## Publicar o painel
share.streamlit.io › New app › este repositório, branch `master`, arquivo principal `radar_app.py`.
