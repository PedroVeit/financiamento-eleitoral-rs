-- =====================================================================
-- 04_contexto_sistema.sql — contexto estrutural, sem nenhum recorte
-- por partido ou candidato.
--
-- Duas perguntas descritivas que conectam o resultado causal ao debate
-- público sobre financiamento eleitoral:
--
--   1. Quanto do dinheiro de campanha é público (Fundo Eleitoral +
--      Fundo Partidário), por eleição?
--   2. Qual a vantagem BRUTA de arrecadação de quem venceu sobre quem
--      perdeu, na eleição seguinte? Este é o número que costuma circular
--      no debate — e que mistura efeito do mandato com seleção (quem
--      venceu já era mais competitivo). O RDD isola só o primeiro.
-- =====================================================================

CREATE OR REPLACE VIEW vw_ctx_financiamento_publico AS
SELECT
    ano_eleicao,
    COUNT(*)                                                    AS candidaturas,
    SUM(receita_total_real)                                     AS receita_total_real,
    SUM(receita_fefc)        / NULLIF(SUM(receita_total), 0)    AS share_fefc,
    SUM(receita_fp)          / NULLIF(SUM(receita_total), 0)    AS share_fundo_partidario,
    (SUM(receita_fefc) + SUM(receita_fp))
                             / NULLIF(SUM(receita_total), 0)    AS share_publico,
    SUM(receita_doacao_pf)   / NULLIF(SUM(receita_total), 0)    AS share_doacao_pf,
    SUM(receita_propria)     / NULLIF(SUM(receita_total), 0)    AS share_propria
FROM vw_financas_candidato
GROUP BY 1
ORDER BY 1;


-- Só anos de origem que têm painel construído (o último ano carregado
-- não tem "eleição seguinte" e entraria como zero de recandidatura).
CREATE OR REPLACE VIEW vw_ctx_vantagem_bruta AS
SELECT
    p.ano_eleicao                                               AS ano_t,
    p.eleito                                                    AS eleito_t,
    COUNT(*)                                                    AS n,
    AVG(CASE WHEN p.concorreu_t1 THEN 1.0 ELSE 0.0 END)         AS taxa_recandidatura,
    AVG(CASE WHEN p.eleito_t1 THEN 1.0 ELSE 0.0 END)
        FILTER (WHERE p.concorreu_t1)                           AS taxa_eleicao_entre_recandidatos,
    COUNT(p.ln_receita_t1_cond)                                 AS n_com_receita_t1,
    AVG(p.ln_receita_t1_cond)                                   AS media_ln_receita_t1,
    STDDEV_SAMP(p.ln_receita_t1_cond)                           AS dp_ln_receita_t1,
    MEDIAN(p.receita_t1) FILTER (WHERE p.concorreu_t1)          AS mediana_receita_t1_real
FROM vw_painel_rdd p
WHERE p.ano_eleicao IN (SELECT DISTINCT ano_t FROM painel_link)
GROUP BY 1, 2
ORDER BY 1, 2;
