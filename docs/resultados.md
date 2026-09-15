# Resultado: efeito de eleger-se sobre o financiamento futuro

**Recorte:** Vereador, Rio Grande do Sul, eleições de 2020 e 2024.
**Rodado em:** dados reais do TSE (Portal de Dados Abertos), carga e
análise descritas em `docs/plano_execucao.md` e `docs/decisoes.md`.

---

## Veredito

> **NÃO IDENTIFICADO**, pela regra de decisão pré-registrada em
> `python/analysis/regras_decisao.py` (nota metodológica, seção 8).

Isto não é "o projeto falhou". É o resultado correto de uma regra que
foi fixada **antes** de qualquer execução, exatamente para impedir que a
leitura do resultado seja escolhida depois de vê-lo. A seção
["Leitura honesta"](#leitura-honesta-do-que-os-números-sugerem) abaixo
explica o que dá para dizer mesmo assim.

### Por que o veredito bloqueou

**1. O efeito trocou de sinal entre janelas.** Na varredura de
robustez (variando a largura da banda ao redor do corte):

| janela (h) | n | τ estimado | erro-padrão | p |
|---|---|---|---|---|
| 0,005 | 346 | **−0,098** | 0,295 | 0,74 |
| 0,010 | 708 | +0,111 | 0,177 | 0,53 |
| 0,020 | 1.323 | +0,147 | 0,114 | 0,20 |
| 0,030 | 1.907 | +0,121 | 0,091 | 0,18 |
| 0,050 | 2.980 | +0,137 | 0,073 | 0,059 |
| 0,080 | 4.305 | +0,160 | 0,059 | **0,007** |
| 0,120 | 5.439 | +0,149 | 0,052 | **0,004** |

A única janela negativa é a mais estreita (346 observações — pouca
massa para estimar qualquer coisa com precisão), e a partir da segunda
janela em diante o efeito é sempre positivo e ganha significância
conforme a amostra cresce. Tem cara de ruído de amostra pequena, não de
efeito genuinamente instável — mas a regra pré-registrada não distingue
isso: qualquer troca de sinal bloqueia, de propósito, para não abrir
brecha de "esse ponto não conta".

**2. Seleção na recandidatura.** Ser eleito em 2020 aumenta em 6,1
pontos percentuais a chance de disputar de novo em 2024 (τ = +0,061,
IC95 [+0,008, +0,096], p = 0,020). Isso confirma o que a nota
metodológica já previa (seção 3): o efeito sobre receita só é observado
para quem voltou a concorrer, então mesmo sem o problema da varredura,
o resultado teria que ser rotulado como **condicional a
recandidatar-se**, nunca como efeito incondicional sobre a população
inteira de candidatos.

---

## Estimativa principal

**Desfecho:** ln(receita de campanha em 2024), só entre quem se
recandidatou — a margem intensiva (ver nota metodológica, seção 3).

| | valor |
|---|---|
| τ̂ (rdrobust, banda MSE-ótima) | **+0,156** |
| IC95% (robusto, bias-corrected) | [−0,013, +0,363] |
| erro-padrão | 0,096 |
| p-valor | 0,068 |
| banda (h) | 0,091 |
| n | 4.662 (2.270 tratados / 2.392 controles) |

Interpretação literal, se o IC95% fosse tomado ao pé da letra: candidatos
que se elegeram por pouco em 2020 e voltaram a concorrer em 2024
captaram entre 1,3% a menos e 44% a mais de receita, com estimativa
central de ~17% a mais (exp(0,156)−1). O intervalo cruza zero por pouco
— o resultado está no limiar da significância convencional de 5%.

---

## Bateria de robustez — resumo

| Teste | Resultado | Leitura |
|---|---|---|
| Dois estimadores (rdrobust vs. local-linear) | τ idêntico: 0,155705 nos dois | motor de cálculo correto |
| Densidade no corte (manipulação) | p = 0,82 | sem indício de manipulação |
| Cortes placebo (6 pontos sem regra) | nenhum significativo | não há "efeito fantasma" em pontos arbitrários |
| Donut (exclui observações coladas no corte) | τ estável: 0,156 → 0,168 → 0,148 | efeito não depende de casos colados no corte |
| Normalização alternativa (margem/disputa vs. margem/lista) | τ cai para 0,120, deixa de ser significativo | sensível à normalização — ver limitação abaixo |
| Amostra restrita à fronteira da lista | τ = 0,197, **p = 0,044** | fica significativo na amostra mais conservadora |
| Continuidade de covariáveis pré-tratamento | 4 de 5 passam; `share_fefc_t` não computou (matriz quase singular) | sem evidência de descontinuidade nas que rodaram |

---

## Leitura honesta do que os números sugerem

Apesar do veredito formal ser "não identificado", o conjunto de
evidências **não é de dado quebrado** — é de **efeito possivelmente real,
mas fraco e no limite do que esta amostra consegue provar**:

- O sinal é consistentemente positivo em 6 das 7 janelas testadas, e cresce em precisão conforme a amostra aumenta.
- Os dois estimadores concordam ponto a ponto.
- Nenhum dos testes de invalidação (placebo, densidade, donut) encontrou problema.
- Na amostra mais conservadora possível (só o par direto último-eleito × primeiro-suplente), o efeito é significativo.

A leitura mais defensável é: **o desenho é válido, mas a amostra —
vereador do RS, duas eleições — não tem poder estatístico suficiente
para satisfazer a robustez que a regra pré-registrada exige.** É uma
limitação de tamanho de amostra, não do método.

### O que isso significaria, se confirmado com mais dados

Um efeito positivo de eleger-se sobre a receita futura é, na prática, a
medição direta do canal de causalidade reversa que motiva o projeto
inteiro (nota metodológica, seção 1): parte da correlação observada
entre "gastar mais" e "vencer" existe porque **vencer atrai mais
dinheiro depois**, não porque o dinheiro comprou o voto antes. Este
resultado, mesmo não identificado com a robustez exigida, aponta na
direção de que esse canal existe e não é desprezível — mas não permite
quantificá-lo com confiança nesta amostra.

---

## Limitações específicas desta execução

1. **Pareamento entre eleições é só por nome + município** (nível 2 da
   cascata). O TSE não publica o CPF completo de candidatos a partir de
   2024 (ver `docs/decisoes.md`, D13.3), então o nível 1 (CPF) não
   contribuiu nenhum par. O nível 2 ainda é considerado forte o
   suficiente para a análise principal, mas é mais frágil que CPF —
   ver nota metodológica, seção 7, item 5.
2. **Cobertura de pareamento: 30,2%** das candidaturas de 2020
   encontraram par em 2024. É plausível para vereador (a maioria não se
   recandidata), mas reduz a amostra do desfecho de 29.839 candidaturas
   para 7.884 com desfecho observado.
3. **`share_fefc_t1`** não pôde ser estimado (erro numérico de matriz
   quase singular no `rdrobust`) — a participação do Fundo Eleitoral na
   receita é quase constante perto do corte, com pouca variação para o
   estimador trabalhar. Não bloqueia a conclusão principal.
4. **Duas eleições apenas.** O recorte (RS, vereador, 2020→2024) é o
   mínimo necessário para o desenho funcionar. Mais anos (2016→2020,
   2012→2016) aumentariam a amostra e são a extensão mais óbvia — ver
   próximos passos.

---

## Próximos passos possíveis

Nenhum destes é necessário para o projeto ser considerado completo — a
resposta "não identificado, mas com sinal sugestivo" já é uma resposta
publicável. São extensões, em ordem de custo-benefício:

1. **Adicionar mais ciclos eleitorais** (2016, 2018, 2022) para
   aumentar o n e testar se a instabilidade na janela mais estreita
   desaparece com mais dados. Esta é uma decisão a ser tomada **antes**
   de rodar de novo, não depois de ver se "ajuda" o resultado.
2. **Calcular limites de Lee** para o efeito condicional a
   recandidatar-se, em vez de reportar apenas o efeito não-condicional
   bloqueado pela regra.
3. **Expandir para outras UFs** — o código já é parametrizado por UF e
   cargo, então é reduzir a fricção operacional (mais tempo de
   download/carga), não reescrever lógica.
