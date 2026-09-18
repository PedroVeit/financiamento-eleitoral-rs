# Registro de decisões

Cada decisão de projeto que teve alternativa razoável, com o motivo da
escolha e o que a rejeitada custaria. Serve para quem lê o repositório
saber que a escolha foi feita, e não apenas herdada, e para eu mesmo não
refazer a discussão daqui a seis meses.

---

## D1 — A margem é calculada dentro da lista, não no ranking do município

**Alternativa rejeitada:** ordenar todos os candidatos da disputa por
voto e cortar na N-ésima vaga.

**Motivo:** vereador é eleito por lista aberta com quociente eleitoral.
As cadeiras vão primeiro para as listas e só depois para as pessoas.
Ranquear o município inteiro cria um limiar que não corresponde a
nenhuma regra: parte dos eleitos aparece do lado errado dele.

**Custo da rejeitada:** a variável de corte seria ruidosa e o tratamento
deixaria de ser função determinística dela — o pressuposto básico do RDD.

**Trava:** `test_margem_nao_usa_ranking_da_disputa` verifica que existem,
nos dados, eleitos fora do topo do ranking municipal. Se algum dia esse
teste falhar, ou o dado mudou de natureza ou alguém quebrou a view.

---

## D2 — O estimando é o efeito de eleger-se sobre o dinheiro futuro

**Alternativa rejeitada:** usar a margem de votos como variável de corte
e o gasto como tratamento, para estimar o efeito do gasto sobre a
eleição.

**Motivo:** o gasto acontece antes da votação e não salta no corte. O que
salta é *ser eleito*. Chamar o resultado de "efeito do gasto" seria
trocar o estimando pela pergunta.

**Custo da rejeitada:** um número sem interpretação causal, apresentado
como se tivesse uma.

**Detalhe:** a inversão não é prêmio de consolação. O efeito de eleger-se
sobre a arrecadação seguinte é exatamente o canal de causalidade reversa
que se usa para argumentar que a correlação gasto→voto não vale nada —
canal quase sempre assumido e quase nunca medido.

---

## D3 — Cadeiras da lista lidas do resultado observado, não remodeladas

**Alternativa rejeitada:** recalcular quantas cadeiras cada lista ganhou a
partir do quociente eleitoral e das sobras.

**Motivo:** remodelar a regra introduz erro de medida na variável de
**tratamento**, que é o pior lugar possível para ter erro de medida. O
número de eleitos por lista está no dado.

**Custo da rejeitada:** casos de cassação, substituição e decisão
judicial fariam o modelo divergir do resultado real, silenciosamente.

---

## D4 — Empates e inversões são descartados, e o descarte é contado

**Motivo:** no Brasil o empate é desempatado pela idade, não por votos —
nesses casos o tratamento não é função da variável de corte. Inversões
(não-eleito com mais votos que um eleito da mesma lista) vêm de cassação
e substituição, não de eleição decidida por votos.

**Como:** `vw_listas_descartadas` reporta quantas listas caem por cada
motivo, e a validação da carga imprime a tabela. Descarte silencioso é
como se perde metade da amostra sem ninguém notar.

---

## D5 — Margem extensiva e intensiva estimadas separadamente

**Alternativa rejeitada:** um único desfecho `ln(1 + receita)`, com zero
para quem não voltou a concorrer.

**Motivo:** isso põe uma pilha de zeros no meio de valores na casa de
ln(receita) ≈ 11. Infla a variância e transforma um efeito sobre captação
num efeito sobre "continuar na política" mal disfarçado.

**Consequência assumida:** o efeito intensivo é condicional a
recandidatar-se sempre que o extensivo for significativo — e a regra de
decisão (D9) aplica esse rótulo automaticamente.

---

## D6 — Dois estimadores, rodados e comparados a cada execução

**Alternativa rejeitada:** usar só `rdrobust`, ou só uma implementação
própria.

**Motivo:** `rdrobust` é a referência da literatura e faz correção de
viés que uma implementação caseira não faria direito. Mas um estimador
que ninguém consegue reproduzir na mão é um estimador em que ninguém
deveria confiar. Os dois rodam na mesma banda; a estimativa pontual tem
de coincidir, porque o coeficiente "Conventional" do `rdrobust` **é** a
regressão local-linear ponderada.

**Trava:** `test_dois_estimadores_concordam`.

---

## D7 — Pareamento entre eleições em cascata, com o nível registrado

**Alternativa rejeitada:** parear só por CPF, ou só por nome.

**Motivo:** o TSE deixou de publicar o CPF completo em parte dos
arquivos, então só CPF perde metade da amostra. Só nome erra em
homônimos. A cascata usa CPF quando existe e cai para nome quando não
existe, gravando qual regra produziu cada par.

**Regra dura:** ambiguidade é **descartada**, não resolvida por
heurística. Homônimo pareado errado vira efeito espúrio, e efeito
espúrio é pior que observação a menos.

**Consequência:** a análise principal usa só os níveis fortes (CPF e nome
+ município); os fracos entram como robustez. A taxa de cobertura é
reportada.

---

## D8 — Deflação na camada analítica, não na ingestão

**Motivo:** o banco precisa continuar auditável contra os totais que o
TSE publica, que são nominais. A deflação é uma view.

**Limitação declarada:** índice anual, não mensal por data de transação.
O schema guarda as datas para permitir o refinamento depois. Ano sem taxa
registrada **não** recebe fator 1 em silêncio — a validação acusa.

---

## D9 — Regras de decisão fixadas antes da execução, e automatizadas

**Alternativa rejeitada:** ler a bateria de robustez e decidir na hora se
o resultado "conta".

**Motivo:** decidir depois de ver o resultado é como se fabrica falso
positivo. As regras estão em `python/analysis/regras_decisao.py`, são
testadas isoladamente e rodam ao fim de todo pipeline, produzindo um
veredito de três valores.

**Tolerância a acaso:** testar seis covariáveis a 5% produz cerca de 0,3
falso positivo — uma falha é esperada e vira alerta; duas ou mais viram
bloqueio.

---

## D10 — Dados sintéticos saem como CSV no formato do TSE

**Alternativa rejeitada:** inserir os dados sintéticos direto nas tabelas
do banco.

**Motivo:** inserir direto testa o SQL analítico mas pula todo o caminho
de ingestão — parse de decimal com vírgula, encoding latin-1,
classificação de fonte de receita, soma de votos por zona. É justamente
onde mora o bug chato.

**Custo aceito:** a construção do banco de teste demora alguns segundos a
mais.

**Bônus:** o gerador injeta homônimos e omite o CPF de parte dos
registros, para que o pareamento (D7) tenha o que errar — e os testes,
o que pegar.

---

## D11 — SQL para o trabalho relacional, Python para o resto

**Motivo:** agregar milhões de lançamentos de receita e despesa, juntar
quatro tabelas e ranquear dentro de lista é exatamente o que um banco
colunar faz bem. Varrer isso em pandas seria mais lento e menos legível.
Python entra para ingestão, econometria e visualização.

**Regra prática:** nenhum CSV do TSE passa por um DataFrame. O DuckDB lê
o arquivo direto do disco.

---

## D12 — A amostra principal não é restrita ao par de fronteira

**Alternativa rejeitada:** usar só o último eleito e o primeiro suplente
de cada lista.

**Motivo:** restringir joga fora observações informativas e engessa a
escolha de banda, que é justamente o que o estimador deveria decidir. A
amostra principal é toda candidatura com margem definida, e a banda
MSE-ótima faz o recorte.

**Mas:** a amostra de fronteira roda como robustez
(`vw_amostra_fronteira`), com o par completo exigido — meio par não é
comparação.

---

## D13 — Correções encontradas na primeira carga de dados reais (RS, vereador, 2020/2024)

Quatro problemas apareceram só ao rodar contra o TSE de verdade — nenhum
aparecia nos dados sintéticos porque o simulador não reproduzia esses
comportamentos específicos do dado real. Registrados aqui para quem abrir
o código depois não estranhar os `#NE` e o piso de 9 dígitos.

**D13.1 — Coluna de ano em receitas/despesas é `AA_ELEICAO`, não
`ANO_ELEICAO`.** Só nesses dois arquivos; candidatos e resultados usam
`ANO_ELEICAO` normalmente. `COLMAP` agora aceita as duas alternativas.

**D13.2 — `DS_SITUACAO_CANDIDATURA` vem como `#NE` em 100% das linhas a
partir do ciclo 2022+.** O TSE parou de preencher esse campo no pacote
publicado após a eleição — ele só fazia sentido durante o período de
registro. A validade da candidatura já é garantida pelo `JOIN` com
`resultados` (só quem tinha candidatura válida aparece no arquivo de
votação), então o filtro agora aceita `#NE` como valor neutro, mantendo
a exclusão de `INAPTO` nos anos em que o campo é preenchido de verdade
(2020 e anteriores).

**D13.3 — `NR_CPF_CANDIDATO` vem como sentinela `-4` em 100% das linhas
de 2024.** Sem piso de tamanho, `-4` vira o dígito `4` depois de limpar
pontuação, e É tratado como documento válido — e como o sentinela é
igual para todo mundo, todo mundo ganharia o MESMO hash. `_hash_sql`
agora exige pelo menos 9 dígitos restantes (CPF tem 11, CNPJ tem 14; um
único dígito nunca é documento real). Consequência aceita: o pareamento
de painel entre 2020 e 2024 cai inteiramente para nível 2 (nome +
município) — o CPF de 2024 simplesmente não é publicado nesse recorte.

**D13.4 — `run_pipeline.py` apagava os dados reais ao rodar sem
`--sintetico`.** O caminho não-sintético chamava `criar_banco()`, que
roda `schema.sql` (que começa com `DROP TABLE` em tudo) — apropriado
para o modo sintético, que sempre quer recriar do zero, mas destrutivo
para o modo real, que espera um banco já populado por
`load_to_duckdb.py`. Corrigido para abrir uma conexão simples e só
reaplicar as views.

---

## D14 — Extensão: empilhar mais de um ciclo eleitoral (2016→2020, além de 2020→2024)

**Contexto do erro corrigido:** os documentos anteriores (`plano_execucao.md`,
`resultados.md`) sugeriam "2016, 2018, 2022" como próximos ciclos a
incluir. Isso estava errado: vereador é cargo **municipal**, eleito só em
anos múltiplos de 4 (2012, 2016, 2020, 2024...). 2018 e 2022 são eleições
**gerais** (presidente, governador, deputados, senadores) — não existe
candidatura a vereador nesses anos. `download_tse.py` e `load_to_duckdb.py`
agora emitem aviso explícito se alguém pedir um cargo municipal num ano
que não é múltiplo de 4, para que o engano não passe despercebido como
"0 candidaturas" silencioso.

**Motivo da extensão:** o veredito NÃO IDENTIFICADO (D13/`resultados.md`)
veio de instabilidade de sinal na janela mais estreita — sintoma clássico
de amostra pequena, não de efeito inexistente. Empilhar o painel
2016→2020 junto do 2020→2024 mais que dobra o n. Bônus: o CPF completo
só passou a ser mascarado a partir do arquivo de 2024 (2020 e 2016 devem
publicá-lo por completo), então o pareamento 2016→2020 deve conseguir
usar hash de CPF (nível 1) em vez de só nome+município — pareamento mais
confiável que o disponível hoje.

**Como o código já suporta isso, quase sem mudança:**
`vw_painel_rdd` junta `painel_link` por `sq_t = t0.sq_candidato`, e como
cada ano de origem gera seu próprio conjunto de pares em `painel_link`
(a chave é `(sq_t, sq_t1)`, sem relação entre pares de anos diferentes),
empilhar um segundo painel é só rodar `build_panel.py` de novo com outro
par de anos — nenhuma tabela é sobrescrita (`DELETE ... WHERE ano_t = ?
AND ano_t1 = ?` já é filtrado por par). `carregar_tse()` já aceita lista
de anos arbitrária.

**O que foi adicionado de verdade:** um teste de robustez novo,
`teste_heterogeneidade_por_ciclo` (`rdd_model.py`), que estima o efeito
separadamente para cada ano de origem empilhado e compara com o pooled.
Existe porque um efeito pooled poderia estar escondendo que ele só existe
num dos ciclos, ou que os ciclos discordam de sinal. A regra de decisão
(`regras_decisao.py`) só bloqueia se **dois ou mais ciclos forem
individualmente significativos com sinais opostos** — tratamento mais
permissivo que o da varredura de janela (que bloqueia com qualquer troca
de sinal), porque a varredura tem 7 pontos para revelar tendência,
enquanto aqui normalmente há só 2 ou 3 ciclos — um mero desacordo no
ponto estimado, sem que ambos sejam significativos, é compatível com
ruído esperado e vira alerta, não bloqueio.

**Cuidado de desenho já identificado, não resolvido:** uma pessoa que
disputou em 2016, 2020 e 2024 contribui **duas observações** ao painel
empilhado (2016→2020 e 2020→2024) — é o comportamento correto para RDD
empilhado em painel (cada transição eleição-a-eleição é uma unidade
válida), mas o agrupamento de erro-padrão atual (`id_lista_disputa`) não
captura a correlação entre as duas observações da MESMA pessoa em anos
diferentes. Não é bloqueante — listas de anos diferentes já são grupos
distintos — mas fica registrado como refinamento possível: agrupar por
pessoa (via `painel_link` encadeado) em vez de só por lista-disputa, se
o número de recandidatos múltiplos for grande o suficiente para importar.

**Testes adicionados:** `test_heterogeneidade_com_um_ciclo_so_nao_quebra`,
`test_heterogeneidade_com_dois_ciclos_simulados`,
`test_ausencia_de_coluna_ciclo_devolve_vazio` (`test_rdd.py`);
`test_regra_bloqueia_com_ciclos_significativos_e_opostos`,
`test_regra_alerta_com_sinais_diferentes_mas_nao_ambos_significativos`,
`test_regra_ignora_heterogeneidade_com_um_ciclo_so` (`test_pipeline.py`).
Suíte total: 52 testes.

---

## D15 — Formato legado de prestação de contas em 2016 (pré-padronização do TSE)

**O que apareceu:** ao inspecionar o pacote de contas de 2016, três
surpresas em cadeia:

1. **A URL do recurso é outra.** `prestacao_de_contas_eleitorais_candidatos_2016.zip`
   (o padrão usado desde 2020) simplesmente não existe para 2016. O nome
   certo é `prestacao_contas_final_2016.zip`.
2. **Os arquivos internos são `.txt`, não `.csv`.** O `inspecionar()` só
   filtrava `.csv` e por isso ficava mudo com o zip certo em mãos — bug
   real, corrigido (agora aceita as duas extensões, como `extrair()` já
   fazia).
3. **O cabeçalho é outro mundo.** Em vez de códigos ALLCAPS
   (`SQ_CANDIDATO`, `VR_RECEITA`...), o arquivo de 2016 usa nomes em
   português por extenso (`"Sequencial Candidato"`, `"Valor receita"`...)
   — formato anterior à padronização do TSE. Sem coluna de ano nenhuma
   (o ano vem do nome do pacote, não do dado).

**Armadilha extra dentro do próprio formato legado:** a coluna do número
do documento se chama **"Numero do documento"** (sem acento) no arquivo
de receitas e **"Número do documento"** (com acento) no de despesas —
inconsistência do próprio TSE dentro do mesmo ciclo. Um mapeamento único
compartilhado entre os dois arquivos teria silenciosamente perdido essa
coluna num dos dois.

**Correção:** `FORMATO_CONTAS_LEGADO` (dict por ano) registra prefixo de
arquivo e extensão especiais; `COLMAP_LEGADO_RECEITAS` /
`COLMAP_LEGADO_DESPESAS` mapeiam os nomes por extenso para os mesmos
conceitos internos (`sq_candidato`, `valor`, `data`, `doc_doador`...),
escritos por extenso em vez de compostos por concatenação de string —
mais fácil de auditar visualmente e de pegar a diferença de acentuação
entre os dois arquivos. `carregar_receitas`/`carregar_despesas` verificam
se o ano está no dict antes de decidir qual caminho seguir; todo o resto
do pipeline (schema, views, deflator, RDD) não muda nada.

**Por que a fonte de receita para 2016 é estruturalmente diferente, não
um bug:** 2016 é anterior à criação do Fundo Eleitoral de Campanha
(FEFC, 2017) e ao fim da doação de pessoa jurídica (2015). É esperado
que a composição de receita de 2016 mostre 0% de FEFC e uma presença de
doação de PJ que simplesmente não existe mais a partir de 2016 em diante
(a lei mudou no meio do próprio ano). Comparar composição de receita
entre 2016 e 2020/2024 tem que vir com essa ressalva no relatório —
não são apenas números diferentes, são regimes legais diferentes.

**Testado antes de rodar contra o dado real:** `test_carga_legado_receitas_e_despesas`
fabrica um arquivo `.txt` em miniatura com os dois cabeçalhos reais
(incluindo a diferença de acentuação) e confirma que valor, data,
classificação de fonte e tipo de documento saem corretos.
`test_glob_aceita_extensao_diferente_de_csv` trava a regressão do bug do
`.csv` fixo. Suíte total: 52 testes.

**Ainda não confirmado:** se 2012 usa o mesmo formato legado ou outro
diferente ainda. Não herdar a configuração de 2016 sem rodar
`--inspecionar` primeiro.

---

## D16 — `quote`/`escape` fixados explicitamente na leitura de CSV (não deixados para o sniffer do DuckDB)

**O que aconteceu:** ao carregar o `.txt` de despesas de 2016 (150 MB,
formato legado — D15), a carga voltou **0 linhas sem nenhum erro**. O
diagnóstico revelou que o autodetector de aspas do DuckDB errou o
caractere de aspas para esse arquivo específico: cada nome de coluna saiu
com as aspas **literais dentro do texto** (`'"Sequencial Candidato"'`, com
aspas inclusas, em vez de `'Sequencial Candidato'`). Como `_pick()`
procura pelo nome exato, nenhuma coluna bateu, a query rodou sem erro (o
`WHERE` simplesmente não casou linha nenhuma) e o retorno foi 0 — o pior
tipo de falha, silenciosa e sem traceback.

**Por que só apareceu em 2016:** o sniffer do DuckDB amostra só um pedaço
do arquivo para adivinhar delimitador/aspas/tipo. Em arquivos grandes o
suficiente (despesas de 2016 tem 150 MB), um trecho ambíguo dentro da
amostra basta para a detecção errar para o arquivo inteiro — mesmo que o
formato seja idêntico ao dos outros arquivos que carregaram certo.

**Correção:** `OPCOES_CSV` agora fixa `quote='"'` e `escape='"'`
explicitamente, em vez de deixar o DuckDB adivinhar. Todo arquivo do TSE
usado neste projeto — moderno ou legado — usa aspas duplas para
delimitar e escapar campos, então essa fixação é estritamente mais segura
que confiar em detecção automática, em qualquer ano passado ou futuro.

**Lição geral, para além deste bug específico:** qualquer parâmetro que
o DuckDB (ou qualquer parser) "adivinha" a partir de uma amostra do
arquivo é um candidato a falha silenciosa em arquivo grande o bastante.
Preferir fixar explicitamente sempre que o formato é conhecido e estável
— exatamente o mesmo princípio por trás de `COLMAP` (D13) e
`FORMATO_CONTAS_LEGADO`/`PADROES_ARQUIVO` (D15): não adivinhar o que já
se sabe.

---

## D17 — Classificação de fonte de receita em 2016 lia a coluna errada

**O que aconteceu:** depois de corrigir D16, a carga de 2016 completou sem
erro, mas a validação mostrou `fonte de receita não classificada:
140.820` — **92% das 153.587 receitas de 2016** caindo no balaio
"outros". Isso não era falha de reconhecer o texto (como em D13.2/D15):
era a coluna errada sendo lida.

`COLMAP_LEGADO_RECEITAS` mapeava `fonte` para `"Fonte recurso"`. Mas essa
coluna, no arquivo real de 2016, só tem **dois** valores possíveis:
`"Outros Recursos"` ou `"Fundo Partidario"` — grosseiro demais para
qualquer classificação útil. A categoria detalhada de verdade
(`"Recursos de pessoas físicas"`, `"Recursos próprios"`, `"Recursos de
partido político"`, `"Recursos de outros candidatos"`...) mora na coluna
**`"Tipo receita"`**, que não estava sendo lida em lugar nenhum.

**Correção:** `fonte` agora aponta para `"Tipo receita"`; `"Fonte
recurso"` (renomeado `fonte_coarse`) entra só em `origem_bruta`, para
auditoria, sem participar da classificação. Resultado esperado: das
140.820 antes não classificadas, ~140.590 se resolvem sozinhas (pessoa
física, próprio, partido, outros candidatos), sobrando só um resíduo
pequeno (~230, de categorias genuinamente residuais como "Doações pela
Internet" ou "Rendimentos de aplicações financeiras" — que são "outros"
de verdade, não erro de leitura).

**Como não caiu num teste antes:** o teste sintético original
(`test_carga_legado_receitas_e_despesas`, D15) tinha os valores de
exemplo **escritos com a suposição errada de qual coluna era qual** —
colocou o texto detalhado (`"Recursos de Pessoas Físicas"`) em "Fonte
recurso" e um texto genérico (`"Doação"`) em "Tipo receita". Isso
mascarou exatamente o bug: com aqueles dados de exemplo, ler a coluna
errada ainda "funcionava por acidente". A lição: dado sintético escrito
antes de ver o arquivo real corre o risco de codificar a mesma suposição
errada que o autor tinha na cabeça. `test_receita_legada_usa_tipo_receita_nao_fonte_recurso`
foi escrito **depois** de ver o arquivo real, com `"Fonte recurso"`
mantido **constante** (`"Outros Recursos"`) nas quatro linhas de teste e
só `"Tipo receita"` variando — replica o padrão real e não deixa
margem para esse tipo de acidente de novo.

**Suíte total: 53 testes.**
