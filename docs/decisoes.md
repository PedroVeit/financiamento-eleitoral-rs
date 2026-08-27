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
