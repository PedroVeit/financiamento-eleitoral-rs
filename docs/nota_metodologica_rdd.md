# Nota metodológica: o que este desenho identifica, e o que não identifica

Esta nota existe para ser lida **antes** dos resultados. Ela descreve o
que o desenho consegue sustentar e onde ele para. A ordem não é
acidental: uma justificativa de identificação escrita depois dos
resultados tende a ser escrita para justificá-los.

---

## 1. O problema, em uma frase

Campanhas que gastam mais elegem mais. Isso é fato descritivo e ninguém
discute. A pergunta é se o dinheiro **produz** o voto, ou se o dinheiro
**segue** o candidato que já ia bem — doadores não são cegos, e financiar
quem tem chance é comportamento racional, não anomalia.

Formalmente: existe uma variável não observada (chame de *qualidade*,
*viabilidade* ou *reputação prévia*) que causa tanto mais arrecadação
quanto mais voto. Regredir voto contra gasto atribui ao gasto o efeito
dessa variável omitida. O coeficiente resultante é enviesado para cima, e
não há quantidade de controles observáveis que resolva isso, porque a
variável central é justamente a não observável.

---

## 2. Por que a especificação original não funciona

A especificação inicial do projeto pedia:

> "calcular a margem de votos entre o último candidato eleito e o primeiro
> não-eleito (a 'linha de corte')" e usar isso para "estimar o efeito do
> gasto sobre a chance de vitória".

Há dois problemas distintos aí, e vale separá-los porque só um é fatal.

### 2.1. Problema mecânico: em eleição proporcional, essa "linha de corte" não existe

Vereador e deputado estadual são eleitos por **representação proporcional
de lista aberta**. As cadeiras vão primeiro para as listas (partido,
federação ou, até 2018, coligação), pelo quociente eleitoral e pela
distribuição de sobras. Só depois vão para as pessoas, por voto nominal,
**dentro** de cada lista.

Consequência: ordenar todos os candidatos do município por voto e cortar
na N-ésima vaga produz uma variável que não corresponde a nenhuma regra
real. Um candidato pode ser o 12º mais votado do município e se eleger
enquanto o 8º não se elege, porque estão em listas diferentes. O "corte"
construído assim é ruidoso, e o tratamento deixa de ser função
determinística da variável de corte — o que quebra o pressuposto básico
do RDD.

**A descontinuidade real é intra-lista.** Dado que a lista conquistou
*S* cadeiras, elas vão para os *S* mais votados da lista. Entre o
*S*-ésimo e o *(S+1)*-ésimo candidato **da mesma lista** existe um corte
determinístico e afiado. É isso que `sql/02_calculo_margem_disputa.sql`
implementa, com window functions, e o que
`test_margem_nao_usa_ranking_da_disputa` trava contra regressão.

Esse problema é corrigível, e foi corrigido.

### 2.2. Problema conceitual: o RDD de margem não identifica o efeito do gasto

Este é o problema fatal, e nenhuma correção de código resolve.

Um RDD precisa de três coisas: uma variável contínua de corte, uma regra
que muda o tratamento descontinuamente num ponto dessa variável, e a
impossibilidade de os agentes controlarem com precisão de que lado do
ponto caem. No desenho original:

- **Tratamento** = gasto de campanha. Variável contínua, escolhida pelo
  próprio candidato. Não existe valor de gasto acima do qual alguma
  regra mude o status do candidato.
- **Variável de corte** = margem de votos. Mas a margem é *posterior* ao
  gasto, e é um dos desfechos de interesse.

O RDD identifica o efeito de **cruzar o corte**, e o que muda
descontinuamente no corte é *ser eleito*. O gasto **não** salta ali —
dois candidatos separados por três votos gastaram valores parecidos, e é
exatamente por isso que são comparáveis. O gasto é a variável contínua
que ambos têm; o mandato é a variável que só um tem.

Se o gasto saltasse no corte, isso não seria evidência a favor do
desenho — seria evidência **contra** ele, sinal de que os dois lados não
são comparáveis. Por isso o gasto em *t* entra no projeto como teste de
continuidade de covariável (seção 4), não como tratamento.

Duas saídas honestas:

- **Mudar o estimando** para algo que o desenho de fato identifica
  (Desenho A). É a entrega principal deste projeto.
- **Mudar a fonte de variação** para uma que atinja diretamente o
  dinheiro (Desenho B). Fica registrado como extensão, com o custo
  declarado.

---

## 3. Desenho A — efeito de eleger-se sobre o financiamento futuro

| Componente | Definição |
|---|---|
| Variável de corte | margem de votos até o corte de cadeira, **dentro da lista** |
| Tratamento | ter sido eleito em *t* (margem > 0). Sharp RD |
| Desfecho principal | ln(receita de campanha) em *t+1* |
| Desfechos auxiliares | voltar a concorrer, eleger-se de novo, composição da receita |
| Unidades | candidaturas próximas ao corte da última cadeira da lista |

É o *close-election RDD*, o desenho mais estabelecido da literatura de
política empírica (Lee, 2008), aplicado à direção de causalidade que os
dados do TSE permitem identificar.

**Por que isto vale a pena, e não é prêmio de consolação.** A pergunta
original pressupõe que a correlação entre dinheiro e voto tem um
componente de causalidade reversa. O Desenho A **mede esse componente
diretamente**. Se dois candidatos empatados em qualidade, gasto e
reputação — separados por um punhado de votos por acaso — divergem
sistematicamente em arrecadação na eleição seguinte, a diferença não pode
ser qualidade prévia: ela foi criada pelo mandato.

Hoje esse canal é quase sempre assumido e quase nunca medido. Medi-lo é o
que torna o projeto interessante, em vez de apenas alegá-lo.

É também um resultado com implicação institucional própria: a vantagem
financeira do incumbente é argumento recorrente em debates sobre
financiamento eleitoral, e normalmente é sustentada por comparação bruta
entre incumbentes e desafiantes — que sofre exatamente do viés de seleção
que este desenho remove.

### Margem extensiva e intensiva, separadas

O desfecho de receita em *t+1* só é observado para quem voltou a
concorrer. Isso obriga a separar duas coisas:

- **extensiva**: ser eleito muda a probabilidade de se recandidatar?
- **intensiva**: entre quem se recandidatou, quanto a mais captou?

Juntar as duas num único `ln(1 + receita)` põe uma pilha de zeros no meio
de valores na casa de ln(receita) ≈ 11, infla a variância e transforma um
efeito sobre captação num efeito sobre "continuar na política" mal
disfarçado. O pipeline estima as duas e reporta as duas.

**Se a margem extensiva for significativa, o efeito intensivo é
condicional a recandidatar-se, e tem de ser rotulado assim.** As saídas
legítimas são: reportar o efeito condicional com o rótulo correto, ou
calcular limites de Lee para o intervalo compatível com a seleção
observada. Reportar como se nada tivesse acontecido não é uma delas.
Essa regra está implementada em `python/analysis/regras_decisao.py` e é
aplicada automaticamente ao fim de cada execução.

---

## 4. Pressupostos, e como cada um é testado

| Pressuposto | Teste | Onde |
|---|---|---|
| Ninguém controla de que lado do corte cai | Densidade da variável de corte (Cattaneo-Jansson-Ma) | `teste_densidade` |
| Perto do corte, ganhar é quase aleatório | Covariáveis pré-eleitorais não saltam no corte | `teste_continuidade_covariaveis` |
| O salto é a regra, não ruído | Estimativa em cortes falsos | `teste_cortes_placebo` |
| A conclusão não depende da janela | Varredura de h de 0,5% a 12% | `varredura_janelas` |
| O efeito não vem de um punhado de casos colados no corte | Donut | `teste_donut` |
| A conclusão não depende da normalização | Margem sobre a lista × sobre a disputa | `run_pipeline`, seção 4.7 |
| O painel não é selecionado pelo tratamento | RDD sobre recandidatura | desfecho `concorreu_t1` |
| O estimador funciona | Recuperar efeito conhecido em dado sintético | `tests/test_rdd.py` |

Sobre manipulação: neste desenho ela é implausível *a priori*, porque o
corte depende do desempenho dos **colegas de lista** e do quociente
eleitoral, não só do próprio voto. Mas implausível não é o mesmo que
testado, e o teste continua obrigatório.

Sobre placebos: são vários testes ao mesmo tempo, então **um** deles dar
significante a 5% é o esperado por acaso. O que invalidaria o desenho é
um padrão — vários saltos, ou salto justo na covariável mais
correlacionada com o desfecho. As regras de decisão bloqueiam a partir de
duas falhas e emitem alerta com uma, em vez de varrer para baixo do tapete.

---

## 5. Exclusões declaradas

Todas em `sql/02_calculo_margem_disputa.sql`, e todas contadas em
`vw_listas_descartadas` — nenhum descarte é silencioso.

- **Listas sem eleito ou sem não-eleito**: não há corte observável nem
  contrafactual interno.
- **Empates no corte**: no Brasil o empate é decidido pela idade do
  candidato, não por votos. Nesses casos o tratamento não é determinado
  pela variável de corte e o desenho *sharp* deixaria de valer.
- **Inversões** (não-eleito com mais votos que um eleito da mesma lista):
  vêm de cassação, substituição, indeferimento posterior. Não são
  eleição decidida por votos.
- **Empatados em votos dentro da lista**: mesma razão do segundo item,
  aplicada a cada candidatura.

Isso condiciona a amostra a listas que ganharam ao menos uma cadeira e
tiveram ao menos um suplente. É restrição de **validade externa**, não de
validade interna.

---

## 6. O que a métrica "gasto por voto" é e não é

`gasto_por_voto = despesa_total / votos` aparece na camada descritiva e é
tentador ler como eficiência. Não é.

O denominador é o desfecho. Candidatos com poucos votos têm razão alta
por construção aritmética, mesmo com gasto idêntico. A distribuição é
fortemente assimétrica e a média é dominada por casos de votação mínima.
E como o gasto responde à expectativa de votação, a razão mistura causa e
consequência num único número.

Ela é reportada porque descreve a estrutura do gasto declarado e porque é
amplamente citada no debate público — mas sempre como mediana por estrato
comparável (mesmo cargo, mesmo porte de município, mesmo ano), nunca como
ranking de eficiência entre candidatos ou partidos.

---

## 7. Limites de validade

1. **O efeito é local.** Vale para candidaturas perto do corte da última
   cadeira da lista. Não diz nada sobre puxadores de legenda, sobre
   candidatos de votação marginal, nem sobre disputas decididas com
   folga — que são a maioria.
2. **Não mede o efeito do dinheiro sobre votos.** Mede o efeito de vencer
   sobre o dinheiro captado depois. São perguntas diferentes, e o README
   não pode confundi-las.
3. **Suplente não é exatamente "não eleito".** Suplentes assumem cadeira
   com alguma frequência ao longo do mandato. Isso *atenua* o efeito
   estimado — parte do grupo de controle recebe tratamento parcial — e
   uma extensão natural é modelar isso explicitamente.
4. **Recorte.** Rio Grande do Sul, vereador. Extrapolação para outros
   estados ou cargos é hipótese, não resultado. O pipeline é
   parametrizado por cargo e UF: expandir é trocar um argumento de linha
   de comando.
5. **Pareamento entre eleições é imperfeito.** O TSE não publica
   identificador estável de pessoa, e o CPF sumiu de parte dos arquivos.
   A cascata de pareamento registra o nível de cada par, a taxa de
   cobertura é reportada, e a análise principal usa só os níveis fortes.
6. **O dado é prestação de contas declarada.** Gasto não declarado não
   aparece — e não há razão para supor que se distribua igualmente dos
   dois lados do corte. É limite do dado, não do método, e nenhum teste
   estatístico o resolve.
7. **Deflação por índice anual** é aproximação. O rigoroso seria
   deflacionar cada lançamento pela data da transação; o schema guarda
   `data_receita` e `data_despesa` para permitir isso depois.
8. **Painel empilhado assume erro-padrão independente entre pares de
   anos diferentes.** Ao empilhar mais de um ciclo (ex.: 2016→2020 e
   2020→2024 — ver `docs/decisoes.md`, D14), uma pessoa que disputou nas
   três eleições contribui duas observações ao painel, uma para cada
   transição. É o desenho correto de RDD em painel — cada transição é
   uma unidade de tratamento válida — mas o agrupamento de erro-padrão
   por lista-disputa não captura a correlação entre as duas observações
   da mesma pessoa em anos diferentes. Não invalida a estimativa pontual,
   mas pode subestimar levemente o erro-padrão quando há muitos
   recandidatos de 3+ eleições; agrupar por pessoa é o refinamento
   natural se isso passar a importar.

---

## 8. Regra de decisão pré-registrada

Fixada antes da execução sobre dados reais e implementada em
`python/analysis/regras_decisao.py`, que é rodado automaticamente ao fim
do pipeline. O veredito é um de três:

- **NÃO IDENTIFICADO** — se o teste de densidade rejeitar, se **duas ou
  mais** covariáveis pré-tratamento saltarem no corte, se dois ou mais
  cortes placebo derem significantes, se o efeito trocar de sinal ao
  longo da varredura de janelas, ou se, havendo mais de um ciclo
  eleitoral empilhado (D14), dois ou mais ciclos forem individualmente
  significativos com sinais opostos. Nesse caso o resultado **não é
  reportado como efeito causal**, com ou sem ressalva.
- **CONDICIONAL** — se ser eleito afetar a probabilidade de voltar a
  concorrer (p < 0,10). O efeito sobre receita existe, mas é condicional
  a recandidatar-se, e só pode ser publicado com esse rótulo.
- **IDENTIFICADO** — nenhum pressuposto testável rejeitado.

"Não foi possível identificar um efeito robusto" é conclusão publicável,
e é a conclusão correta quando os pressupostos falham. O repositório fica
mais confiável por reportá-la, não menos.

Alterações de desenho posteriores devem ser registradas em commit datado
com justificativa, e resultados obtidos após mudança de desenho devem ser
apresentados como exploratórios.

---

## 9. Validação do estimador antes do dado real

`python/synthetic/gerar_dados_sinteticos.py` produz CSVs no formato do
TSE a partir de um processo com efeito causal **conhecido**, incluindo de
propósito a variável de qualidade omitida que enviesa a regressão
ingênua. A suíte de testes exige que o pipeline recupere esse efeito
dentro do intervalo de confiança **e** que não encontre efeito quando ele
é zero.

O caminho de ingestão inteiro é exercitado: os dados sintéticos saem como
CSV latin-1 com `;` e decimal com vírgula, passam pelo `read_csv` do
DuckDB, pela classificação de fonte de receita e pelo pareamento do
painel. Não é uma maquete do pipeline; é o pipeline.

Isso já se pagou. A primeira versão estimava um efeito sistematicamente
pequeno demais, com aparência inteiramente plausível: o `log()` do DuckDB
é logaritmo de **base 10**, não natural, e todos os coeficientes saíam
divididos por ln(10) ≈ 2,3. Um resultado plausível e errado é mais
perigoso que um obviamente quebrado, porque não convida a verificação.
Sem teste contra um valor verdadeiro conhecido, esse número teria ido
para o relatório final. `test_unidade_e_log_natural` existe para que não
volte.

---

## 10. Sobre a implementação do estimador

O projeto roda **dois** estimadores:

1. `rdrobust` (Calonico, Cattaneo, Farrell e Titiunik) — implementação de
   referência da literatura, disponível em Python (não é preciso `rpy2`).
   Banda MSE-ótima e inferência *robust bias-corrected*: o erro-padrão
   convencional subestima a incerteza quando a banda é escolhida pelo
   próprio dado. É o número que vai ao relatório.
2. Um estimador local-linear escrito à mão, kernel triangular, erros
   agrupados por lista.

Os dois são rodados na mesma banda e comparados a cada execução. A
estimativa pontual tem de coincidir — o coeficiente "Conventional" do
`rdrobust` **é** a regressão local-linear ponderada. Os erros-padrão
diferem de propósito. Divergência no ponto é bug de implementação, e o
teste `test_dois_estimadores_concordam` trava isso.

Agrupamento: as duas observações de fronteira da mesma lista não são
independentes — o corte de uma é definido pela votação da outra. O padrão
é agrupar por lista.

---

## 11. Desenho B — efeito do gasto sobre o voto (extensão)

Para atacar a direção original é preciso uma fonte de variação no
**dinheiro** que não venha da qualidade do candidato. Em ordem
decrescente de credibilidade:

**B1. Limites legais de gasto por faixa populacional.** O teto de gastos
varia por porte do município, com mudanças em limiares populacionais.
Municípios logo abaixo e logo acima de um limiar são comparáveis em quase
tudo, mas enfrentam tetos diferentes. É um RDD com farta tradição na
literatura brasileira de economia política. **Cuidado central:** o mesmo
limiar frequentemente move *várias* regras ao mesmo tempo — número de
cadeiras na câmara, teto de gastos, repasses. Se duas regras mudam no
mesmo ponto, o RDD identifica o efeito conjunto do pacote, não do teto
isoladamente. Verificar limiar a limiar antes de qualquer interpretação.

**B2. Regras de destinação do Fundo Eleitoral.** As normas de alocação
mínima do FEFC por gênero e, depois, por raça criam variação na
disponibilidade de recursos que não é função da qualidade individual, e
sim da composição da lista. Promissor, mas a exogeneidade é parcial: o
partido escolhe **como** distribuir dentro da cota, e essa escolha
reintroduz seleção. Exigiria variável instrumental, não RDD puro.

**B3. Descontinuidades no repasse do fundo partidário por desempenho
eleitoral prévio**, que introduzem saltos em função de resultados
passados.

**Recomendação prática:** B1 é o caminho mais defensável e o único que
vale abrir sem apoio de orientação acadêmica. Mesmo assim é um projeto
inteiro por si só, não um apêndice do Desenho A. A decisão consciente
deste repositório é entregar o Desenho A bem-feito antes de abrir o B.

---

## Referências para a leitura teórica

- Lee, D. S. (2008). *Randomized experiments from non-random selection in
  U.S. House elections*. Journal of Econometrics.
- Calonico, S., Cattaneo, M. D., & Titiunik, R. (2014). *Robust
  nonparametric confidence intervals for regression-discontinuity
  designs*. Econometrica.
- Cattaneo, M. D., Idrobo, N., & Titiunik, R. *A Practical Introduction to
  Regression Discontinuity Designs* (Cambridge Elements) — o guia
  aplicado mais direto para checar cada pressuposto.
- Cattaneo, M. D., Jansson, M., & Ma, X. *Simple local polynomial density
  estimators* — o teste de manipulação usado aqui, sucessor do McCrary.
- Lee, D. S. (2009). *Training, wages, and sample selection* — os limites
  para seleção de amostra citados na seção 3.
- Literatura brasileira sobre financiamento e retorno eleitoral, com
  atenção ao período pós-2015 (fim da doação de pessoa jurídica) e
  pós-2017 (criação do FEFC): as regras mudam entre ciclos e
  comparabilidade entre anos não pode ser assumida.
- Trabalhos sobre RDD em eleições proporcionais de lista aberta, para
  confrontar a construção do corte intra-lista adotada aqui.
