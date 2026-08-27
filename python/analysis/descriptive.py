"""Camada descritiva: lê as views SQL e devolve as tabelas do relatório.

Nenhuma agregação acontece aqui em pandas — as consultas voltam já
agregadas pelo DuckDB. Este módulo só formata.

Valores monetários saem deflacionados (reais do ano-base definido em
python/ingest/deflator.py), exceto onde a coluna diz "nominal".
"""

from __future__ import annotations

import pandas as pd


def resumo_por_ano(con) -> pd.DataFrame:
    return con.execute("""
        SELECT ano_eleicao,
               COUNT(*)                                   AS candidaturas,
               SUM(CASE WHEN eleito THEN 1 ELSE 0 END)    AS eleitos,
               SUM(CASE WHEN tem_prestacao_contas THEN 1 ELSE 0 END) AS com_prestacao,
               ROUND(SUM(despesa_total_real) / 1e6, 2)    AS despesa_total_mi,
               ROUND(MEDIAN(despesa_total_real), 2)       AS despesa_mediana,
               ROUND(AVG(despesa_total_real), 2)          AS despesa_media,
               ROUND(MEDIAN(gasto_por_voto), 2)           AS gasto_por_voto_mediano
        FROM vw_financas_candidato
        GROUP BY 1 ORDER BY 1
    """).df()


def composicao_receita(con) -> pd.DataFrame:
    """De onde vem o dinheiro de campanha, por ano."""
    return con.execute("""
        SELECT ano_eleicao,
               ROUND(SUM(receita_fefc)            / NULLIF(SUM(receita_total),0), 4) AS share_fefc,
               ROUND(SUM(receita_fp)              / NULLIF(SUM(receita_total),0), 4) AS share_fundo_partidario,
               ROUND(SUM(receita_doacao_pf)       / NULLIF(SUM(receita_total),0), 4) AS share_doacao_pf,
               ROUND(SUM(receita_doacao_partido)  / NULLIF(SUM(receita_total),0), 4) AS share_doacao_partido,
               ROUND(SUM(receita_propria)         / NULLIF(SUM(receita_total),0), 4) AS share_propria,
               ROUND(SUM(receita_outros)          / NULLIF(SUM(receita_total),0), 4) AS share_outros
        FROM vw_financas_candidato
        GROUP BY 1 ORDER BY 1
    """).df()


def gasto_por_decil(con) -> pd.DataFrame:
    """Concentração: quanto do dinheiro total fica em cada decil de gasto.

    A média de gasto por candidato é estatística ruim num universo em
    que a maioria gasta pouco e uma minoria gasta muito.
    """
    return con.execute("""
        WITH d AS (
            SELECT ano_eleicao, despesa_total_real, eleito,
                   NTILE(10) OVER (PARTITION BY ano_eleicao
                                   ORDER BY despesa_total_real) AS decil
            FROM vw_financas_candidato
        )
        SELECT ano_eleicao, decil,
               COUNT(*)                                       AS n,
               ROUND(SUM(despesa_total_real), 2)              AS despesa_decil,
               ROUND(100.0 * SUM(despesa_total_real)
                     / SUM(SUM(despesa_total_real)) OVER (PARTITION BY ano_eleicao), 2)
                                                              AS pct_do_total,
               ROUND(100.0 * AVG(CASE WHEN eleito THEN 1.0 ELSE 0 END), 2)
                                                              AS pct_eleitos
        FROM d GROUP BY 1, 2 ORDER BY 1, 2
    """).df()


def taxa_sucesso_por_gasto(con) -> pd.DataFrame:
    """Associação BRUTA entre gasto e eleição, por decil.

    É a correlação que o projeto existe para problematizar: mistura o
    efeito do dinheiro com o fato de que candidatos com mais chance
    atraem mais doação. Publicada explicitamente rotulada como
    descritiva, nunca como estimativa de efeito.
    """
    return con.execute("""
        WITH d AS (
            SELECT eleito, despesa_total_real,
                   NTILE(10) OVER (ORDER BY despesa_total_real) AS decil
            FROM vw_financas_candidato
        )
        SELECT decil, COUNT(*) AS n,
               ROUND(MEDIAN(despesa_total_real), 2)                        AS despesa_mediana,
               ROUND(100.0 * AVG(CASE WHEN eleito THEN 1.0 ELSE 0 END), 2) AS pct_eleitos
        FROM d GROUP BY 1 ORDER BY 1
    """).df()


def listas_descartadas(con) -> pd.DataFrame:
    """Listas fora da amostra e o motivo — descarte declarado."""
    return con.execute("SELECT * FROM vw_listas_descartadas "
                       "ORDER BY n_listas DESC").df()


def contagem_por_janela(con) -> pd.DataFrame:
    """Quantas observações sobrevivem a cada janela candidata."""
    return con.execute("SELECT * FROM vw_contagem_por_janela").df()


def qualidade_pareamento(con) -> pd.DataFrame:
    """Distribuição dos níveis de match do painel entre eleições."""
    return con.execute("""
        SELECT ano_t, ano_t1, nivel_match, regra, COUNT(*) AS n
        FROM painel_link GROUP BY ALL ORDER BY ano_t, nivel_match
    """).df()


def painel_rdd(con, apenas_fronteira: bool = False) -> pd.DataFrame:
    """Painel do RDD. `apenas_fronteira` restringe ao par
    (último eleito, primeiro suplente) de cada lista — amostra
    conservadora usada como robustez."""
    where = "WHERE eh_ultimo_eleito OR eh_primeiro_suplente" if apenas_fronteira else ""
    df = con.execute(f"SELECT * FROM vw_painel_rdd {where}").df()
    return preparar_desfechos(df)


def preparar_desfechos(df: pd.DataFrame) -> pd.DataFrame:
    """Converte booleanos em 0/1 e cria as covariáveis derivadas."""
    df = df.copy()
    for c in ("concorreu_t1", "eleito_t1", "eleito"):
        if c in df.columns:
            df[c] = df[c].astype(float)
    if "genero" in df.columns:
        df["genero_fem"] = (df["genero"].astype(str).str.upper()
                            .str.startswith("F")).astype(float)
    return df
