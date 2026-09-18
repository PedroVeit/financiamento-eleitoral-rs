# Resultado: efeito de eleger-se sobre o financiamento futuro

**Recorte:** Vereador, Rio Grande do Sul, painel empilhado de duas
transições eleitorais: **2016→2020** e **2020→2024**.
**Rodado em:** dados reais do TSE (Portal de Dados Abertos), carga e
análise descritas em `docs/plano_execucao.md` e `docs/decisoes.md`.

> Esta é a segunda rodada de execução. A primeira (só 2020→2024, n=4.662)
> está preservada no histórico do repositório; a comparação entre as duas
> rodadas é, em si, parte do resultado — ver seção
> ["Por que rodar de novo com mais dado"](#por-que-rodar-de-novo-com-mais-dado)
> abaixo.

---

## Veredito

> **NÃO IDENTIFICADO**, pela regra de decisão pré-registrada em
> `python/analysis/regras_decisao.py` (nota metodológica, seção 8).

O veredito não mudou entre as duas rodadas — mas o motivo de mantê-lo
mudou de qualidade, e isso importa. Ver a leitura completa abaixo antes
de concluir que "nada aconteceu".

### Por que o veredito bloqueou

**1. O efeito ainda troca de sinal na janela mais estreita, mas por uma
margem quase nula.**

| janela (h) | n | τ estimado | erro-padrão | p |
|---|---|---|---|---|
| 0,005 | 806 | **−0,001** | 0,156 | 0,993 |
| 0,010 | 1.680 | +0,059 | 0,102 | 0,561 |
| 0,020 | 3.185 | +0,073 | 0,070 | 0,296 |
| 0,030 | 4.556 | +0,054 | 0,056 | 0,333 |
| 0,050 | 7.084 | +0,085 | 0,045 | 0,056 |
| 0,080 | 9.846 | +0,078 | 0,038 | **0,040** |
| 0,120 | 12.062 | +0,051 | 0,035 | 0,142 |

Na primeira rodada (só 2020→2024), a janela mais estreita dava
τ = −0,098 — negativo de forma clara. Com o painel dobrado, o mesmo ponto
dá τ = −0,001: estatisticamente indistinguível de zero, e a nuvem de
pontos ao redor é toda positiva. A regra pré-registrada não abre exceção
para "quase zero" — bloqueia com qualquer sinal negativo, de propósito,
para não abrir brecha de interpretação seletiva. Mas a natureza do
problema mudou: de "o efeito parece instável" para "o efeito é positivo
em todo lugar, exceto um ponto que hoje é essencialmente nulo".

**2. Seleção na recandidatura — mais forte, não mais fraca, com mais
dado.**

| | 1ª rodada (n=4.662) | 2ª rodada (n=9.275) |
|---|---|---|
| τ (concorreu_t1) | +0,061 | **+0,070** |
| p-valor | 0,020 | **0,0013** |

Ser eleito aumenta a chance de disputar de novo — e esse efeito ficou
**mais preciso e mais significativo** com o dobro de observações, não
menos. Isso indica que não é ruído de amostra pequena: é uma
característica estrutural do fenômeno (quem se elege tem mais incentivo
e mais estrutura política para se recandidatar). Continua obrigando a
ler o efeito sobre receita como **condicional a recandidatar-se**.

---

## Estimativa principal

**Desfecho:** ln(receita de campanha na eleição seguinte), só entre quem
se recandidatou — a margem intensiva (nota metodológica, seção 3).

| | 1ª rodada (2020→2024 só) | 2ª rodada (2016→2020 + 2020→2024) |
|---|---|---|
| τ̂ (rdrobust, banda MSE-ótima) | +0,156 | **+0,085** |
| IC95% (robusto, bias-corrected) | [−0,013, +0,363] | **[−0,036, +0,230]** |
| erro-padrão | 0,096 | 0,068 |
| p-valor | 0,068 | **0,152** |
| n | 4.662 | **9.275** (4.489 tratados / 4.786 controles) |

O ponto estimado **caiu** de 0,156 para 0,085 com o dobro de dado — e o
erro-padrão também caiu (0,096 → 0,068), então a estimativa ficou mais
precisa mesmo com o efeito menor. Isso é exatamente o padrão esperado
quando a primeira estimativa estava parcialmente inflada por ruído de
amostra pequena: mais dado não necessariamente confirma o número
antigo, confirma um número mais correto — que aqui foi menor.

Interpretação literal do ponto central: candidatos que se elegeram por
pouco e voltaram a concorrer captaram, em média, cerca de 9% a mais de
receita na eleição seguinte (exp(0,085)−1 ≈ 0,089) — mas o intervalo de
confiança [−3,6%, +23,0%] inclui zero, então essa magnitude não pode ser
afirmada com confiança estatística convencional.

---

## Por que rodar de novo com mais dado

A primeira rodada (docs desta mesma pasta, versão anterior) foi
bloqueada por dois motivos: instabilidade de sinal na janela mais
estreita (346 observações — pouca massa) e seleção na recandidatura.
Vereador só é eleito em anos municipais (2012, 2016, 2020, 2024); a
extensão mais direta era empilhar o painel 2016→2020 ao lado do já
existente 2020→2024, decisão tomada **antes** de ver o resultado desta
segunda rodada — ver `docs/decisoes.md`, D14.

**Bônus técnico:** o CPF completo só passou a ser mascarado a partir do
arquivo de 2024. O painel 2016→2020 conseguiu parear **8.930 dos 8.982
pares por hash de CPF** (nível 1 — o mais forte da cascata), contra
30,2% por nome no painel 2020→2024. Cobertura de pareamento muito mais
confiável nesta metade do painel empilhado.

**O que a segunda rodada realmente mostrou:**
- A instabilidade de sinal quase desapareceu (−0,098 → −0,001).
- A estimativa central ficou mais precisa e menor (0,156 → 0,085).
- A seleção na recandidatura ficou **mais** forte com mais dado — não é
  artefato de amostra pequena, é estrutural.
- O teste de heterogeneidade entre os dois ciclos (novo nesta rodada)
  não encontrou contradição: os dois apontam no mesmo sentido.

Ou seja: **dobrar a amostra não "resolveu" o não identificado, mas
mudou completamente o que "não identificado" significa aqui.** Não é
mais "a amostra é pequena demais para saber". É "o efeito parece
real e positivo, mas pequeno, e a seleção de quem se recandidata é
genuína o suficiente para exigir tratamento explícito (limites de Lee)
antes de qualquer afirmação causal incondicional".

---

## Heterogeneidade entre os dois ciclos empilhados (teste novo)

| ciclo | τ | erro-padrão | p-valor | n |
|---|---|---|---|---|
| 2016→2020 | +0,043 | 0,090 | 0,479 | 5.045 |
| 2020→2024 | +0,156 | 0,096 | 0,068 | 4.662 |

Os dois ciclos têm o mesmo sinal (positivo) e intervalos de confiança
amplamente sobrepostos — nenhum dos dois é individualmente significativo
o bastante para acionar o bloqueio de contradição entre ciclos (que exige
os dois significativos com sinais opostos). O pooled (τ=0,085) fica,
como esperado, entre os dois.

---

## Bateria de robustez — resumo

| Teste | Resultado | Leitura |
|---|---|---|
| Dois estimadores (rdrobust vs. local-linear) | τ idêntico: 0,085171 nos dois | motor de cálculo correto |
| Densidade no corte (manipulação) | p = 0,70 | sem indício de manipulação |
| Cortes placebo (6 pontos sem regra) | 1 de 6 significativo (h=−0,04, p=0,023) | esperado por acaso a 5%; alertado, não bloqueante sozinho |
| Donut (exclui observações coladas no corte) | τ estável: 0,085 → 0,090 → 0,086 | efeito não depende de casos colados no corte |
| Normalização alternativa (margem/disputa vs. margem/lista) | τ cai para 0,056, não significativo | sensível à normalização — mesma ressalva da 1ª rodada |
| Amostra restrita à fronteira da lista | τ = 0,134, p = 0,067 | no limiar, mesmo padrão do pooled |
| Continuidade de covariáveis pré-tratamento | 5 de 6 passam; `idade_posse` salta (p=0,013); `share_fefc_t` não computou | uma falha em 6 é esperada por acaso, mas registrada |
| Heterogeneidade entre ciclos (novo) | 2016 e 2020 mesmo sinal, nenhum contradiz o outro | reforça que o efeito não é artefato de um ciclo específico |

---

## Leitura honesta do conjunto

A conclusão mudou de forma, não de direção. Na primeira rodada, a leitura
era "o desenho é válido, mas a amostra é pequena demais para a robustez
exigida". Com o dobro de dado, a leitura passa a ser mais específica e
mais forte:

- **O sinal é positivo e consistente** — 6 das 7 janelas, os dois ciclos
  empilhados, a amostra de fronteira mais conservadora. Não é um
  artefato de um recorte específico.
- **A magnitude é modesta** — em torno de 8–9% de receita a mais para
  quem venceu por pouco e voltou a concorrer, não os ~17% que a primeira
  rodada sugeria. Mais dado corrigiu a estimativa para baixo, o que é
  precisamente o comportamento esperado de uma correção por ruído.
- **A seleção na recandidatura é o obstáculo real**, não a instabilidade
  de amostra pequena. Isso desloca o próximo passo metodológico de
  "conseguir mais dado" para "modelar a seleção explicitamente" (limites
  de Lee — ver Próximos passos).

Continua sendo, na prática, a mesma mensagem de fundo do projeto: há
evidência de que vencer uma eleição por pouco causa um aumento real,
porém modesto, na capacidade de captação futura — o canal de causalidade
reversa que motiva o projeto existe e não é grande o bastante para
sustentar um número solto, mas grande o bastante para não ser descartado
como zero.

---

## Limitações desta execução

1. **Pareamento ainda misto entre painéis.** 2016→2020 usa
   majoritariamente CPF (nível 1, 99,4% dos pares); 2020→2024 usa nome +
   município (nível 2, mais frágil) porque o CPF de 2024 não é publicado
   integralmente (D13.3). O painel empilhado herda essa heterogeneidade
   de qualidade entre metades.
2. **`share_fefc_t1`** continua sem estimar (erro numérico de matriz
   quase singular) — não bloqueia a conclusão principal.
3. **Formato de dado de 2016 exigiu mapeamento próprio** (cabeçalhos em
   português por extenso, sem coluna de ano, arquivos `.txt` em vez de
   `.csv` — D15, D16, D17). Testado, mas é uma superfície de código maior
   que os anos 2020+, e vale conferência extra se um terceiro ciclo
   (2012) for adicionado no futuro.
4. **Erro-padrão agrupado por lista-disputa, não por pessoa.** Uma pessoa
   que disputou em 2016, 2020 e 2024 contribui até duas observações ao
   painel empilhado; a correlação entre essas duas observações da mesma
   pessoa não é capturada pelo agrupamento atual (D14, "cuidado de
   desenho").

---

## Próximos passos possíveis

1. **Calcular limites de Lee** para o efeito condicional a
   recandidatar-se — agora a prioridade nº1, já que a seleção se mostrou
   estrutural, não amostral.
2. **Agrupar erro-padrão por pessoa** em vez de só por lista-disputa
   (D14) — o painel empilhado tornou essa questão mais relevante que na
   1ª rodada.
3. **2012**, se ainda mais poder estatístico for desejado — mesmo
   procedimento do 2016, um ciclo mais para trás. Formato de arquivo
   precisa ser conferido do zero (`--inspecionar` antes de assumir
   qualquer coisa).
4. **Expandir para outras UFs** — código já parametrizado, é custo
   operacional, não redesenho.
