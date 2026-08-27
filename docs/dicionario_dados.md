# Dicionário de dados

Tabelas, views e as colunas que importam. O que não estiver aqui está
comentado no próprio SQL.

## Convenções que valem para tudo

- **`sq_candidato`** é chave de **candidatura**, não de pessoa. A mesma
  pessoa em duas eleições tem dois `sq_candidato`. A ligação entre anos
  está em `painel_link`.
- **`id_lista`** é a unidade que disputa as cadeiras no sistema
  proporcional: coligação (até 2018), partido isolado (2020, 2024),
  partido ou federação (2022). Vem de `SQ_COLIGACAO`, que o TSE preenche
  com o sequencial do próprio partido quando não há coligação.
- **"disputa"** = (ano, turno, cargo, uf, município). **"lista"** =
  (disputa, id_lista).
- Valores monetários nas **tabelas** são nominais. Nas **views** existem
  as duas versões: `receita_total` (nominal) e `receita_total_real`
  (deflacionada pelo IPCA, base em `deflator.ANO_BASE`).
- Documentos (CPF/CNPJ) só existem como SHA-256 salgado.

---

## Tabelas

### `candidatos` — uma linha por candidatura

| coluna | tipo | nota |
|---|---|---|
| `sq_candidato` | BIGINT PK | `SQ_CANDIDATO` |
| `ano_eleicao`, `turno` | INTEGER | só turno 1 é carregado |
| `cargo`, `cd_cargo` | VARCHAR / INTEGER | filtro estrutural da carga |
| `uf`, `municipio`, `cd_municipio` | VARCHAR | município NULL em cargos estaduais |
| `nome_candidato`, `nome_urna` | VARCHAR | normalizados em maiúscula; usados no pareamento |
| `partido`, `nr_partido` | VARCHAR / INTEGER | |
| `id_lista`, `nm_lista` | VARCHAR | ver convenções |
| `cpf_hash` | VARCHAR | NULL quando o TSE não publica o CPF |
| `genero`, `cor_raca`, `grau_instrucao`, `ocupacao`, `idade_posse`, `st_reeleicao` | | covariáveis pré-tratamento |
| `situacao_candidatura` | VARCHAR | APTO / INAPTO / … ; a view filtra por APTO e deferidos |
| `situacao_final` | VARCHAR | `DS_SIT_TOT_TURNO`, preenchido na carga de resultados |

### `resultados` — votação consolidada

| coluna | nota |
|---|---|
| `sq_candidato`, `turno` | PK composta |
| `votos_nominais` | soma entre zonas do município |
| `eleito` | `situacao_final LIKE 'ELEITO%'`. QP e MÉDIA são caminho, não status diferente |

### `receitas` / `despesas` — nível de transação

| coluna | nota |
|---|---|
| `fonte` | `fundo_eleitoral`, `fundo_partidario`, `doacao_pf`, `doacao_partido`, `proprio`, `outros` |
| `origem_bruta` | texto original do TSE, mantido para auditoria da classificação |
| `valor` | DECIMAL(18,2), nominal; negativos existem (estornos) |
| `data_receita` / `data_despesa` | guardadas para permitir deflação mensal depois |
| `doador_hash` / `fornecedor_hash` | SHA-256 salgado |
| `doador_tipo` / `fornecedor_tipo` | PF ou PJ, inferido pelo tamanho do documento |

### `ipca` — deflator

`ano`, `indice` (base 100 no ano de referência). Populada a partir de
`python/ingest/deflator.py`. Ano ausente ⇒ sem deflação, e a validação
acusa.

### `painel_link` — mesma pessoa entre eleições

`sq_t`, `sq_t1`, `ano_t`, `ano_t1`, `nivel_match` (1 a 4), `regra`.
Níveis 1 e 2 são os fortes; 3 e 4 entram só em robustez.

---

## Views

### Camada descritiva (`01_agregacoes_receita.sql`)

| view | o que é |
|---|---|
| `vw_deflator` | fator por ano + flag `deflacionado` |
| `vw_receita_candidato` | total, composição por fonte, nº de doadores, `share_maior_doador` |
| `vw_despesa_candidato` | total, nº de fornecedores, despesa com pessoal e publicidade |
| `vw_financas_candidato` | **tabela analítica principal**: uma linha por candidatura, finanças + resultado + shares + `gasto_por_voto` |
| `vw_desc_por_partido` | agregação por partido/ano/cargo, com mediana além da média |

Colunas de `vw_financas_candidato` que costumam confundir:

- `tem_prestacao_contas` — distingue "não arrecadou" de "não prestou contas".
- `share_fefc`, `share_doacao_pf`, `share_propria` — **NULL** quando a
  receita total é zero, não 0. Inventar "0% de FEFC" para quem não
  arrecadou nada é fabricar dado.
- `gasto_por_voto` — descritivo. Ver nota metodológica, seção 6.

### Variável de corte (`02_calculo_margem_disputa.sql`)

| view | o que é |
|---|---|
| `vw_rank_lista` | posição dentro da lista, cadeiras da lista, votos da lista e da disputa, `n_empatados` |
| `vw_corte_lista_bruto` | último eleito e primeiro suplente de cada lista, sem filtro |
| `vw_corte_lista` | idem, só listas com corte válido (`v_ultimo_eleito > v_primeiro_suplente`) |
| `vw_listas_descartadas` | quantas listas caem, por motivo |
| `vw_margem_candidato` | **a running variable**: `margem_votos`, `margem_rel_lista`, `margem_rel_disputa`, flags de fronteira |
| `vw_check_sinal_margem` | tem de voltar vazia: sinal da margem × status de eleito |
| `vw_check_simetria_margem` | tem de ser simétrica dentro da lista |

`margem_rel_lista` é a normalização principal (denominador = votos
nominais da lista); `margem_rel_disputa` entra como robustez.

### Amostra e painel (`03_janela_rdd.sql`)

| view | o que é |
|---|---|
| `vw_amostra_rdd` | amostra principal: toda candidatura com margem definida |
| `vw_amostra_fronteira` | só o par (último eleito, primeiro suplente), e só listas com o par completo |
| `vw_painel_rdd` | candidatura em *t* + desfechos em *t+1*, via `painel_link` |
| `vw_contagem_por_janela` | quantas observações sobrevivem a cada janela candidata |

Desfechos em `vw_painel_rdd`:

| coluna | tipo de margem | nota |
|---|---|---|
| `concorreu_t1` | extensiva | 0/1; quem não voltou é informação, não linha perdida |
| `ln_receita_t1_cond` | intensiva | **NULL** para quem não concorreu — é o desfecho principal |
| `ln_receita_t1` | mista | `ln(1 + receita)`, com zeros; reportado mas não é o principal |
| `eleito_t1`, `votos_t1` | extensiva | |
| `share_fefc_t1` | composição | |

Covariáveis pré-tratamento (têm de ser contínuas no corte):
`ln_receita_t`, `ln_despesa_t`, `share_fefc_t`, `n_doadores_t`,
`idade_posse`, `genero_fem` (derivada em Python).

A **janela do RDD não é fixada em SQL** de propósito: ela é escolhida em
`rdd_model.py` por banda MSE-ótima e varrida na robustez. Fixar `h` no
SQL esconderia a decisão mais sensível do desenho dentro do pipeline.

---

## Saídas

`outputs/tabelas/*.csv` — descritivas, estimativas e cada teste de
robustez, um arquivo por teste.
`outputs/figures/*.png` — descontinuidade, varredura de janelas,
densidade, composição de receita, associação bruta gasto × eleição.
`outputs/relatorio_rdd.json` — tudo consolidado, incluindo o veredito das
regras de decisão.
