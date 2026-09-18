"""Cria o banco DuckDB, aplica o schema e carrega os CSVs do TSE.

Entradas públicas:

    criar_banco(caminho)                -> conexão com schema + views aplicados
    aplicar_views(con)                  -> (re)cria as views analíticas
    carregar_tse(con, anos, cargo, uf)  -> popula as tabelas
    validar(con)                        -> relatório de integridade

Toda a normalização pesada (parse de decimal com vírgula, soma de votos
por zona, classificação da fonte de receita, hash de documento) é feita
em SQL dentro do DuckDB, lendo os CSVs direto do disco com `read_csv`.
Nenhum CSV do TSE passa por um DataFrame: os arquivos de despesa de um
ano geral têm milhões de linhas.

Mudança de nome de coluna entre eleições
----------------------------------------
O TSE renomeia colunas sem aviso. Em vez de quebrar, o módulo declara
alternativas por conceito em COLMAP e usa a primeira que existir no
arquivo (`_pick`). Para ver o que um ano novo traz de fato:

    python -m python.ingest.download_tse --anos 2026 --inspecionar
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import duckdb

RAIZ = Path(__file__).resolve().parents[2]
DIR_SQL = RAIZ / "sql"
DIR_RAW = RAIZ / "data" / "raw"
BANCO_PADRAO = RAIZ / "data" / "db" / "financiamento.duckdb"

SCRIPTS_VIEWS = [
    "01_agregacoes_receita.sql",
    "02_calculo_margem_disputa.sql",
    "03_janela_rdd.sql",
]

# Sal da pseudonimização. Definir via variável de ambiente e NÃO
# versionar: sem sal, o hash de um CPF é reversível por força bruta —
# o espaço de CPFs válidos é pequeno demais.
SAL = os.environ.get("FIN_HASH_SAL", "sal-de-desenvolvimento-trocar-antes-de-publicar")

OPCOES_CSV = (
    "delim=';', header=true, encoding='latin-1', "
    "union_by_name=true, all_varchar=true, ignore_errors=true, "
    # quote/escape fixados explicitamente, não deixados para o sniffer do
    # DuckDB adivinhar. Descoberto ao carregar o .txt de despesas de 2016
    # (150 MB): a autodetecção errou o caractere de aspas nesse arquivo
    # específico, e cada nome de coluna saiu com as aspas LITERAIS dentro
    # do texto (ex.: '"Sequencial Candidato"', aspas inclusas), fazendo
    # todo _pick() falhar em silêncio e a carga de despesas voltar 0 sem
    # erro nenhum. O sniffer amostra só um pedaço do arquivo; em arquivos
    # grandes o suficiente, um trecho ambíguo na amostra basta para errar
    # a detecção do arquivo inteiro. Todos os arquivos do TSE usam aspas
    # duplas para quiar e escapar campos -- fixar isso é estritamente mais
    # seguro que confiar na adivinhação, em qualquer ano.
    "quote='\"', escape='\"'"
)

# Alternativas de nome de coluna por conceito. A primeira que existir vence.
COLMAP: dict[str, list[str]] = {
    "sq_candidato":         ["SQ_CANDIDATO"],
    "ano_eleicao":          ["ANO_ELEICAO"],
    "turno":                ["NR_TURNO"],
    "cd_cargo":             ["CD_CARGO"],
    "cargo":                ["DS_CARGO"],
    "uf":                   ["SG_UF", "SG_UF_SUPERIOR"],
    "municipio":            ["NM_UE", "NM_MUNICIPIO"],
    "cd_municipio":         ["SG_UE", "CD_MUNICIPIO"],
    "nome_candidato":       ["NM_CANDIDATO"],
    "nome_urna":            ["NM_URNA_CANDIDATO"],
    "numero_urna":          ["NR_CANDIDATO"],
    "partido":              ["SG_PARTIDO"],
    "nr_partido":           ["NR_PARTIDO"],
    "id_lista":             ["SQ_COLIGACAO"],
    "nm_lista":             ["NM_COLIGACAO", "DS_COMPOSICAO_COLIGACAO"],
    "cpf":                  ["NR_CPF_CANDIDATO"],
    "genero":               ["DS_GENERO"],
    "cor_raca":             ["DS_COR_RACA"],
    "grau_instrucao":       ["DS_GRAU_INSTRUCAO"],
    "ocupacao":             ["DS_OCUPACAO"],
    "idade_posse":          ["NR_IDADE_DATA_POSSE"],
    "st_reeleicao":         ["ST_REELEICAO"],
    "situacao_candidatura": ["DS_SITUACAO_CANDIDATURA", "DS_DETALHE_SITUACAO_CAND"],
}


# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------
def _executar_arquivo(con: duckdb.DuckDBPyConnection, caminho: Path) -> None:
    con.execute(caminho.read_text(encoding="utf-8"))


def _colunas(con: duckdb.DuckDBPyConnection, padrao: str) -> set[str]:
    rel = con.sql(f"SELECT * FROM read_csv('{padrao}', {OPCOES_CSV}) LIMIT 0")
    return set(rel.columns)


def _pick(cols: set[str], alternativas: list[str], default: str = "NULL") -> str:
    """Primeira coluna existente entre as alternativas; senão, NULL."""
    for c in alternativas:
        if c in cols:
            return f'"{c}"'
    return default


def _hash_sql(expr: str) -> str:
    """SHA-256 salgado dos dígitos de um documento.

    NULL se vazio OU se sobrar menos de 9 dígitos após limpar o texto.
    O TSE às vezes preenche o campo com um código sentinela (ex.: '-4')
    quando o dado não é publicado (privacidade). Sem esse piso de 9
    dígitos, '-4' viraria o dígito '4' e seria tratado como documento
    válido — e como o sentinela é igual para todo mundo, todo mundo
    ganharia o MESMO hash, o que quebraria silenciosamente o
    pareamento por CPF (ver docs/decisoes.md, D7).
    """
    digitos = f"regexp_replace(COALESCE({expr}, ''), '[^0-9]', '', 'g')"
    return (f"CASE WHEN length({digitos}) >= 9 "
            f"THEN sha256('{SAL}' || {digitos}) END")


def _glob(subpasta: str, ano: int, prefixo: str, extensao: str = "csv") -> str:
    return str(DIR_RAW / subpasta / str(ano) /
               f"{prefixo}*.{extensao}").replace("\\", "/")


# ---------------------------------------------------------------------
# Banco e views
# ---------------------------------------------------------------------
def criar_banco(caminho: Path | str = BANCO_PADRAO,
                recriar: bool = False) -> duckdb.DuckDBPyConnection:
    """Abre (ou cria) o banco, aplica schema.sql e as views analíticas."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if recriar and caminho.exists():
        caminho.unlink()
    con = duckdb.connect(str(caminho))
    _executar_arquivo(con, DIR_SQL / "schema.sql")
    carregar_ipca(con)
    aplicar_views(con)
    return con


def aplicar_views(con: duckdb.DuckDBPyConnection) -> None:
    """(Re)cria as views analíticas. Idempotente — pode rodar sempre."""
    for nome in SCRIPTS_VIEWS:
        _executar_arquivo(con, DIR_SQL / nome)


def carregar_ipca(con: duckdb.DuckDBPyConnection) -> None:
    from python.ingest.deflator import SERIE_IPCA
    con.execute("DELETE FROM ipca")
    con.executemany("INSERT INTO ipca VALUES (?, ?)", list(SERIE_IPCA.items()))


# ---------------------------------------------------------------------
# Carga por tipo de arquivo
# ---------------------------------------------------------------------
def carregar_candidatos(con, ano: int, cargo: str = "VEREADOR", uf: str = "RS") -> int:
    padrao = _glob("candidatos", ano, "consulta_cand")
    cols = _colunas(con, padrao)
    c = {k: _pick(cols, v) for k, v in COLMAP.items()}

    con.execute(f"""
        INSERT OR REPLACE INTO candidatos
        SELECT DISTINCT ON (TRY_CAST({c['sq_candidato']} AS BIGINT))
            TRY_CAST({c['sq_candidato']} AS BIGINT)     AS sq_candidato,
            TRY_CAST({c['ano_eleicao']} AS INTEGER)     AS ano_eleicao,
            TRY_CAST({c['turno']} AS INTEGER)           AS turno,
            TRY_CAST({c['cd_cargo']} AS INTEGER)        AS cd_cargo,
            UPPER(TRIM({c['cargo']}))                   AS cargo,
            UPPER(TRIM({c['uf']}))                      AS uf,
            UPPER(TRIM({c['municipio']}))               AS municipio,
            TRIM({c['cd_municipio']})                   AS cd_municipio,
            UPPER(TRIM({c['nome_candidato']}))          AS nome_candidato,
            UPPER(TRIM({c['nome_urna']}))               AS nome_urna,
            TRIM({c['numero_urna']})                    AS numero_urna,
            UPPER(TRIM({c['partido']}))                 AS partido,
            TRY_CAST({c['nr_partido']} AS INTEGER)      AS nr_partido,
            -- id_lista: sequencial da coligação/federação; quando não há
            -- coligação o TSE preenche com o sequencial do próprio
            -- partido. O fallback para a sigla cobre arquivo sem a coluna.
            COALESCE(NULLIF(TRIM({c['id_lista']}), ''),
                     UPPER(TRIM({c['partido']})))       AS id_lista,
            {c['nm_lista']}                             AS nm_lista,
            {_hash_sql(c['cpf'])}                       AS cpf_hash,
            {c['genero']}                               AS genero,
            {c['cor_raca']}                             AS cor_raca,
            {c['grau_instrucao']}                       AS grau_instrucao,
            {c['ocupacao']}                             AS ocupacao,
            TRY_CAST({c['idade_posse']} AS INTEGER)     AS idade_posse,
            {c['st_reeleicao']}                         AS st_reeleicao,
            UPPER(TRIM({c['situacao_candidatura']}))    AS situacao_candidatura,
            NULL                                        AS situacao_final
        FROM read_csv('{padrao}', {OPCOES_CSV})
        WHERE UPPER(TRIM({c['uf']}))    = '{uf}'
          AND UPPER(TRIM({c['cargo']})) = '{cargo}'
          AND TRY_CAST({c['turno']} AS INTEGER) = 1
    """)
    return con.execute("SELECT COUNT(*) FROM candidatos WHERE ano_eleicao = ?",
                       [ano]).fetchone()[0]


def carregar_resultados(con, ano: int) -> int:
    """Votos nominais somados entre zonas + situação final do turno.

    DS_SIT_TOT_TURNO traz ELEITO POR QP / ELEITO POR MEDIA / ELEITO /
    SUPLENTE / NAO ELEITO. Qualquer rótulo que comece com 'ELEITO' conta
    como eleito: QP e MEDIA são o caminho pelo qual a cadeira foi obtida,
    não um status diferente.
    """
    padrao = _glob("resultados", ano, "votacao_candidato_munzona")
    cols = _colunas(con, padrao)
    sq = _pick(cols, ["SQ_CANDIDATO"])
    turno = _pick(cols, ["NR_TURNO"])
    votos = _pick(cols, ["QT_VOTOS_NOMINAIS", "QT_VOTOS_NOMINAIS_VALIDOS"])
    sit = _pick(cols, ["DS_SIT_TOT_TURNO"])

    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _votos AS
        SELECT
            TRY_CAST({sq} AS BIGINT)                     AS sq_candidato,
            TRY_CAST({turno} AS INTEGER)                 AS turno,
            SUM(TRY_CAST({votos} AS BIGINT))             AS votos_nominais,
            MAX(UPPER(TRIM({sit})))                      AS situacao_final
        FROM read_csv('{padrao}', {OPCOES_CSV})
        WHERE TRY_CAST({turno} AS INTEGER) = 1
        GROUP BY 1, 2
    """)
    con.execute("""
        UPDATE candidatos c SET situacao_final = v.situacao_final
        FROM _votos v WHERE v.sq_candidato = c.sq_candidato
    """)
    con.execute("""
        INSERT OR REPLACE INTO resultados
        SELECT c.sq_candidato, c.ano_eleicao, c.turno,
               COALESCE(v.votos_nominais, 0),
               COALESCE(v.situacao_final, '') LIKE 'ELEITO%'
        FROM candidatos c
        JOIN _votos v ON v.sq_candidato = c.sq_candidato AND v.turno = c.turno
    """)
    return con.execute("SELECT COUNT(*) FROM resultados r JOIN candidatos c "
                       "USING (sq_candidato) WHERE c.ano_eleicao = ?", [ano]).fetchone()[0]


# Classificação da fonte de receita. O texto do TSE muda entre anos (o
# FEFC só existe a partir de 2018), por isso a classificação é por
# padrão de texto e a descrição original fica em origem_bruta.
def _case_fonte(origem: str, fonte: str) -> str:
    txt = f"UPPER(COALESCE({fonte}, '') || ' ' || COALESCE({origem}, ''))"
    return f"""
    CASE
        WHEN {txt} LIKE '%FUNDO ESPECIAL DE FINANCIAMENTO%'
          OR {txt} LIKE '%FEFC%'                    THEN 'fundo_eleitoral'
        WHEN {txt} LIKE '%FUNDO PARTID%'            THEN 'fundo_partidario'
        WHEN {txt} LIKE '%PR%PRIO%'                 THEN 'proprio'
        WHEN {txt} LIKE '%PESSOA%F%SICA%'           THEN 'doacao_pf'
        WHEN {txt} LIKE '%PARTIDO%'
          OR {txt} LIKE '%OUTRO%CANDIDATO%'         THEN 'doacao_partido'
        ELSE 'outros'
    END"""


def _valor(expr: str) -> str:
    """Decimal brasileiro ('1.234,56') para DECIMAL."""
    return f"TRY_CAST(REPLACE(REPLACE({expr}, '.', ''), ',', '.') AS DECIMAL(18,2))"


# ---------------------------------------------------------------------
# Formato legado de prestação de contas (anos < 2018)
#
# Antes da padronização do TSE em códigos ALLCAPS (ANO_ELEICAO,
# SQ_CANDIDATO, VR_RECEITA...), a prestação de contas era publicada com
# cabeçalho em português por extenso, sem coluna de ano (o ano vem do
# nome do pacote, não de uma coluna) e com nomes de arquivo diferentes
# (despesas_candidatos_prestacao_contas_final_2016_RS.txt, não
# despesas_contratadas_candidatos_2016_RS.csv). O restante do pipeline
# (schema, views, deflator, RDD) não muda nada -- só a extração destas
# duas tabelas precisa de um caminho de leitura à parte.
#
# Cuidado real que já mordeu uma vez: o nome da coluna do número do
# documento é "Numero do documento" (SEM acento) no arquivo de
# RECEITAS e "Número do documento" (COM acento) no de DESPESAS. É o
# tipo de inconsistência que o TSE introduz sem aviso -- por isso cada
# mapa abaixo é escrito por extenso em vez de composto por concatenação
# de string, mais fácil de auditar visualmente.
FORMATO_CONTAS_LEGADO: dict[int, dict[str, str]] = {
    2016: {
        "receitas_prefixo": "receitas_candidatos_prestacao_contas_final",
        "despesas_prefixo": "despesas_candidatos_prestacao_contas_final",
        "extensao": "txt",
    },
    # 2012 provavelmente segue o mesmo padrão -- confirmar com
    # --inspecionar antes de assumir; NÃO herdar esta entrada sem checar.
}

COLMAP_LEGADO_RECEITAS = {
    "sq_candidato": ["Sequencial Candidato"],
    "id_receita":   ["Numero Recibo Eleitoral"],
    "origem":       ["Descricao da receita", "Especie recurso"],
    # "Tipo receita" é a categoria detalhada (Recursos de pessoas físicas,
    # Recursos próprios, Recursos de partido político, Recursos de outros
    # candidatos...) -- é ISSO que alimenta a classificação. "Fonte
    # recurso" em 2016 só tem dois valores possíveis ("Outros Recursos" /
    # "Fundo Partidario"), grosseiro demais para classificar sozinho, mas
    # entra em `fonte_coarse` só para constar na auditoria.
    #
    # Bug real que isso corrige: a versão anterior lia só "Fonte recurso"
    # como `fonte`, o que jogou 140.820 de 153.587 receitas de 2016 (92%)
    # no balaio "outros" -- não porque o texto fosse desconhecido, mas
    # porque a coluna lida nunca continha o texto informativo. Ver
    # docs/decisoes.md, D17.
    "fonte":        ["Tipo receita"],
    "fonte_coarse": ["Fonte recurso"],
    "valor":        ["Valor receita"],
    "data":         ["Data da receita"],
    "doc_doador":   ["CPF/CNPJ do doador"],
}

COLMAP_LEGADO_DESPESAS = {
    "sq_candidato":    ["Sequencial Candidato"],
    "id_despesa":      ["Número do documento"],   # ATENÇÃO: com acento aqui
    "categoria":       ["Tipo despesa", "Descriçao da despesa"],
    "valor":           ["Valor despesa"],
    "data":            ["Data da despesa"],
    "doc_fornecedor":  ["CPF/CNPJ do fornecedor"],
}


def _carregar_receitas_legado(con, ano: int, padrao: str) -> int:
    cols = _colunas(con, padrao)
    c = {k: _pick(cols, v) for k, v in COLMAP_LEGADO_RECEITAS.items()}
    con.execute(f"""
        INSERT INTO receitas
        SELECT
            {c['id_receita']}                                   AS id_receita,
            TRY_CAST({c['sq_candidato']} AS BIGINT)              AS sq_candidato,
            {ano}                                                AS ano_eleicao,
            {_case_fonte(c['origem'], c['fonte'])}               AS fonte,
            COALESCE({c['fonte']}, '') || ' | ' || COALESCE({c['origem']}, '')
                || ' | ' || COALESCE({c['fonte_coarse']}, '')    AS origem_bruta,
            {_valor(c['valor'])}                                 AS valor,
            TRY_STRPTIME({c['data']}, '%d/%m/%Y')::DATE          AS data_receita,
            {_hash_sql(c['doc_doador'])}                         AS doador_hash,
            CASE WHEN length(regexp_replace(COALESCE({c['doc_doador']}, ''),
                                            '[^0-9]', '', 'g')) = 14
                 THEN 'PJ' ELSE 'PF' END                         AS doador_tipo
        FROM read_csv('{padrao}', {OPCOES_CSV})
        WHERE TRY_CAST({c['sq_candidato']} AS BIGINT) IN
              (SELECT sq_candidato FROM candidatos WHERE ano_eleicao = {ano})
    """)
    return con.execute("SELECT COUNT(*) FROM receitas WHERE ano_eleicao = ?",
                       [ano]).fetchone()[0]


def _carregar_despesas_legado(con, ano: int, padrao: str) -> int:
    cols = _colunas(con, padrao)
    c = {k: _pick(cols, v) for k, v in COLMAP_LEGADO_DESPESAS.items()}
    con.execute(f"""
        INSERT INTO despesas
        SELECT
            {c['id_despesa']}                                   AS id_despesa,
            TRY_CAST({c['sq_candidato']} AS BIGINT)              AS sq_candidato,
            {ano}                                                AS ano_eleicao,
            {c['categoria']}                                    AS categoria,
            {_valor(c['valor'])}                                 AS valor,
            TRY_STRPTIME({c['data']}, '%d/%m/%Y')::DATE          AS data_despesa,
            {_hash_sql(c['doc_fornecedor'])}                     AS fornecedor_hash,
            CASE WHEN length(regexp_replace(COALESCE({c['doc_fornecedor']}, ''),
                                            '[^0-9]', '', 'g')) = 14
                 THEN 'PJ' ELSE 'PF' END                         AS fornecedor_tipo
        FROM read_csv('{padrao}', {OPCOES_CSV})
        WHERE TRY_CAST({c['sq_candidato']} AS BIGINT) IN
              (SELECT sq_candidato FROM candidatos WHERE ano_eleicao = {ano})
    """)
    return con.execute("SELECT COUNT(*) FROM despesas WHERE ano_eleicao = ?",
                       [ano]).fetchone()[0]


def carregar_receitas(con, ano: int) -> int:
    if ano in FORMATO_CONTAS_LEGADO:
        cfg = FORMATO_CONTAS_LEGADO[ano]
        padrao = _glob("contas", ano, cfg["receitas_prefixo"], cfg["extensao"])
        return _carregar_receitas_legado(con, ano, padrao)

    padrao = _glob("contas", ano, "receitas_candidatos")
    cols = _colunas(con, padrao)
    sq = _pick(cols, ["SQ_CANDIDATO"])
    origem = _pick(cols, ["DS_ORIGEM_RECEITA", "DS_ESPECIE_RECEITA"])
    fonte = _pick(cols, ["DS_FONTE_RECEITA"])
    doc = _pick(cols, ["NR_CPF_CNPJ_DOADOR", "NR_DOCUMENTO_DOADOR"])

    con.execute(f"""
        INSERT INTO receitas
        SELECT
            {_pick(cols, ['SQ_RECEITA', 'NR_RECIBO_DOACAO'])}   AS id_receita,
            TRY_CAST({sq} AS BIGINT)                            AS sq_candidato,
            TRY_CAST({_pick(cols, ['ANO_ELEICAO', 'AA_ELEICAO'])} AS INTEGER) AS ano_eleicao,
            {_case_fonte(origem, fonte)}                        AS fonte,
            COALESCE({origem}, '') || ' | ' || COALESCE({fonte}, '') AS origem_bruta,
            {_valor(_pick(cols, ['VR_RECEITA']))}               AS valor,
            TRY_STRPTIME({_pick(cols, ['DT_RECEITA'])}, '%d/%m/%Y')::DATE AS data_receita,
            {_hash_sql(doc)}                                    AS doador_hash,
            CASE WHEN length(regexp_replace(COALESCE({doc}, ''), '[^0-9]', '', 'g')) = 14
                 THEN 'PJ' ELSE 'PF' END                        AS doador_tipo
        FROM read_csv('{padrao}', {OPCOES_CSV})
        WHERE TRY_CAST({sq} AS BIGINT) IN
              (SELECT sq_candidato FROM candidatos WHERE ano_eleicao = {ano})
    """)
    return con.execute("SELECT COUNT(*) FROM receitas WHERE ano_eleicao = ?",
                       [ano]).fetchone()[0]


def carregar_despesas(con, ano: int) -> int:
    if ano in FORMATO_CONTAS_LEGADO:
        cfg = FORMATO_CONTAS_LEGADO[ano]
        padrao = _glob("contas", ano, cfg["despesas_prefixo"], cfg["extensao"])
        return _carregar_despesas_legado(con, ano, padrao)

    padrao = _glob("contas", ano, "despesas_contratadas_candidatos")
    cols = _colunas(con, padrao)
    sq = _pick(cols, ["SQ_CANDIDATO"])
    doc = _pick(cols, ["NR_CPF_CNPJ_FORNECEDOR"])

    con.execute(f"""
        INSERT INTO despesas
        SELECT
            {_pick(cols, ['SQ_DESPESA', 'NR_DOCUMENTO'])}       AS id_despesa,
            TRY_CAST({sq} AS BIGINT)                            AS sq_candidato,
            TRY_CAST({_pick(cols, ['ANO_ELEICAO', 'AA_ELEICAO'])} AS INTEGER) AS ano_eleicao,
            {_pick(cols, ['DS_TIPO_DESPESA', 'DS_DESPESA'])}    AS categoria,
            {_valor(_pick(cols, ['VR_DESPESA_CONTRATADA', 'VR_DESPESA']))} AS valor,
            TRY_STRPTIME({_pick(cols, ['DT_DESPESA'])}, '%d/%m/%Y')::DATE  AS data_despesa,
            {_hash_sql(doc)}                                    AS fornecedor_hash,
            CASE WHEN length(regexp_replace(COALESCE({doc}, ''), '[^0-9]', '', 'g')) = 14
                 THEN 'PJ' ELSE 'PF' END                        AS fornecedor_tipo
        FROM read_csv('{padrao}', {OPCOES_CSV})
        WHERE TRY_CAST({sq} AS BIGINT) IN
              (SELECT sq_candidato FROM candidatos WHERE ano_eleicao = {ano})
    """)
    return con.execute("SELECT COUNT(*) FROM despesas WHERE ano_eleicao = ?",
                       [ano]).fetchone()[0]


#: Cargos municipais (vereador, prefeito) só têm candidatura em anos
#: múltiplos de 4 (2012, 2016, 2020, 2024...). Pedir esses cargos num ano
#: de eleição geral (2018, 2022, 2026...) não dá erro no download -- o
#: arquivo existe, só não tem nenhuma linha desse cargo -- e por isso o
#: engano passa despercebido se não for avisado aqui.
CARGOS_MUNICIPAIS = {"VEREADOR", "PREFEITO", "VICE-PREFEITO"}


def carregar_tse(con, anos: list[int], cargo: str = "VEREADOR", uf: str = "RS") -> None:
    if cargo.upper() in CARGOS_MUNICIPAIS:
        fora = [a for a in anos if a % 4 != 0]
        if fora:
            print(f"  [aviso] {cargo} é cargo municipal (só concorre em anos "
                  f"múltiplos de 4). Não deve haver candidaturas em {fora} -- "
                  f"confira se não é o ano errado antes de interpretar 0 "
                  f"candidaturas como bug.")
    for ano in anos:
        print(f"\n=== carregando {ano} ({cargo}/{uf}) ===")
        print(f"  candidatos : {carregar_candidatos(con, ano, cargo, uf):>9,}")
        print(f"  resultados : {carregar_resultados(con, ano):>9,}")
        print(f"  receitas   : {carregar_receitas(con, ano):>9,}")
        print(f"  despesas   : {carregar_despesas(con, ano):>9,}")


# ---------------------------------------------------------------------
# Validação — os totais têm de bater com a realidade antes de analisar
# ---------------------------------------------------------------------
CHECAGENS: dict[str, str] = {
    "candidatura sem resultado":
        "SELECT COUNT(*) FROM candidatos c LEFT JOIN resultados r USING (sq_candidato) "
        "WHERE r.sq_candidato IS NULL",
    "receita com valor negativo (estorno)":
        "SELECT COUNT(*) FROM receitas WHERE valor < 0",
    "despesa com valor negativo":
        "SELECT COUNT(*) FROM despesas WHERE valor < 0",
    "receita órfã (sem candidatura na amostra)":
        "SELECT COUNT(*) FROM receitas r LEFT JOIN candidatos c USING (sq_candidato) "
        "WHERE c.sq_candidato IS NULL",
    "fonte de receita não classificada":
        "SELECT COUNT(*) FROM receitas WHERE fonte = 'outros'",
    "sinal da margem inconsistente com status de eleito":
        "SELECT COUNT(*) FROM vw_check_sinal_margem",
    "margem assimétrica na lista (bug no cálculo do corte)":
        "SELECT COUNT(*) FROM vw_check_simetria_margem "
        "WHERE margem_pos IS NOT NULL AND margem_neg IS NOT NULL "
        "AND ABS(margem_pos + margem_neg) > 1e-9",
    "ano sem deflator IPCA":
        "SELECT COUNT(*) FROM vw_deflator WHERE NOT deflacionado",
}

# Checagens cujo resultado diferente de zero é informação esperada,
# não erro. Ficam marcadas com 'i' em vez de '!!'.
INFORMATIVAS = {
    "receita com valor negativo (estorno)",
    "receita órfã (sem candidatura na amostra)",
    "fonte de receita não classificada",
}

# Estas quebram o desenho: se derem diferente de zero, a análise causal
# não deve ser rodada.
BLOQUEANTES = {
    "sinal da margem inconsistente com status de eleito",
    "margem assimétrica na lista (bug no cálculo do corte)",
}


def validar(con, verbose: bool = True) -> tuple[dict[str, int], bool]:
    """Roda as checagens. Devolve (resultados, ok) — ok=False bloqueia a análise."""
    resultados: dict[str, int] = {}
    ok = True
    if verbose:
        print("\n=== validação ===")
    for nome, sql in CHECAGENS.items():
        n = con.execute(sql).fetchone()[0]
        resultados[nome] = n
        if n and nome in BLOQUEANTES:
            ok = False
            marca = "!! "
        elif n and nome in INFORMATIVAS:
            marca = "i  "
        elif n:
            marca = "?  "
        else:
            marca = "ok "
        if verbose:
            print(f"  {marca}{nome}: {n:,}")

    if verbose:
        print("\n  Listas fora da amostra (descarte declarado, não silencioso):")
        for m, n in con.execute("SELECT motivo, n_listas FROM vw_listas_descartadas "
                                "ORDER BY n_listas DESC").fetchall():
            print(f"    {m}: {n:,}")

        print("\n  Totais por ano — conferir contra as estatísticas do TSE:")
        for l in con.execute("""
            SELECT ano_eleicao, COUNT(*) AS candidaturas,
                   SUM(CASE WHEN eleito THEN 1 ELSE 0 END) AS eleitos,
                   ROUND(SUM(receita_total)/1e6, 2) AS receita_mi,
                   ROUND(SUM(despesa_total)/1e6, 2) AS despesa_mi
            FROM vw_financas_candidato GROUP BY 1 ORDER BY 1
        """).fetchall():
            print(f"    {l[0]}: {l[1]:>6,} candidaturas | {l[2]:>5,} eleitos "
                  f"| R$ {l[3]:>9,.2f} mi receita | R$ {l[4]:>9,.2f} mi despesa "
                  f"(valores nominais)")
    return resultados, ok


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Carrega os CSVs do TSE no DuckDB.")
    p.add_argument("--anos", nargs="+", type=int, default=[2020, 2024])
    p.add_argument("--cargo", default="VEREADOR")
    p.add_argument("--uf", default="RS")
    p.add_argument("--banco", default=str(BANCO_PADRAO))
    p.add_argument("--recriar", action="store_true")
    args = p.parse_args(argv)

    con = criar_banco(args.banco, recriar=args.recriar)
    carregar_tse(con, args.anos, cargo=args.cargo.upper(), uf=args.uf.upper())
    aplicar_views(con)
    _, ok = validar(con)
    con.close()
    if not ok:
        print("\n[BLOQUEIO] checagem estrutural falhou — não rode a análise causal.",
              file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
