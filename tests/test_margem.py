"""Testes da camada SQL — variável de corte e integridade dos dados.

O erro mais provável e mais caro deste projeto é calcular a margem no
ranking da disputa inteira em vez de dentro da lista. Vários testes aqui
existem só para travar esse comportamento, porque é o tipo de coisa que
se reintroduz sem perceber numa refatoração.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from python.ingest.load_to_duckdb import criar_banco   # noqa: E402


# ---------------------------------------------------------------------
# Variável de corte
# ---------------------------------------------------------------------
def test_sinal_da_margem_bate_com_eleito(con):
    """margem > 0 <=> eleito. Sem exceção, e margem nunca é zero."""
    n = con.execute("SELECT COUNT(*) FROM vw_check_sinal_margem").fetchone()[0]
    assert n == 0, f"{n} candidaturas com sinal de margem inconsistente"


def test_margem_simetrica_dentro_da_lista(con):
    """A folga do último eleito e a do primeiro suplente são a mesma
    distância, com sinais opostos. Assimetria = bug no cálculo do corte."""
    df = con.execute("""
        SELECT * FROM vw_check_simetria_margem
        WHERE margem_pos IS NOT NULL AND margem_neg IS NOT NULL
    """).df()
    assert len(df) > 0, "nenhuma lista com par de fronteira: amostra vazia"
    assert ((df["margem_pos"] + df["margem_neg"]).abs() < 1e-9).all()


def test_listas_sem_corte_sao_excluidas(con):
    """Lista que elegeu todo mundo (ou ninguém) não tem contrafactual
    interno e não pode entrar na amostra."""
    df = con.execute("""
        SELECT id_lista_disputa,
               COUNT(*) FILTER (WHERE eleito)     AS n_eleitos,
               COUNT(*) FILTER (WHERE NOT eleito) AS n_nao_eleitos
        FROM vw_margem_candidato GROUP BY 1
    """).df()
    assert (df["n_eleitos"] >= 1).all()
    assert (df["n_nao_eleitos"] >= 1).all()


def test_empate_no_corte_e_descartado(con):
    """No Brasil o empate é desempatado pela idade, não por votos: nesses
    casos o tratamento não é função da variável de corte."""
    n = con.execute("""
        SELECT COUNT(*) FROM vw_margem_candidato m
        JOIN vw_corte_lista k USING (id_lista_disputa)
        WHERE k.v_ultimo_eleito = k.v_primeiro_suplente
    """).fetchone()[0]
    assert n == 0


def test_descartes_sao_contados_e_nao_silenciosos(con):
    """Toda lista fora da amostra tem que aparecer com motivo declarado."""
    df = con.execute("SELECT * FROM vw_listas_descartadas").df()
    assert set(df.columns) == {"motivo", "n_listas"}
    assert (df["n_listas"] > 0).all()


def test_amostra_de_fronteira_so_tem_par_completo(con):
    """Uma lista pode perder um dos lados do par quando há empate em
    votos entre dois candidatos dela (os empatados saem da amostra).
    Meio par não é comparação, então a amostra de fronteira exclui a
    lista inteira nesse caso."""
    df = con.execute("""
        SELECT id_lista_disputa,
               COUNT(*) FILTER (WHERE eh_ultimo_eleito)     AS n_ue,
               COUNT(*) FILTER (WHERE eh_primeiro_suplente) AS n_ps
        FROM vw_amostra_fronteira GROUP BY 1
    """).df()
    assert len(df) > 100
    assert (df["n_ue"] >= 1).all()
    assert (df["n_ps"] >= 1).all()


def test_amostra_de_fronteira_esta_contida_na_amostra_principal(con):
    a = con.execute("SELECT COUNT(*) FROM vw_amostra_fronteira").fetchone()[0]
    b = con.execute("SELECT COUNT(*) FROM vw_amostra_rdd").fetchone()[0]
    assert 0 < a < b


def test_margem_nao_usa_ranking_da_disputa(con):
    """Teste de regressão do erro conceitual.

    Em lista aberta existem candidatos eleitos que NÃO estão entre os N
    mais votados do município — eleitos pela força da lista. Se a margem
    fosse calculada no ranking geral, essa gente teria margem negativa.
    O teste documenta que o fenômeno existe nos dados: é a razão de a
    margem ser calculada por lista.
    """
    n = con.execute("""
        SELECT COUNT(*) FROM (
            SELECT eleito,
                   RANK() OVER (PARTITION BY ano_eleicao, municipio
                                ORDER BY votos_nominais DESC) AS rank_disputa,
                   SUM(CASE WHEN eleito THEN 1 ELSE 0 END)
                       OVER (PARTITION BY ano_eleicao, municipio) AS cadeiras
            FROM vw_financas_candidato
        ) WHERE eleito AND rank_disputa > cadeiras
    """).fetchone()[0]
    assert n > 0, ("nenhum eleito fora do topo do ranking municipal — o dado "
                   "sintético deixou de reproduzir a lista aberta e o teste "
                   "perdeu o sentido")


# ---------------------------------------------------------------------
# Integridade das finanças
# ---------------------------------------------------------------------
def test_receita_bate_com_a_soma_dos_lancamentos(con):
    """A view agregada não pode divergir da tabela de lançamentos."""
    a = con.execute("SELECT ROUND(SUM(valor), 2) FROM receitas").fetchone()[0]
    b = con.execute("SELECT ROUND(SUM(receita_total), 2) "
                    "FROM vw_financas_candidato").fetchone()[0]
    assert abs(float(a) - float(b)) < 1.0


def test_candidatura_sem_receita_nao_desaparece(con):
    """LEFT JOIN: quem não arrecadou aparece com 0, não some da amostra.
    Excluir esses casos em silêncio enviesa a média de gasto para cima."""
    a = con.execute("SELECT COUNT(*) FROM candidatos c JOIN resultados r "
                    "ON r.sq_candidato = c.sq_candidato "
                    "WHERE c.situacao_candidatura = 'APTO'").fetchone()[0]
    b = con.execute("SELECT COUNT(*) FROM vw_financas_candidato").fetchone()[0]
    assert a == b


def test_deflacao_e_aplicada(con):
    """Valor real e nominal têm de diferir nos anos que não são o ano-base."""
    from python.ingest.deflator import ANO_BASE
    df = con.execute("""
        SELECT ano_eleicao, ANY_VALUE(fator_deflator) AS fator,
               ANY_VALUE(deflacionado) AS ok
        FROM vw_financas_candidato GROUP BY 1 ORDER BY 1
    """).df()
    assert df["ok"].all(), "algum ano ficou sem deflator IPCA"
    for _, r in df.iterrows():
        if int(r["ano_eleicao"]) == ANO_BASE:
            assert abs(r["fator"] - 1.0) < 1e-6
        else:
            assert r["fator"] > 1.0, "ano anterior ao base deveria ter fator > 1"


def test_hash_nao_guarda_documento_em_claro(con):
    """Nenhum CPF/CNPJ pode sobreviver à ingestão em texto legível."""
    n = con.execute("""
        SELECT COUNT(*) FROM receitas
        WHERE doador_hash IS NOT NULL AND length(doador_hash) < 32
    """).fetchone()[0]
    assert n == 0
    amostra = con.execute("SELECT doador_hash FROM receitas "
                          "WHERE doador_hash IS NOT NULL LIMIT 1").fetchone()[0]
    assert not amostra.isdigit(), "doador_hash parece ser o documento em claro"


# ---------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------
def test_schema_aplica_em_banco_vazio(tmp_path):
    """schema.sql + views rodam do zero, sem dado nenhum."""
    c = criar_banco(tmp_path / "vazio.duckdb", recriar=True)
    assert c.execute("SELECT COUNT(*) FROM vw_financas_candidato").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM vw_painel_rdd").fetchone()[0] == 0
    c.close()


def test_schema_e_reexecutavel(tmp_path):
    """Rodar a carga duas vezes não pode duplicar candidatura."""
    from python.ingest.load_to_duckdb import aplicar_views
    c = criar_banco(tmp_path / "re.duckdb", recriar=True)
    aplicar_views(c)
    aplicar_views(c)
    assert c.execute("SELECT COUNT(*) FROM vw_amostra_rdd").fetchone()[0] == 0
    c.close()
