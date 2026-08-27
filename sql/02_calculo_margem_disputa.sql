-- =====================================================================
-- 02_calculo_margem_disputa.sql — variável de corte (running variable)
--
-- PONTO CENTRAL DO PROJETO. LEIA ANTES DE USAR.
-- ---------------------------------------------------------------------
-- Em eleição proporcional (vereador, deputado estadual/federal) o
-- candidato NÃO é eleito por estar entre os N mais votados da disputa:
--
--   1. O quociente eleitoral e a distribuição de sobras definem quantas
--      cadeiras (S) cada LISTA (partido / federação / coligação) ganhou.
--   2. Dentro da lista, as cadeiras vão para os S candidatos mais
--      votados nominalmente.
--   3. Logo, entre o S-ésimo e o (S+1)-ésimo candidato DA MESMA LISTA
--      existe um corte determinístico e afiado (sharp RD).
--
-- Consequência: ordenar todos os candidatos do município por voto e
-- cortar na N-ésima vaga produz um limiar FICTÍCIO. Um candidato com
-- 900 votos pode se eleger enquanto outro com 1.500 não se elege, se
-- estiverem em listas diferentes — e boa parte dos eleitos aparece do
-- lado errado desse corte inventado. O teste
-- `test_margem_nao_usa_ranking_da_disputa` documenta o fenômeno.
--
-- O par comparável é: último eleito da lista × primeiro suplente da
-- MESMA lista. Mesma legenda, mesmo município, mesmo ano, mesma regra,
-- disputando literalmente a mesma cadeira.
--
-- S é lido do resultado OBSERVADO (contagem de eleitos por lista), não
-- remodelado a partir do quociente — remodelar reintroduziria erro de
-- medida na variável de tratamento.
-- =====================================================================


-- ---------------------------------------------------------------------
-- Passo 1 — posição de cada candidatura dentro da própria lista
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_rank_lista AS
SELECT
    f.*,
    concat_ws('-', f.ano_eleicao, f.turno, f.cargo, f.uf,
              COALESCE(f.municipio, 'UF'))              AS id_disputa,
    concat_ws('-', f.ano_eleicao, f.turno, f.cargo, f.uf,
              COALESCE(f.municipio, 'UF'), f.id_lista)  AS id_lista_disputa,

    ROW_NUMBER() OVER (
        PARTITION BY f.ano_eleicao, f.turno, f.cargo, f.uf, f.municipio, f.id_lista
        ORDER BY f.votos_nominais DESC, f.sq_candidato   -- desempate determinístico
    ) AS posicao_na_lista,

    COUNT(*) OVER (
        PARTITION BY f.ano_eleicao, f.turno, f.cargo, f.uf, f.municipio, f.id_lista
    ) AS n_candidatos_lista,

    -- cadeiras efetivamente conquistadas pela lista (observado)
    SUM(CASE WHEN f.eleito THEN 1 ELSE 0 END) OVER (
        PARTITION BY f.ano_eleicao, f.turno, f.cargo, f.uf, f.municipio, f.id_lista
    ) AS cadeiras_da_lista,

    SUM(f.votos_nominais) OVER (
        PARTITION BY f.ano_eleicao, f.turno, f.cargo, f.uf, f.municipio, f.id_lista
    ) AS votos_nominais_lista,

    SUM(f.votos_nominais) OVER (
        PARTITION BY f.ano_eleicao, f.turno, f.cargo, f.uf, f.municipio
    ) AS votos_nominais_disputa,

    -- empates exatos em votos: o desempate legal é por idade, não por
    -- voto. Nesses casos o tratamento deixa de ser função só da
    -- variável de corte e o desenho sharp não vale.
    COUNT(*) OVER (
        PARTITION BY f.ano_eleicao, f.turno, f.cargo, f.uf, f.municipio,
                     f.id_lista, f.votos_nominais
    ) AS n_empatados
FROM vw_financas_candidato f;


-- ---------------------------------------------------------------------
-- Passo 2 — os dois candidatos que definem o corte em cada lista
--   v_ultimo_eleito     = votos do eleito MENOS votado da lista
--   v_primeiro_suplente = votos do não-eleito MAIS votado da lista
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_corte_lista_bruto AS
SELECT
    ano_eleicao, turno, cargo, uf, municipio, id_lista, id_lista_disputa,
    MIN(votos_nominais) FILTER (WHERE eleito)     AS v_ultimo_eleito,
    MAX(votos_nominais) FILTER (WHERE NOT eleito) AS v_primeiro_suplente,
    COUNT(*) FILTER (WHERE eleito)                AS cadeiras_da_lista,
    COUNT(*) FILTER (WHERE NOT eleito)            AS n_nao_eleitos
FROM vw_rank_lista
GROUP BY ALL;

-- Corte válido = estritamente positivo. Três situações caem fora, de
-- propósito, e cada descarte é contado em vw_listas_descartadas:
--   (a) lista sem nenhum eleito, ou sem nenhum não-eleito: não há
--       contrafactual interno, não existe corte observável;
--   (b) EMPATE no corte (v_ultimo_eleito = v_primeiro_suplente): o
--       desempate é por idade, não por votos;
--   (c) INVERSÃO (não-eleito com mais votos que um eleito da mesma
--       lista): vem de cassação, substituição, indeferimento posterior.
--       Não é eleição decidida por votos.
CREATE OR REPLACE VIEW vw_corte_lista AS
SELECT * FROM vw_corte_lista_bruto
WHERE v_ultimo_eleito IS NOT NULL
  AND v_primeiro_suplente IS NOT NULL
  AND v_ultimo_eleito > v_primeiro_suplente;

CREATE OR REPLACE VIEW vw_listas_descartadas AS
SELECT
    CASE
        WHEN v_ultimo_eleito IS NULL                       THEN 'sem eleito na lista'
        WHEN v_primeiro_suplente IS NULL                   THEN 'sem nao-eleito na lista'
        WHEN v_ultimo_eleito = v_primeiro_suplente         THEN 'empate no corte'
        ELSE                                                    'inversao (eleito com menos votos)'
    END                                    AS motivo,
    COUNT(*)                               AS n_listas
FROM vw_corte_lista_bruto
WHERE v_ultimo_eleito IS NULL
   OR v_primeiro_suplente IS NULL
   OR v_ultimo_eleito <= v_primeiro_suplente
GROUP BY 1;


-- ---------------------------------------------------------------------
-- Passo 3 — a variável de corrida
--
--   margem_votos > 0  <=>  candidato eleito
--   margem_votos < 0  <=>  candidato não eleito
--
-- Duas normalizações são gravadas. A análise principal usa
-- margem_rel_lista (denominador = votos nominais da lista), convenção
-- mais comum na literatura de RDD em lista aberta; margem_rel_disputa
-- entra como teste de robustez. A conclusão não pode depender da
-- escolha de normalização, e isso é verificado.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_margem_candidato AS
SELECT
    r.*,
    k.v_ultimo_eleito,
    k.v_primeiro_suplente,

    CASE WHEN r.eleito
         THEN r.votos_nominais - k.v_primeiro_suplente   -- folga com que passou
         ELSE r.votos_nominais - k.v_ultimo_eleito       -- folga que faltou (negativa)
    END AS margem_votos,

    (CASE WHEN r.eleito
          THEN r.votos_nominais - k.v_primeiro_suplente
          ELSE r.votos_nominais - k.v_ultimo_eleito
     END)::DOUBLE / NULLIF(r.votos_nominais_lista, 0)    AS margem_rel_lista,

    (CASE WHEN r.eleito
          THEN r.votos_nominais - k.v_primeiro_suplente
          ELSE r.votos_nominais - k.v_ultimo_eleito
     END)::DOUBLE / NULLIF(r.votos_nominais_disputa, 0)  AS margem_rel_disputa,

    -- o par exatamente na fronteira da lista
    (r.eleito     AND r.votos_nominais = k.v_ultimo_eleito)     AS eh_ultimo_eleito,
    (NOT r.eleito AND r.votos_nominais = k.v_primeiro_suplente) AS eh_primeiro_suplente
FROM vw_rank_lista r
JOIN vw_corte_lista k USING (id_lista_disputa)
WHERE r.n_empatados = 1;    -- descarta empates exatos dentro da lista


-- ---------------------------------------------------------------------
-- Passo 4 — testes de consistência interna.
-- Se qualquer uma destas views retornar linha, o pipeline está
-- quebrado e a análise causal NÃO deve ser rodada. Rodadas em tests/
-- e em validar() na carga.
-- ---------------------------------------------------------------------

-- O sinal da margem tem que reproduzir exatamente o status de eleito.
CREATE OR REPLACE VIEW vw_check_sinal_margem AS
SELECT sq_candidato, ano_eleicao, municipio, id_lista,
       posicao_na_lista, cadeiras_da_lista, votos_nominais, margem_votos, eleito
FROM vw_margem_candidato
WHERE (margem_votos > 0 AND NOT eleito)
   OR (margem_votos < 0 AND eleito)
   OR (margem_votos = 0);

-- A folga do último eleito e a do primeiro suplente são a mesma
-- distância, com sinais opostos. Assimetria = bug no cálculo do corte.
CREATE OR REPLACE VIEW vw_check_simetria_margem AS
SELECT
    id_lista_disputa,
    MAX(margem_votos) FILTER (WHERE eh_ultimo_eleito)     AS margem_pos,
    MIN(margem_votos) FILTER (WHERE eh_primeiro_suplente) AS margem_neg
FROM vw_margem_candidato
GROUP BY id_lista_disputa;
