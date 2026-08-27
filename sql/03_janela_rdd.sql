-- =====================================================================
-- 03_janela_rdd.sql — amostra do desenho causal
--
-- Desenho principal (close-election RDD, Lee 2008):
--   variável de corte : margem de votos até o corte DENTRO da lista (02)
--   tratamento        : ter sido eleito em t (margem > 0)
--   desfecho          : dinheiro de campanha na eleição seguinte (t+1)
--
-- Estima o efeito causal de *vencer por um fio* sobre *quanto dinheiro
-- o candidato capta na eleição seguinte*. É a direção que estes dados
-- de fato identificam — e é exatamente o canal de causalidade reversa
-- que invalida a leitura ingênua de "gastou mais, elegeu-se mais".
-- Justificativa completa em docs/nota_metodologica_rdd.md.
-- =====================================================================

-- ---------------------------------------------------------------------
-- vw_amostra_rdd — amostra principal: toda candidatura com margem
-- definida. A largura de banda NÃO é fixada aqui de propósito: ela é
-- escolhida na camada de modelagem (rdd_model.py), por seleção ótima,
-- e varrida nos testes de robustez. Fixar h no SQL esconderia a
-- decisão mais sensível do desenho dentro do pipeline.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_amostra_rdd AS
SELECT *
FROM vw_margem_candidato
WHERE margem_rel_lista IS NOT NULL;

-- ---------------------------------------------------------------------
-- vw_amostra_fronteira — só o par (último eleito, primeiro suplente)
-- de cada lista. Amostra mais conservadora, usada como robustez: são
-- as unidades cujo status é mais claramente decidido "no fio".
-- ---------------------------------------------------------------------
-- Só entram listas que têm OS DOIS lados do par. Uma lista pode perder
-- um dos lados quando há empate exato em votos entre dois candidatos da
-- mesma lista (os empatados saem em 02, porque o desempate legal é por
-- idade): nesse caso sobra meio par, e meio par não é comparação.
CREATE OR REPLACE VIEW vw_amostra_fronteira AS
WITH pares_completos AS (
    SELECT id_lista_disputa
    FROM vw_amostra_rdd
    GROUP BY 1
    HAVING COUNT(*) FILTER (WHERE eh_ultimo_eleito)     >= 1
       AND COUNT(*) FILTER (WHERE eh_primeiro_suplente) >= 1
)
SELECT a.*
FROM vw_amostra_rdd a
JOIN pares_completos USING (id_lista_disputa)
WHERE a.eh_ultimo_eleito OR a.eh_primeiro_suplente;


-- ---------------------------------------------------------------------
-- vw_painel_rdd — candidatura em t ligada à candidatura da MESMA
-- PESSOA em t+1, via painel_link (ver python/analysis/build_panel.py).
--
-- LEFT JOIN de propósito: quem não voltou a concorrer é informação, não
-- linha perdida. Isso permite separar as duas margens:
--   extensiva : voltou a concorrer? (concorreu_t1)
--   intensiva : quanto captou, entre quem voltou (ln_receita_t1_cond)
-- Misturar as duas num único ln(1+receita) põe uma pilha de zeros no
-- meio de valores na casa de ln(receita) ~ 11, infla a variância e
-- transforma um efeito sobre captação num efeito sobre "continuar na
-- política" mal disfarçado.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_painel_rdd AS
SELECT
    t0.sq_candidato,
    t0.id_disputa,
    t0.id_lista_disputa,
    t0.ano_eleicao,
    t0.cargo,
    t0.uf,
    t0.municipio,
    t0.cd_municipio,
    t0.partido,
    t0.id_lista,
    t0.nome_urna,
    t0.genero,
    t0.cor_raca,
    t0.idade_posse,
    t0.st_reeleicao,
    t0.votos_nominais,
    t0.votos_nominais_lista,
    t0.cadeiras_da_lista,
    t0.n_candidatos_lista,
    t0.posicao_na_lista,
    t0.eleito,
    CASE WHEN t0.eleito THEN 1 ELSE 0 END       AS tratamento,
    t0.margem_votos,
    t0.margem_rel_lista,
    t0.margem_rel_disputa,
    t0.eh_ultimo_eleito,
    t0.eh_primeiro_suplente,

    -- covariáveis medidas em t (usadas nos testes de continuidade)
    t0.receita_total_real                       AS receita_t,
    t0.despesa_total_real                       AS despesa_t,
    ln(1 + t0.receita_total_real)               AS ln_receita_t,
    ln(1 + t0.despesa_total_real)               AS ln_despesa_t,
    t0.share_fefc                               AS share_fefc_t,
    t0.share_propria                            AS share_propria_t,
    t0.n_doadores_distintos                     AS n_doadores_t,

    l.nivel_match,
    t1.ano_eleicao                              AS ano_t1,

    -- desfechos em t+1
    (l.sq_t1 IS NOT NULL)                       AS concorreu_t1,
    COALESCE(t1.receita_total_real, 0)          AS receita_t1,
    COALESCE(t1.despesa_total_real, 0)          AS despesa_t1,
    COALESCE(t1.receita_fefc, 0)                AS fefc_t1,
    COALESCE(t1.receita_doacao_pf, 0)           AS doacao_pf_t1,
    t1.share_fefc                               AS share_fefc_t1,
    COALESCE(t1.votos_nominais, 0)              AS votos_t1,
    COALESCE(t1.eleito, FALSE)                  AS eleito_t1,
    -- margem intensiva: NULL para quem não concorreu, e não zero.
    -- ln() natural — em DuckDB log() é base 10, e usar log() aqui
    -- dividiria todos os coeficientes por ln(10) ≈ 2,3 sem quebrar
    -- nada visivelmente. Ver tests/test_rdd.py::test_unidade_e_log_natural.
    CASE WHEN t1.receita_total_real > 0
         THEN ln(t1.receita_total_real) END     AS ln_receita_t1_cond,
    ln(1 + COALESCE(t1.receita_total_real, 0))  AS ln_receita_t1
FROM vw_amostra_rdd t0
LEFT JOIN painel_link l         ON l.sq_t  = t0.sq_candidato
LEFT JOIN vw_financas_candidato t1 ON t1.sq_candidato = l.sq_t1;


-- ---------------------------------------------------------------------
-- vw_contagem_por_janela — quantas observações sobrevivem a cada
-- janela candidata. Serve para decidir se o recorte tem poder
-- estatístico ANTES de olhar qualquer estimativa.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_contagem_por_janela AS
SELECT
    h.janela,
    COUNT(*)                                        AS n_total,
    COUNT(*) FILTER (WHERE eleito)                  AS n_tratados,
    COUNT(*) FILTER (WHERE NOT eleito)              AS n_controles,
    COUNT(*) FILTER (WHERE concorreu_t1)            AS n_com_desfecho,
    COUNT(DISTINCT municipio)                       AS n_municipios
FROM vw_painel_rdd a
CROSS JOIN (SELECT UNNEST([0.005, 0.01, 0.02, 0.03, 0.05, 0.10]) AS janela) h
WHERE ABS(a.margem_rel_lista) <= h.janela
GROUP BY h.janela
ORDER BY h.janela;
