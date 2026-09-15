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
| 6 | Extensões (outras UFs, outros cargos, Desenho B) | não iniciada |

O recorte vereador/RS/2020→2024 está encerrado com resultado **NÃO
IDENTIFICADO** (ver `resultados.md`). O caminho crítico agora, se o
projeto continuar, é a fase 6 — mais ciclos eleitorais para aumentar o
poder estatístico da amostra.

**Nota sobre a validação de totais:** o DivulgaCandContas é um painel
carregado via JavaScript, sem endpoint agregável por busca automatizada
(só consulta individual por candidato). A validação foi feita por
plausibilidade: o gasto médio por candidato (R$ 2.304 em 2020, R$ 5.432
em 2024) fica bem abaixo do teto legal de R$ 85.811,91 por candidatura a
vereador no RS, como esperado; e o número de vereadores eleitos é quase
idêntico entre os dois anos (4.902 e 4.903), como deveria ser. Quem
quiser uma comparação direta pode abrir o painel manualmente para um
recorte específico.

## Próximos passos, em ordem

1. **`make inspecionar ANOS="2020 2024"`.** Compare a saída com `COLMAP`
   em `load_to_duckdb.py` e com `FONTES` em `download_tse.py`. O TSE
   renomeia arquivos e colunas entre anos; ajustar o mapeamento é
   manutenção esperada, não sinal de erro.

2. **`make dados ANOS="2020 2024"`** e conferir se os CSVs do RS foram
   extraídos nas três pastas (`candidatos`, `resultados`, `contas`).

3. **`make banco ANOS="2020 2024"`** e comparar os totais impressos com
   as estatísticas de prestação de contas publicadas pelo TSE
   (DivulgaCandContas). Divergência acima de ~2% indica problema de
   ingestão, não arredondamento. **Não avançar enquanto não baterem** —
   erro de carga aqui contamina tudo em silêncio.

   Atenção específica de 2018 vs. 2020: a EC 97/2017 vedou coligação
   proporcional a partir de 2020, então `SQ_COLIGACAO` muda de natureza
   entre os dois anos. Confirmar que `id_lista` continua identificando a
   unidade que disputa as cadeiras nos dois casos.

4. **Conferir manualmente umas dez listas.** Quem foi o último eleito,
   quem foi o primeiro suplente, qual a margem. É a única forma de ter
   certeza de que o corte intra-lista está certo no dado real — nenhum
   teste automatizado substitui isso na primeira execução.

5. **`make painel DE=2020 PARA=2024`** e olhar a taxa de pareamento por
   nível. Cobertura baixa compromete o desfecho e precisa ser reportada
   no relatório final, não escondida.

6. **Olhar `outputs/tabelas/rdd_contagem_por_janela.csv`.** Se as janelas
   estreitas tiverem poucas observações, expandir o recorte (mais anos,
   mais UFs) **antes** de olhar qualquer estimativa.

7. **Só então `make analise`.** Ler o veredito da seção 6 antes dos
   coeficientes.

8. Confrontar a estimativa principal com uma execução independente em R,
   se houver oportunidade. O `rdrobust` em Python é a mesma implementação
   de referência, então a divergência esperada é nula — mas conferir uma
   vez custa pouco.

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

1. **Mais ciclos eleitorais (2016, 2018, 2022).** É a extensão mais
   direta e a que mais provavelmente resolve a instabilidade na janela
   mais estreita observada em `resultados.md` — mais observações dão
   mais poder estatístico exatamente onde a amostra atual é fraca.
   Decisão a tomar **antes** de rodar de novo, não depois de ver se
   "ajuda" o resultado.
2. **Limites de Lee** para o efeito condicional a recandidatar-se, em
   vez de só reportar que a regra bloqueou por seleção de amostra.
3. **Demais UFs.** O código não tem nada específico do RS além de um
   argumento de linha de comando.
4. **Deputado estadual (2018, 2022).** A mesma lógica intra-lista se
   aplica; muda o tamanho da lista e a unidade geográfica.
5. **Modelar suplência.** Suplentes assumem cadeira com alguma
   frequência, o que atenua o efeito estimado. Tratar como tratamento
   parcial é um refinamento com literatura própria.
6. **Deflação mensal** por data de transação, em vez de índice anual.
7. **Desenho B** (efeito do gasto sobre voto) via limiares populacionais
   de teto de gasto — projeto próprio, ver nota metodológica, seção 11.
8. **Eleição de 2026**, quando as contas estiverem consolidadas. É
   atualização do pipeline existente, não projeto novo.
