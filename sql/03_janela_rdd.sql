CREATE OR REPLACE VIEW vw_amostra_rdd AS
SELECT *
FROM vw_margem_candidato
WHERE margem_rel_lista IS NOT NULL;


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

    
    CASE WHEN t1.receita_total_real > 0
         THEN ln(t1.receita_total_real) END     AS ln_receita_t1_cond,
    ln(1 + COALESCE(t1.receita_total_real, 0))  AS ln_receita_t1
FROM vw_amostra_rdd t0
LEFT JOIN painel_link l         ON l.sq_t  = t0.sq_candidato
LEFT JOIN vw_financas_candidato t1 ON t1.sq_candidato = l.sq_t1;



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
