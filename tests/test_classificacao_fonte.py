"""Regressão: textos reais do TSE devem cair na fonte certa.
Bug original: padrão 'FUNDO ESPECIAL DE FINANCIAMENTO' não casava com o
texto curto 'FUNDO ESPECIAL', zerando o FEFC em 2020/2024; e em 2016 o
Fundo Partidário (coluna 'Fonte recurso') não entrava na classificação.
"""
import sys
from pathlib import Path
import duckdb
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from python.ingest.load_to_duckdb import _case_fonte  # noqa: E402

CASOS = [
    ("Recursos de partido político", "FUNDO ESPECIAL", None, "fundo_eleitoral"),
    ("Recursos de outros candidatos", "FUNDO ESPECIAL", None, "fundo_eleitoral"),
    ("Fundo Especial de Financiamento de Campanha", "", None, "fundo_eleitoral"),
    ("Recursos de partido político", "FUNDO PARTIDÁRIO", None, "fundo_partidario"),
    ("Recursos de partido político", "OUTROS RECURSOS", None, "doacao_partido"),
    ("Recursos de pessoas físicas", "OUTROS RECURSOS", None, "doacao_pf"),
    ("Recursos próprios", "OUTROS RECURSOS", None, "proprio"),
    ("Recursos de Financiamento Coletivo", "OUTROS RECURSOS", None, "outros"),
    # 2016 legado: Fundo Partidario vem na coluna extra
    ("Recursos de partido político", "#NULO", "Fundo Partidario", "fundo_partidario"),
    ("Recursos de partido político", "#NULO", "Outros Recursos", "doacao_partido"),
]


@pytest.mark.parametrize("tipo,origem,extra,esperado", CASOS)
def test_classificacao(tipo, origem, extra, esperado):
    con = duckdb.connect()
    q = lambda v: "NULL" if v is None else "'" + v.replace("'", "''") + "'"
    expr = _case_fonte(q(origem), q(tipo), q(extra) if extra else None)
    assert con.execute(f"SELECT {expr}").fetchone()[0] == esperado
