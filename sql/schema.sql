DROP TABLE IF EXISTS painel_link;
DROP TABLE IF EXISTS receitas;
DROP TABLE IF EXISTS despesas;
DROP TABLE IF EXISTS resultados;
DROP TABLE IF EXISTS candidatos;
DROP TABLE IF EXISTS ipca;


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


CREATE TABLE resultados (
    sq_candidato    BIGINT  NOT NULL,
    ano_eleicao     INTEGER NOT NULL,
    turno           INTEGER NOT NULL DEFAULT 1,
    votos_nominais  BIGINT  NOT NULL,
    eleito          BOOLEAN NOT NULL,          -- derivado de situacao_final
    PRIMARY KEY (sq_candidato, turno)
);


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


CREATE TABLE ipca (
    ano     INTEGER PRIMARY KEY,
    indice  DOUBLE  NOT NULL
);


CREATE TABLE painel_link (
    sq_t         BIGINT  NOT NULL,
    sq_t1        BIGINT  NOT NULL,
    ano_t        INTEGER NOT NULL,
    ano_t1       INTEGER NOT NULL,
    nivel_match  INTEGER NOT NULL,
    regra        VARCHAR
);


CREATE INDEX IF NOT EXISTS ix_cand_disputa  ON candidatos (ano_eleicao, cargo, uf, municipio);
CREATE INDEX IF NOT EXISTS ix_cand_cpf      ON candidatos (cpf_hash);
CREATE INDEX IF NOT EXISTS ix_receitas_cand ON receitas   (sq_candidato);
CREATE INDEX IF NOT EXISTS ix_despesas_cand ON despesas   (sq_candidato);
CREATE INDEX IF NOT EXISTS ix_result_cand   ON resultados (sq_candidato);
