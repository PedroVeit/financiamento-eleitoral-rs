"""Corrige a classificação de fonte de receita (FEFC e Fundo Partidário 2016).

1. Ajusta python/ingest/load_to_duckdb.py (idempotente).
2. Reclassifica a tabela `receitas` do banco existente a partir de
   `origem_bruta`, sem recarregar nada. Totais de receita NÃO mudam.

Uso (raiz do repo):  python corrigir_fonte.py
"""
from pathlib import Path
import sys
import duckdb

RAIZ = Path(__file__).resolve().parent
ARQ = RAIZ / "python" / "ingest" / "load_to_duckdb.py"
BANCO = RAIZ / "data" / "db" / "financiamento.duckdb"

# ---- 1. código ------------------------------------------------------
s = ARQ.read_text(encoding="utf-8")
orig = s
s = s.replace(
    "def _case_fonte(origem: str, fonte: str) -> str:\n"
    "    txt = f\"UPPER(COALESCE({fonte}, '') || ' ' || COALESCE({origem}, ''))\"",
    "def _case_fonte(origem: str, fonte: str, extra: str | None = None) -> str:\n"
    "    # `extra`: coluna adicional de texto (2016: Fundo Partidario fica em\n"
    "    # \"Fonte recurso\", separada do \"Tipo receita\").\n"
    "    ext = f\" || ' ' || COALESCE({extra}, '')\" if extra else \"\"\n"
    "    txt = f\"UPPER(COALESCE({fonte}, '') || ' ' || COALESCE({origem}, ''){ext})\"")
s = s.replace("LIKE '%FUNDO ESPECIAL DE FINANCIAMENTO%'", "LIKE '%FUNDO ESPECIAL%'")
s = s.replace("{_case_fonte(c['origem'], c['fonte'])}",
              "{_case_fonte(c['origem'], c['fonte'], c['fonte_coarse'])}")
if s != orig:
    ARQ.write_text(s, encoding="utf-8")
    print("codigo: load_to_duckdb.py corrigido")
else:
    print("codigo: ja estava corrigido (nada a fazer)")

ok = ("LIKE '%FUNDO ESPECIAL%'" in s and "extra: str | None" in s
      and "c['fonte_coarse'])}" in s)
if not ok:
    sys.exit("ERRO: o arquivo nao ficou como esperado; me mande a saida.")

# ---- 2. banco -------------------------------------------------------
sys.path.insert(0, str(RAIZ))
from python.ingest.load_to_duckdb import _case_fonte  # noqa: E402

con = duckdb.connect(str(BANCO))
antes = con.execute("SELECT SUM(valor) FROM receitas").fetchone()[0]
con.execute(f"UPDATE receitas SET fonte = {_case_fonte('origem_bruta', chr(39)*2)}")
depois = con.execute("SELECT SUM(valor) FROM receitas").fetchone()[0]
assert antes == depois, "total mudou: abortar"
print("\nreceita por fonte e ano (R$ milhoes):")
print(con.execute("""
    SELECT ano_eleicao,
           ROUND(SUM(valor) FILTER (WHERE fonte='fundo_eleitoral')/1e6,1) AS fefc,
           ROUND(SUM(valor) FILTER (WHERE fonte='fundo_partidario')/1e6,1) AS fundo_part,
           ROUND(SUM(valor) FILTER (WHERE fonte='doacao_partido')/1e6,1) AS rep_partido,
           ROUND(SUM(valor) FILTER (WHERE fonte='doacao_pf')/1e6,1) AS pf,
           ROUND(SUM(valor) FILTER (WHERE fonte='proprio')/1e6,1) AS proprio,
           ROUND(SUM(valor) FILTER (WHERE fonte='outros')/1e6,1) AS outros
    FROM receitas GROUP BY 1 ORDER BY 1""").df().to_string(index=False))
con.close()
print("\nok. Proximo: python -m python.run_pipeline --banco data\\db\\financiamento.duckdb")
