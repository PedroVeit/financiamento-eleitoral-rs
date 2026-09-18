# Plano de execução e estado atual

Não há prazo externo. Os dados consolidados de 2026 só saem bem depois de
outubro, e o valor do projeto está no pipeline histórico — 2026 é fase
posterior, não âncora.

## Estado

| Fase | Entrega | Estado |
|---|---|---|
| 0 | Schema, esqueleto do repositório, Makefile, CI | **pronto** |
| 0 | Deflator IPCA e camada de valores reais | **pronto** |
| 0 | Gerador sintético em formato TSE + validação do estimador | **pronto** |
| 1 | Scripts de download e carga do TSE | **pronto e rodando contra o servidor real** |
| 1 | Validação dos totais contra as estatísticas oficiais | feita por plausibilidade (teto legal de gasto, nº de eleitos ano a ano); comparação direta com o DivulgaCandContas não foi possível automatizar — ver nota abaixo |
| 2 | Camada descritiva (SQL + gráficos) | **pronta**, rodada em dado real |
| 3 | Nota metodológica e regras de decisão | **prontas, automatizadas, e já aplicadas a um resultado real** |
| 4 | Modelo causal + bateria de robustez | **pronto**, rodado em dado real |
| 5 | Redação dos resultados | **feita** — [`docs/resultados.md`](resultados.md) |
| 6 | Extensão: empilhar ciclo 2016→2020 | **feita** — executada, resultado em `resultados.md` |
| 7 | Limites de Lee para o efeito condicional | não iniciada — nova prioridade nº1 |
| 7 | Agrupar erro-padrão por pessoa (não só lista-disputa) | não iniciada |
| 7 | Outras UFs, outros cargos, Desenho B | não iniciada |

O recorte vereador/RS fechou a 2ª rodada (painel empilhado 2016→2020 +
2020→2024) com resultado **NÃO IDENTIFICADO** (ver `resultados.md`) —
mesmo veredito da 1ª rodada, mas por um motivo diferente e mais
específico. A instabilidade de sinal que bloqueava a 1ª rodada quase
desapareceu (de τ=−0,098 para τ=−0,001 na janela mais estreita); o que
passou a bloquear é a seleção na recandidatura, que ficou **mais forte**
com mais dado (p caiu de 0,020 para 0,0013) — sinal de que é estrutural,
não amostral. Isso desloca a prioridade da extensão de "mais dados" para
"modelar a seleção explicitamente" (fase 7, limites de Lee).

**Nota sobre a validação de totais:** o DivulgaCandContas é um painel
carregado via JavaScript, sem endpoint agregável por busca automatizada
(só consulta individual por candidato). A validação foi feita por
plausibilidade: o gasto médio por candidato (R$ 2.304 em 2020, R$ 5.432
em 2024) fica bem abaixo do teto legal de R$ 85.811,91 por candidatura a
vereador no RS, como esperado; e o número de vereadores eleitos é quase
idêntico entre os dois anos (4.902 e 4.903), como deveria ser. Quem
quiser uma comparação direta pode abrir o painel manualmente para um
recorte específico.

## Próximos passos, em ordem — extensão 2016→2020

Os passos abaixo substituem os que valiam para a primeira execução (já
feitos — ver histórico completo em `docs/decisoes.md`, D13). São a
sequência para a extensão atual: empilhar o ciclo 2016→2020 ao lado do
2020→2024 já carregado.

1. **`make inspecionar ANOS="2016"`.** O arquivo de 2016 é anterior à
   LGPD entrar em vigor plenamente nas publicações do TSE — é esperado
   que `NR_CPF_CANDIDATO` venha com o CPF completo (ao contrário de 2024,
   que veio mascarado como `-4`). Confirmar isso antes de mais nada: se
   confirmado, o pareamento 2016→2020 pode usar nível 1 (CPF), muito mais
   confiável que nível 2 (nome + município). Comparar também
   `DS_SITUACAO_CANDIDATURA` — é esperado que 2016 tenha valores reais
   (`APTO`/`INAPTO`), não o sentinela `#NE` que só aparece a partir de
   2022 (ver D13.2).

2. **`make dados ANOS="2016"`** — baixa e extrai só o que falta; 2020 e
   2024 já estão em cache.

3. **`make banco ANOS="2016 2020 2024"` com `--recriar`.** Precisa
   recarregar os três anos juntos porque `--recriar` apaga o banco antes
   de popular — não dá para só "adicionar" 2016 a um banco que já tem
   2020/2024 carregados sem `--recriar`, ou os totais de validação
   ficariam inconsistentes com uma carga parcial anterior.
   `carregar_tse()` já aceita lista de anos arbitrária, então isso é
   literalmente `python -m python.ingest.load_to_duckdb --anos 2016 2020
   2024 --uf RS --cargo VEREADOR --banco data/db/financiamento.duckdb
   --recriar`. Conferir que o aviso de cargo-municipal-em-ano-errado
   (D14) NÃO aparece — se aparecer, algo passou um ano de eleição geral
   por engano.

4. **Conferir manualmente umas cinco listas de 2016**, mesma lógica do
   passo 4 da execução original — o corte intra-lista precisa ser
   validado em cada ano novo carregado, não só uma vez.

5. **Construir os DOIS painéis, nesta ordem:**
   ```
   make painel DE=2016 PARA=2020
   make painel DE=2020 PARA=2024
   ```
   Cada um popula `painel_link` filtrado pelo próprio par de anos —
   rodar os dois não apaga um ao outro. Comparar a taxa de pareamento do
   novo painel (2016→2020) com a do antigo (2020→2024, 30,2% por nome):
   se vier sensivelmente maior (esperado, pelo CPF completo), é sinal de
   que a hipótese do passo 1 se confirmou.

6. **`make analise`.** A seção "4.9 heterogeneidade por ciclo eleitoral"
   do relatório agora vai ter dado de verdade para comparar (com um só
   painel, ela aparecia como "[pulado]"). Ler o veredito da seção 6
   antes de qualquer coeficiente — inclusive a nova regra de
   heterogeneidade entre ciclos (D14).

7. **Comparar o novo `docs/resultados.md` com a versão anterior lado a
   lado.** As perguntas que importam: o veredito mudou? Se sim, por quê
   (a instabilidade da janela estreita sumiu com mais dado, ou a
   heterogeneidade entre ciclos revelou outra coisa)? Documentar a
   comparação é tão importante quanto o novo número.

## Regra de disciplina

A ordem acima é o ponto do plano: a estimativa causal vem **por último**,
depois que amostra, recorte e validação já estão fechados. Rodar o modelo
cedo e ajustar o recorte até o resultado ficar bonito é o modo mais fácil
de produzir um número que não significa nada — e num projeto de
portfólio, o histórico de commits denuncia isso.

## Definição de "pronto"

- [x] Schema relacional e pipeline SQL versionado e reexecutável do zero
- [x] Nota metodológica escrita **antes** da implementação do modelo
- [x] Regras de decisão pré-registradas e automatizadas
- [x] Estimador validado contra efeito conhecido, e contra efeito zero
- [x] Robustez implementada (janela, covariáveis, placebo, donut,
      densidade, normalização alternativa, amostra de fronteira)
- [x] Deflação de valores entre eleições
- [x] README compreensível por leigo em menos de dois minutos, com a
      seção "o que este projeto não conclui"
- [x] CI rodando a suíte a cada push
- [x] Banco populado e validado com duas eleições reais (RS, vereador,
      2020 e 2024)
- [x] Camada descritiva com dados reais
- [x] Estimativa causal reportada com robustez, no cenário de efeito
      **não identificado** — `docs/resultados.md`
- [x] Figura do README substituída pela versão com dado real

O projeto está **completo** no recorte proposto. As extensões abaixo são
melhorias possíveis, não pendências.

## Extensões, em ordem de custo-benefício

1. **~~Mais ciclos eleitorais~~ → em andamento** (ver seção "Próximos
   passos" acima). Corrigido: só 2016 e 2012 são ciclos municipais
   anteriores válidos para vereador — 2018 e 2022 são eleições gerais e
   não têm essa candidatura (ver `docs/decisoes.md`, D14).
2. **2012, se 2016 não resolver.** Mesmo procedimento do 2016, um passo
   mais para trás. Guardado como próxima carta, não como parte do plano
   atual — melhor esgotar um incremento de cada vez e ler o resultado
   antes de decidir se vale acrescentar mais um ciclo.
3. **Limites de Lee** para o efeito condicional a recandidatar-se, em
   vez de só reportar que a regra bloqueou por seleção de amostra.
4. **Agrupar erro-padrão por pessoa**, não só por lista-disputa, quando
   o painel empilhado tiver muita gente que disputou 3+ eleições — a
   mesma pessoa em dois pares diferentes (2016→2020 e 2020→2024) não é
   uma observação independente (ver D14, "cuidado de desenho").
5. **Demais UFs.** O código não tem nada específico do RS além de um
   argumento de linha de comando.
6. **Deputado estadual.** A mesma lógica intra-lista se aplica; muda o
   tamanho da lista e a unidade geográfica. Cargo de eleição geral —
   usar os anos 2018, 2022, 2026, não os municipais.
7. **Modelar suplência.** Suplentes assumem cadeira com alguma
   frequência, o que atenua o efeito estimado. Tratar como tratamento
   parcial é um refinamento com literatura própria.
8. **Deflação mensal** por data de transação, em vez de índice anual.
9. **Desenho B** (efeito do gasto sobre voto) via limiares populacionais
   de teto de gasto — projeto próprio, ver nota metodológica, seção 11.
10. **Eleição de 2028**, quando as contas estiverem consolidadas (a
    próxima municipal). É atualização do pipeline existente, não
    projeto novo.
