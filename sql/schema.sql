-- =====================================================================
-- schema.sql — modelo relacional do projeto
-- Banco: DuckDB (arquivo local em data/db/financiamento.duckdb).
-- Reexecutável do zero (idempotente).
--
-- Convenções
-- ---------------------------------------------------------------------
--   * sq_candidato = SQ_CANDIDATO do TSE. É chave de CANDIDATURA, não
--     de pessoa: a mesma pessoa em dois anos tem dois sq_candidato.
--     A ligação entre eleições é feita pela tabela `painel_link`,
--     construída em python/analysis/build_panel.py.
--
--   * id_lista = unidade que disputa as vagas no sistema proporcional.
--     2018 -> coligação; 2020/2024 -> partido isolado (a EC 97/2017
--     vedou coligação proporcional a partir de 2020); 2022 -> partido
--     ou federação. O TSE preenche SQ_COLIGACAO com o sequencial do
--     próprio partido quando não há coligação, então o campo serve
--     para todos os anos.
--
--   * "disputa" = (ano, turno, cargo, uf, municipio): a unidade dentro
--     da qual as cadeiras são distribuídas.
--     "lista"   = (disputa, id_lista): a unidade dentro da qual a ordem
--     de eleição é definida por voto nominal.
--
--   * Valores monetários em BRL NOMINAL. A deflação é feita na camada
--     analítica (view vw_financas_candidato, via tabela `ipca`), nunca
--     na ingestão — assim o dado bruto continua auditável contra os
--     totais publicados pelo TSE.
-- =====================================================================

DROP TABLE IF EXISTS painel_link;
DROP TABLE IF EXISTS receitas;
DROP TABLE IF EXISTS despesas;
DROP TABLE IF EXISTS resultados;
DROP TABLE IF EXISTS candidatos;
DROP TABLE IF EXISTS ipca;

-- ---------------------------------------------------------------------
-- 1. candidatos — uma linha por candidatura
-- ---------------------------------------------------------------------
CREATE TABLE candidatos (
    sq_candidato          BIGINT   PRIMARY KEY,
    ano_eleicao           INTEGER  NOT NULL,
    turno                 INTEGER  NOT NULL DEFAULT 1,
    cd_cargo              INTEGER,
    cargo                 VARCHAR  NOT NULL,   -- VEREADOR, DEPUTADO ESTADUAL, ...
    uf                    VARCHAR  NOT NULL,
    municipio             VARCHAR,             -- NULL em cargos estaduais/federais
    cd_municipio          VARCHAR,
    nome_candidato        VARCHAR,
    nome_urna             VARCHAR,
    numero_urna           VARCHAR,
    partido               VARCHAR  NOT NULL,
    nr_partido            INTEGER,
    id_lista              VARCHAR  NOT NULL,   -- SQ_COLIGACAO (ver nota acima)
    nm_lista              VARCHAR,
    cpf_hash              VARCHAR,             -- SHA-256 salgado; NULL quando o TSE não publica
    genero                VARCHAR,
    cor_raca              VARCHAR,
    grau_instrucao        VARCHAR,
    ocupacao              VARCHAR,
    idade_posse           INTEGER,
    st_reeleicao          VARCHAR,
    situacao_candidatura  VARCHAR,             -- APTO / INAPTO / RENUNCIA ...
    situacao_final        VARCHAR              -- ELEITO POR QP / POR MEDIA / SUPLENTE / NAO ELEITO
);

-- ---------------------------------------------------------------------
-- 2. resultados — votação nominal consolidada por candidatura
--    (o CSV do TSE vem por município E zona; a soma é feita na carga)
-- ---------------------------------------------------------------------
CREATE TABLE resultados (
    sq_candidato    BIGINT  NOT NULL,
    ano_eleicao     INTEGER NOT NULL,
    turno           INTEGER NOT NULL DEFAULT 1,
    votos_nominais  BIGINT  NOT NULL,
    eleito          BOOLEAN NOT NULL,          -- derivado de situacao_final
    PRIMARY KEY (sq_candidato, turno)
);

-- ---------------------------------------------------------------------
-- 3. receitas — nível de transação
-- ---------------------------------------------------------------------
CREATE TABLE receitas (
    id_receita      VARCHAR,
    sq_candidato    BIGINT        NOT NULL,
    ano_eleicao     INTEGER       NOT NULL,
    fonte           VARCHAR       NOT NULL,    -- fundo_eleitoral | fundo_partidario
                                               -- | doacao_pf | doacao_partido
                                               -- | proprio | outros
    origem_bruta    VARCHAR,                   -- texto original do TSE (auditoria)
    valor           DECIMAL(18,2) NOT NULL,
    data_receita    DATE,
    doador_hash     VARCHAR,                   -- SHA-256 salgado do CPF/CNPJ
    doador_tipo     VARCHAR                    -- PF | PJ
);

-- ---------------------------------------------------------------------
-- 4. despesas — nível de transação
-- ---------------------------------------------------------------------
CREATE TABLE despesas (
    id_despesa      VARCHAR,
    sq_candidato    BIGINT        NOT NULL,
    ano_eleicao     INTEGER       NOT NULL,
    categoria       VARCHAR,
    valor           DECIMAL(18,2) NOT NULL,
    data_despesa    DATE,
    fornecedor_hash VARCHAR,
    fornecedor_tipo VARCHAR
);

-- ---------------------------------------------------------------------
-- 5. ipca — deflator anual (IPCA médio, IBGE/SIDRA tabela 1737)
--    Comparar 2018 com 2024 em reais nominais é um erro que aparece
--    direto nos gráficos. `indice` tem base 100 no ano de referência
--    definido em python/ingest/deflator.py.
-- ---------------------------------------------------------------------
CREATE TABLE ipca (
    ano     INTEGER PRIMARY KEY,
    indice  DOUBLE  NOT NULL
);

-- ---------------------------------------------------------------------
-- 6. painel_link — ligação da MESMA PESSOA entre duas eleições.
--    Populada por python/analysis/build_panel.py. nivel_match registra
--    a força do pareamento (1 = mais forte); ver o módulo para a
--    cascata completa. O nível fica gravado para que a análise possa
--    ser refeita só com os matches fortes.
-- ---------------------------------------------------------------------
CREATE TABLE painel_link (
    sq_t         BIGINT  NOT NULL,
    sq_t1        BIGINT  NOT NULL,
    ano_t        INTEGER NOT NULL,
    ano_t1       INTEGER NOT NULL,
    nivel_match  INTEGER NOT NULL,
    regra        VARCHAR
);

-- ---------------------------------------------------------------------
-- Índices de apoio (DuckDB usa zone maps, mas ajudam em joins seletivos)
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS ix_cand_disputa  ON candidatos (ano_eleicao, cargo, uf, municipio);
CREATE INDEX IF NOT EXISTS ix_cand_cpf      ON candidatos (cpf_hash);
CREATE INDEX IF NOT EXISTS ix_receitas_cand ON receitas   (sq_candidato);
CREATE INDEX IF NOT EXISTS ix_despesas_cand ON despesas   (sq_candidato);
CREATE INDEX IF NOT EXISTS ix_result_cand   ON resultados (sq_candidato);
