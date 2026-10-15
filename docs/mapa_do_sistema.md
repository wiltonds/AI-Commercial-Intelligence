# Mapa do sistema — fonte → job → arquivo → página

Para quem precisa mexer no projeto: **cada job, o que ele lê, o que grava e quem usa o resultado.**
A ordem de execução e o passo a passo estão no [manual de atualização](manual_atualizacao.md);
a visão geral, no [README](../README.md).

Convenções:
- Todos os jobs ficam em `jobs/` e rodam **a partir da raiz do projeto** (`python jobs/<nome>.py`).
- O texto no topo de cada job explica o uso e as opções (`python jobs/<nome>.py --help`).
- 🔒 = arquivo confidencial, fica só na máquina local (`data/privado/` ou `data/contatos/`).
- **Log**: nome com que o job grava a data de execução em `data/processed/LOG_ATUALIZACOES.csv`
  (é o que `checar_entradas.py` e a página Rotina de Dados usam para dizer o que está vencido).

---

## 1. Jobs da rotina mensal (nesta ordem)

| # | Job | Lê | Grava | Log |
|---|---|---|---|---|
| 1 | `carregar_base_ampliada.py --pasta <zips>` | Zips da Receita (Estabelecimentos, Empresas, **Simples**, Municipios, Cnaes, Naturezas); Base Mestre; `config/referencia/tabela_dn_cni.csv`; `filtro_nao_industria.yaml`; `data/raw/BASE_CONSOLIDADA_SESI_SENAI.xlsx` (porte FIEA) | `data/processed/BASE_AMPLIADA_AL.csv` (empresas ativas de AL fora da Base Mestre, sem MEI, sem CPF); `data/processed/MEI_BASE_MESTRE.csv`; 🔒 `data/contatos/CONTATOS_RECEITA.csv` | `receita_cnpj` |
| 2 | `incorporar_industrias_novas.py --competencia AAAA-MM` | Base Ampliada; Base Mestre; contatos | Base Mestre com as indústrias novas (`ORIGEM_REGISTRO = Receita AAAA-MM (incorporada)`); Base Ampliada sem elas; 🔒 `data/contatos/INDUSTRIAS_NOVAS_AAAAMM.xlsx` (lista para o comercial) | `base_mestre` |
| 3 | `extrair_enderecos.py --pasta <zips>` | Zips da Receita (Estabelecimentos, Empresas, Municipios, Naturezas) | 🔒 `data/contatos/ENDERECOS_AL.csv` — todo estabelecimento **ativo** de AL: bairro, CEP, capital, natureza | `enderecos` |
| 4 | `atualizar_relacionamento.py --arquivo data/privado/propostas.xlsx` | 🔒 Propostas; Base Mestre; Base Ampliada; `config/referencia/relacionamento.yaml`, `linhas_negocio.yaml` | **Dentro** da Base Mestre e da Base Ampliada: cliente SESI/SENAI, situação (Ativo/Inativo), última compra. Também `VISAO_360.csv`, `ADESAO_NATUREZA_MUNICIPIO.csv`, `PORTE_FIEA.csv`, `PRODUTOS_RANKING.csv`, `ATENDIMENTO_POR_ANO.csv`; 🔒 `data/privado/RELACIONAMENTO_POR_EMPRESA.csv`, `CLIENTES_FORA_DA_BASE.csv` | `propostas` |
| 5 | `distribuir_carteira.py --historico data/privado/propostas.xlsx` | 🔒 `ENDERECOS_AL.csv`; 🔒 propostas; `config/referencia/carteira_minuta.csv`; Base Mestre + Ampliada (universo) | `data/processed/CARTEIRA_UNIDADES.csv` (só a unidade); 🔒 `data/privado/CARTEIRA_UNIDADES_DETALHE.csv` (motivo, histórico, bairro) | `carteira_unidades` |
| 6 | `calcular_potencial.py` | Base Mestre; Base Ampliada; `MEI_BASE_MESTRE.csv`; 🔒 `ENDERECOS_AL.csv` | `data/processed/POTENCIAL_MERCADO.csv` (nota, prioridade, motivo, alerta, bairro — sem bairro de Empresário Individual) | `potencial` |
| 7 | `publicar_dados.ps1` | Os arquivos de `data/processed/` listados no script | Commit + push no GitHub (o painel online atualiza sozinho). Chama `backup_teams.ps1`, que zipa 🔒 `data/privado` e `data/contatos` para subir no Teams/SharePoint | — |

> **Por que a ordem importa:** o relacionamento (passo 4) é gravado **dentro** da Base Mestre e da Base
> Ampliada. Se os passos 1–2 rodarem depois, eles recriam as bases e o relacionamento some até o
> passo 4 rodar de novo. Carteira e prioridade (5–6) dependem de endereços e relacionamento prontos.

## 2. Jobs de enriquecimento (quando `checar_entradas.py` indicar)

| Job | Lê | Grava | Log |
|---|---|---|---|
| `enriquecer_contatos.py` | Base Mestre + Ampliada (fila: quem tem sinal primeiro) | 🔒 `data/contatos/CONTATOS_EMPRESAS.csv` (BrasilAPI: telefones, e-mail, sócios/responsável) | `contatos_robo` |
| `segunda_passada_contatos.py` | 🔒 `CONTATOS_EMPRESAS.csv` | O mesmo arquivo: celular antigo ganha o nono dígito e vai para WhatsApp; firma individual sem sócio ganha o titular como responsável (sem nova consulta) | — |
| `enriquecer_digital.py` | 🔒 `CONTATOS_EMPRESAS.csv`; chave `SERPER_API_KEY` | O mesmo arquivo: site, Instagram, e-mail do site | `presenca_digital` |
| `importar_colaboradores.py --arquivo data/privado/colaboradores.xlsx` | 🔒 Exportação da Solução 360 | `data/processed/COLABORADORES.csv` (faixa); 🔒 `data/privado/COLABORADORES_EXATO.csv` | `colaboradores` |
| `mapear_hubs.py` | 🔒 Contatos; Base Mestre + Ampliada | `HUBS_CANAIS_PUBLICO.csv`, `HUBS_MEMBROS_PUBLICO.csv` (só domínio de empresa); 🔒 `data/privado/HUBS_CANAIS.xlsx` | `hubs` |

## 3. Jobs de verificação e ferramentas manuais

| Job | Para quê |
|---|---|
| `checar_entradas.py` | Diz o que está em dia, vencido ou nunca rodado, e o que rodar. Lê `config/entradas.yaml` + o log. |
| `checar_situacao_cadastral.py` | Checagem diária rotativa de baixa/inaptidão (ReceitaWS), entre uma carga mensal e outra; grava `MONITORAMENTO_SITUACAO_CADASTRAL.csv` (fora do Git). |
| `qualificar_base.py` | Roda o motor de recomendação em toda a Base Mestre e gera `BASE_QUALIFICADA_CRM.csv` para importar no CRM. |
| `validar_afinidade.py` | Mede se a matriz de afinidade setor × produto prevê compra real (gera `AFINIDADE_EMPIRICA_*.csv`). |

---

## 4. Quem lê cada arquivo do painel

| Arquivo (`data/processed/`) | Gerado por | Usado nas páginas |
|---|---|---|
| `BASE_MESTRE_COMERCIAL.csv` | BI_Project + jobs 2 e 4 | Todas (é a base do menu e dos filtros globais) |
| `BASE_AMPLIADA_AL.csv` | jobs 1, 2 e 4 | Clientes, Mercado, Explorador, SESI \| SENAI |
| `CARTEIRA_UNIDADES.csv` | job 5 | Clientes, Mercado e o filtro "Unidade (carteira)" das outras páginas |
| `POTENCIAL_MERCADO.csv` | job 6 | Mercado |
| `MEI_BASE_MESTRE.csv` | job 1 | Clientes, Mercado (tira MEI que nunca comprou) |
| `PORTE_FIEA.csv` | job 4 | Clientes, Mercado, Explorador |
| `VISAO_360.csv`, `ADESAO_NATUREZA_MUNICIPIO.csv` | job 4 | SESI \| SENAI, Canais, cartão Visão 360 do Explorador |
| `PRODUTOS_RANKING.csv`, `ATENDIMENTO_POR_ANO.csv` | job 4 | Share & Relacionamento |
| `COLABORADORES.csv` | `importar_colaboradores.py` | Explorador, SESI \| SENAI, Visão 360 |
| `HUBS_*_PUBLICO.csv` | `mapear_hubs.py` | Canais e Conexões |
| `AUDITORIA_RECEITA_GAP_INDUSTRIA.csv` | Auditoria inicial (arquivo fixo, set/2026) | Auditoria de Cobertura |
| `LOG_ATUALIZACOES.csv` | todos os jobs | Rotina de Dados |

O painel guarda os arquivos em memória (cache). Quando qualquer arquivo de `data/processed/` muda,
o `app.py` percebe pela data/tamanho e recarrega sozinho — não é preciso reiniciar o app.

---

## 5. Onde fica cada regra no código

| Assunto | Arquivo |
|---|---|
| Ler os zips da Receita, porte, MEI | `src/tools/receita_cnpj.py` |
| O que é indústria / filtro de não indústria | `src/tools/receita_cnpj.py` + `config/referencia/` |
| Cliente, ativo/inativo, última compra | `src/tools/relacionamento.py` + `config/referencia/relacionamento.yaml` |
| Unidade responsável (Minuta) | `src/tools/carteira.py` + `config/referencia/carteira_minuta.csv` |
| Modelo de prioridade, faixas, alertas | `src/tools/potencial.py` |
| Universo Clientes/Mercado, réguas de porte, filtros | `src/tools/universo_comercial.py` |
| Telas Clientes e Mercado | `src/paginas/comercial.py` |
| Retirar CPF dos arquivos públicos | `src/tools/lgpd.py` |
| Consolidar matriz + filiais por CNPJ raiz | `src/tools/cnpj_raiz.py` |
| Motor de recomendação de produto | `src/agents/`, `src/intelligence/`, `src/pipeline.py` |
| Menu, filtros globais, páginas antigas, cache | `app.py` |

Os testes automáticos de cada regra estão em `tests/` com o mesmo nome do assunto
(ex.: `tests/test_carteira.py`, `tests/test_potencial.py`). Rode `python -m pytest` depois de qualquer mudança.
