"""Testes da camada de contexto (vantagem bruta x causal, dinheiro público).

O ponto que mais importa: no dado sintético, a qualidade não observada
afeta receita E chance de vencer — exatamente o viés que o projeto existe
para corrigir. Então a vantagem bruta TEM de sair maior que o efeito
causal verdadeiro. Se não sair, ou o simulador perdeu o viés, ou a
comparação bruta está errada.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from python.analysis import contexto as ctx   # noqa: E402


def test_shares_publicos_sao_proporcoes_validas(con):
    ctx.aplicar(con)
    fp = ctx.financiamento_publico(con)
    assert len(fp) >= 2
    for c in ("share_fefc", "share_fundo_partidario", "share_publico"):
        assert ((fp[c] >= 0) & (fp[c] <= 1)).all(), c
    assert np.allclose(fp["share_publico"],
                       fp["share_fefc"] + fp["share_fundo_partidario"])


def test_vantagem_bruta_maior_que_efeito_causal(con, tau_verdadeiro):
    """Viés de seleção plantado no simulador: a comparação simples
    superestima o efeito do mandato."""
    ctx.aplicar(con)
    bruta = ctx.vantagem_bruta(con)
    assert bruta["tau"].iloc[0] > tau_verdadeiro


def test_vantagem_por_ano_so_inclui_anos_com_painel(con):
    ctx.aplicar(con)
    df = con.execute("SELECT * FROM vw_ctx_vantagem_bruta").df()
    anos_painel = set(con.execute(
        "SELECT DISTINCT ano_t FROM painel_link").df()["ano_t"])
    assert set(df["ano_t"]) == anos_painel
    assert set(df["eleito_t"]) == {True, False}


def test_conversao_log_para_percentual():
    assert abs(ctx.pct(0.0)) < 1e-12
    assert abs(ctx.pct(np.log(1.5)) - 50.0) < 1e-9


def test_rodar_sem_relatorio_nao_quebra(con, tmp_path, monkeypatch):
    """Sem relatorio_rdd.json, roda a parte descritiva e só avisa."""
    monkeypatch.setattr(ctx, "DIR_TAB", tmp_path / "tab")
    monkeypatch.setattr(ctx, "DIR_FIG", tmp_path / "fig")
    out = ctx.rodar(con, relatorio=tmp_path / "nao_existe.json", verbose=False)
    assert len(out["comparacao"]) == 1
    assert (tmp_path / "fig" / "ctx_dinheiro_publico.png").exists()


def test_checar_fefc_acusa_share_zerado_em_ano_municipal_recente():
    import pandas as pd
    ok = pd.DataFrame({"ano_eleicao": [2016, 2020, 2024],
                       "share_fefc": [0.0, 0.35, 0.63]})
    ruim = pd.DataFrame({"ano_eleicao": [2016, 2020, 2024],
                         "share_fefc": [0.0, 0.0, 0.0]})
    assert ctx.checar_fefc(ok) == []
    assert len(ctx.checar_fefc(ruim)) == 2
