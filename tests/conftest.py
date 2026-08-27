"""Fixtures dos testes.

O banco sintético é construído uma vez por sessão (cerca de 3 segundos)
e reaproveitado. Ele passa pelo caminho de ingestão inteiro — CSVs no
formato do TSE, carga em DuckDB, views, pareamento do painel — então os
testes exercitam o pipeline de verdade, não uma maquete dele.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from python.analysis.descriptive import preparar_desfechos       # noqa: E402
from python.synthetic.gerar_dados_sinteticos import (            # noqa: E402
    TAU_PADRAO, construir_banco)

#: municípios do banco de teste. Menos que isso e a varredura de janelas
#: estreitas fica sem observações.
N_MUNICIPIOS = 90


@pytest.fixture(scope="session")
def sintetico(tmp_path_factory):
    """(conexão, gabarito) do banco sintético com efeito conhecido."""
    caminho = tmp_path_factory.mktemp("db") / "sintetico.duckdb"
    con, info = construir_banco(caminho, n_municipios=N_MUNICIPIOS, semente=11)
    yield con, info
    con.close()


@pytest.fixture(scope="session")
def con(sintetico):
    return sintetico[0]


@pytest.fixture(scope="session")
def gabarito(sintetico):
    return sintetico[1]


@pytest.fixture(scope="session")
def painel(con):
    """Painel do RDD, com os desfechos já preparados."""
    return preparar_desfechos(con.execute("SELECT * FROM vw_painel_rdd").df())


@pytest.fixture(scope="session")
def tau_verdadeiro():
    return TAU_PADRAO
