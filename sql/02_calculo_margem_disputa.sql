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

    -- empates exatos em votos: o desempate legal é por idade, não por voto
    
    COUNT(*) OVER (
        PARTITION BY f.ano_eleicao, f.turno, f.cargo, f.uf, f.municipio,
                     f.id_lista, f.votos_nominais
    ) AS n_empatados
FROM vw_financas_candidato f;


CREATE OR REPLACE VIEW vw_corte_lista_bruto AS
SELECT
    ano_eleicao, turno, cargo, uf, municipio, id_lista, id_lista_disputa,
    MIN(votos_nominais) FILTER (WHERE eleito)     AS v_ultimo_eleito,
    MAX(votos_nominais) FILTER (WHERE NOT eleito) AS v_primeiro_suplente,
    COUNT(*) FILTER (WHERE eleito)                AS cadeiras_da_lista,
    COUNT(*) FILTER (WHERE NOT eleito)            AS n_nao_eleitos
FROM vw_rank_lista
GROUP BY ALL;


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



CREATE OR REPLACE VIEW vw_check_sinal_margem AS
SELECT sq_candidato, ano_eleicao, municipio, id_lista,
       posicao_na_lista, cadeiras_da_lista, votos_nominais, margem_votos, eleito
FROM vw_margem_candidato
WHERE (margem_votos > 0 AND NOT eleito)
   OR (margem_votos < 0 AND eleito)
   OR (margem_votos = 0);


CREATE OR REPLACE VIEW vw_check_simetria_margem AS
SELECT
    id_lista_disputa,
    MAX(margem_votos) FILTER (WHERE eh_ultimo_eleito)     AS margem_pos,
    MIN(margem_votos) FILTER (WHERE eh_primeiro_suplente) AS margem_neg
FROM vw_margem_candidato
GROUP BY id_lista_disputa;
