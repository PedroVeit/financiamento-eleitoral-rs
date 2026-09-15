-- =====================================================================
-- 01_agregacoes_receita.sql — camada descritiva
--
-- Toda a agregação pesada (milhões de lançamentos de receita e despesa)
-- acontece aqui, no DuckDB. Nenhum loop em Python toca lançamento
-- individual.
--
-- Regra de ouro: nada aqui filtra por partido, ideologia ou nome. Todo
-- filtro é estrutural (ano, cargo, UF, situação de candidatura).
-- =====================================================================

-- ---------------------------------------------------------------------
-- Fator de deflação por ano. Se a tabela `ipca` estiver vazia, o fator
-- é 1 e a coluna `deflacionado` indica isso — o pipeline não quebra,
-- mas também não mente sobre estar comparando reais de anos diferentes.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_deflator AS
SELECT
    c.ano_eleicao                              AS ano,
    COALESCE(100.0 / NULLIF(i.indice, 0), 1.0) AS fator,
    (i.ano IS NOT NULL)                        AS deflacionado
FROM (SELECT DISTINCT ano_eleicao FROM candidatos) c
LEFT JOIN ipca i ON i.ano = c.ano_eleicao;


-- ---------------------------------------------------------------------
-- vw_receita_candidato — total e composição da receita por candidatura
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_receita_candidato AS
SELECT
    sq_candidato,
    ano_eleicao,
    SUM(valor)                                              AS receita_total,
    SUM(valor) FILTER (WHERE fonte = 'fundo_eleitoral')     AS receita_fefc,
    SUM(valor) FILTER (WHERE fonte = 'fundo_partidario')    AS receita_fp,
    SUM(valor) FILTER (WHERE fonte = 'doacao_pf')           AS receita_doacao_pf,
    SUM(valor) FILTER (WHERE fonte = 'doacao_partido')      AS receita_doacao_partido,
    SUM(valor) FILTER (WHERE fonte = 'proprio')             AS receita_propria,
    SUM(valor) FILTER (WHERE fonte = 'outros')              AS receita_outros,
    COUNT(*)                                                AS n_lancamentos_receita,
    COUNT(DISTINCT doador_hash)                             AS n_doadores_distintos,
    COUNT(DISTINCT doador_hash) FILTER (WHERE doador_tipo = 'PF') AS n_doadores_pf,
    -- Concentração: participação do maior doador individual na receita.
    -- Métrica de ESTRUTURA de financiamento, não de mérito.
    MAX(valor_doador) / NULLIF(SUM(valor), 0)               AS share_maior_doador
FROM (
    SELECT r.*,
           SUM(valor) OVER (PARTITION BY sq_candidato, doador_hash) AS valor_doador
    FROM receitas r
)
GROUP BY sq_candidato, ano_eleicao;


-- ---------------------------------------------------------------------
-- vw_despesa_candidato — total e composição da despesa por candidatura
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_despesa_candidato AS
SELECT
    sq_candidato,
    ano_eleicao,
    SUM(valor)                      AS despesa_total,
    COUNT(*)                        AS n_lancamentos_despesa,
    COUNT(DISTINCT fornecedor_hash) AS n_fornecedores,
    SUM(valor) FILTER (WHERE categoria ILIKE '%pessoal%'
                          OR categoria ILIKE '%militan%')   AS despesa_pessoal,
    SUM(valor) FILTER (WHERE categoria ILIKE '%public%'
                          OR categoria ILIKE '%propaganda%'
                          OR categoria ILIKE '%internet%'
                          OR categoria ILIKE '%impress%')   AS despesa_publicidade
FROM despesas
GROUP BY sq_candidato, ano_eleicao;


-- ---------------------------------------------------------------------
-- vw_financas_candidato — tabela analítica principal.
-- Uma linha por candidatura: finanças + resultado + composição.
--
-- LEFT JOIN nas finanças é proposital: candidatura sem receita
-- declarada existe e precisa aparecer com 0, não sumir da amostra —
-- excluí-la silenciosamente enviesa qualquer média de gasto para cima.
-- A distinção entre "não arrecadou" e "não prestou contas" fica em
-- tem_prestacao_contas.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_financas_candidato AS
SELECT
    c.sq_candidato,
    c.ano_eleicao,
    c.turno,
    c.cargo,
    c.uf,
    c.municipio,
    c.cd_municipio,
    c.partido,
    c.id_lista,
    c.nm_lista,
    c.nome_candidato,
    c.nome_urna,
    c.cpf_hash,
    c.genero,
    c.cor_raca,
    c.idade_posse,
    c.st_reeleicao,
    c.situacao_final,
    res.votos_nominais,
    res.eleito,
    d.fator                                     AS fator_deflator,
    d.deflacionado,
    COALESCE(rc.receita_total, 0)               AS receita_total,
    COALESCE(dc.despesa_total, 0)               AS despesa_total,
    COALESCE(rc.receita_total, 0) * d.fator     AS receita_total_real,
    COALESCE(dc.despesa_total, 0) * d.fator     AS despesa_total_real,
    (rc.sq_candidato IS NOT NULL)               AS tem_prestacao_contas,
    COALESCE(rc.receita_fefc, 0)                AS receita_fefc,
    COALESCE(rc.receita_fp, 0)                  AS receita_fp,
    COALESCE(rc.receita_doacao_pf, 0)           AS receita_doacao_pf,
    COALESCE(rc.receita_doacao_partido, 0)      AS receita_doacao_partido,
    COALESCE(rc.receita_propria, 0)             AS receita_propria,
    COALESCE(rc.receita_outros, 0)              AS receita_outros,
    COALESCE(rc.n_doadores_distintos, 0)        AS n_doadores_distintos,
    COALESCE(rc.n_doadores_pf, 0)               AS n_doadores_pf,
    rc.share_maior_doador,
    COALESCE(dc.despesa_publicidade, 0)         AS despesa_publicidade,
    COALESCE(dc.despesa_pessoal, 0)             AS despesa_pessoal,
    -- shares: NULL (não 0) quando a receita total é zero, para não
    -- inventar "0% de FEFC" para quem não arrecadou nada
    CASE WHEN COALESCE(rc.receita_total, 0) > 0
         THEN COALESCE(rc.receita_fefc, 0) / rc.receita_total END        AS share_fefc,
    CASE WHEN COALESCE(rc.receita_total, 0) > 0
         THEN COALESCE(rc.receita_doacao_pf, 0) / rc.receita_total END   AS share_doacao_pf,
    CASE WHEN COALESCE(rc.receita_total, 0) > 0
         THEN COALESCE(rc.receita_propria, 0) / rc.receita_total END     AS share_propria,
    -- gasto por voto: métrica DESCRITIVA, não de eficiência causal.
    -- Ver docs/nota_metodologica_rdd.md, seção "o que este número não é".
    CASE WHEN res.votos_nominais > 0
         THEN COALESCE(dc.despesa_total, 0) / res.votos_nominais END     AS gasto_por_voto
FROM candidatos c
JOIN resultados res
     ON res.sq_candidato = c.sq_candidato AND res.turno = c.turno
JOIN vw_deflator d
     ON d.ano = c.ano_eleicao
LEFT JOIN vw_receita_candidato rc ON rc.sq_candidato = c.sq_candidato
LEFT JOIN vw_despesa_candidato dc ON dc.sq_candidato = c.sq_candidato
-- A partir do ciclo 2022, o TSE deixou de preencher
-- DS_SITUACAO_CANDIDATURA no arquivo publicado apos a eleicao: o campo
-- vem uniformemente como '#NE' (nao se aplica), porque so faz sentido
-- durante o periodo de registro, nao no pacote final. Nesses anos a
-- validade da candidatura ja esta garantida pelo JOIN com `resultados`
-- (so quem tinha candidatura valida aparece no arquivo de votacao).
WHERE c.situacao_candidatura IN ('APTO', 'DEFERIDO', 'DEFERIDO COM RECURSO', '#NE');


-- ---------------------------------------------------------------------
-- vw_desc_por_partido — agregação descritiva por partido/ano/cargo.
-- Mediana além da média: a distribuição de gasto de campanha é muito
-- assimétrica e a média sozinha engana.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_desc_por_partido AS
SELECT
    ano_eleicao,
    cargo,
    uf,
    partido,
    COUNT(*)                                    AS n_candidaturas,
    SUM(CASE WHEN eleito THEN 1 ELSE 0 END)     AS n_eleitos,
    SUM(despesa_total_real)                     AS despesa_total_partido,
    AVG(despesa_total_real)                     AS despesa_media,
    MEDIAN(despesa_total_real)                  AS despesa_mediana,
    AVG(share_fefc)                             AS share_fefc_medio,
    MEDIAN(gasto_por_voto)                      AS gasto_por_voto_mediano
FROM vw_financas_candidato
GROUP BY ano_eleicao, cargo, uf, partido;
