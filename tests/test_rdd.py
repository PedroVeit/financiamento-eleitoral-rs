"""Testes do estimador de RDD contra dado sintético de efeito conhecido.

A lógica: se o estimador não recupera um efeito plantado por mim mesmo,
ele não tem por que ser confiável num dado real onde o efeito verdadeiro
é desconhecido.

Foi um teste desta família que pegou o bug mais perigoso do projeto: o
`log()` do DuckDB é logaritmo de BASE 10, não natural, e todos os
coeficientes saíam divididos por ln(10) ≈ 2,3 — com aparência
inteiramente plausível. Um resultado plausível e errado é pior que um
obviamente quebrado, porque não convida a verificação.
`test_unidade_e_log_natural` existe para que isso não volte.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from python.analysis import rdd_model as rdd                     # noqa: E402
from python.analysis.descriptive import preparar_desfechos       # noqa: E402
from python.synthetic.gerar_dados_sinteticos import construir_banco  # noqa: E402

DESFECHO = "ln_receita_t1_cond"


# ---------------------------------------------------------------------
# O teste central
# ---------------------------------------------------------------------
def test_recupera_efeito_verdadeiro(painel, tau_verdadeiro):
    r = rdd.estimar_rdd(painel, DESFECHO)
    assert r.ic95[0] < tau_verdadeiro < r.ic95[1], (
        f"τ verdadeiro {tau_verdadeiro} fora do IC95 "
        f"[{r.ic95[0]:.3f}, {r.ic95[1]:.3f}] (τ̂ = {r.tau:.3f})")


def test_efeito_zero_e_estimado_como_zero(tmp_path):
    """Placebo do gerador: sem efeito plantado, o estimador não pode
    encontrar efeito. Um estimador que só acha o que existe é metade do
    requisito; o outro metade é não achar o que não existe."""
    con, _ = construir_banco(tmp_path / "zero.duckdb", n_municipios=90,
                             efeito_verdadeiro=0.0, semente=99)
    df = preparar_desfechos(con.execute("SELECT * FROM vw_painel_rdd").df())
    con.close()
    r = rdd.estimar_rdd(df, DESFECHO)
    assert r.ic95[0] < 0 < r.ic95[1], f"falso positivo: {r}"


def test_unidade_e_log_natural(painel, tau_verdadeiro):
    """Guarda contra a regressão do bug log10: se alguém trocar ln() por
    log() no SQL, o efeito cai por um fator de ln(10) ≈ 2,3."""
    r = rdd.estimar_rdd(painel, DESFECHO)
    assert r.tau > tau_verdadeiro / 2, (
        "efeito suspeitosamente pequeno — verificar se o SQL usa ln() e não log()")


# ---------------------------------------------------------------------
# Concordância e estabilidade
# ---------------------------------------------------------------------
def test_dois_estimadores_concordam(painel):
    """rdrobust e o estimador próprio, na mesma banda, têm de dar a mesma
    estimativa pontual — o coeficiente 'Conventional' do rdrobust É a
    regressão local-linear com kernel triangular. Os erros-padrão
    diferem de propósito (o do rdrobust corrige viés de seleção de
    banda). Divergência no ponto significa bug de implementação."""
    comp = rdd.comparar_estimadores(painel, DESFECHO)
    assert len(comp) == 2
    assert abs(comp["tau"].iloc[0] - comp["tau"].iloc[1]) < 1e-6


def test_estimativa_estavel_entre_janelas(painel):
    v = rdd.varredura_janelas(painel, DESFECHO,
                              janelas=(0.01, 0.02, 0.03, 0.05, 0.08))
    taus = v["tau"].dropna()
    assert len(taus) == 5
    assert (taus > 0).all(), f"efeito troca de sinal entre janelas:\n{v}"
    assert taus.max() - taus.min() < 0.35, f"instável entre janelas:\n{v}"


def test_normalizacao_nao_muda_a_conclusao(painel):
    """A escolha de normalizar pela lista ou pela disputa não pode
    inverter o resultado."""
    a = rdd.estimar_rdd(painel, DESFECHO, running="margem_rel_lista")
    b = rdd.estimar_rdd(painel, DESFECHO, running="margem_rel_disputa")
    assert np.sign(a.tau) == np.sign(b.tau)
    assert abs(a.tau - b.tau) < 3 * max(a.erro_padrao, b.erro_padrao)


# ---------------------------------------------------------------------
# Validade do desenho
# ---------------------------------------------------------------------
def test_covariaveis_pre_tratamento_sao_continuas(painel):
    """Nas covariáveis fixadas antes da eleição, o salto tem de ser nulo.

    Tolerância de uma falha: testar 6 covariáveis a 5% produz, sob a
    hipótese nula, cerca de 0,3 falsos positivos — um acontece. Duas ou
    mais é padrão, não acaso.
    """
    covs = ["ln_receita_t", "ln_despesa_t", "share_fefc_t",
            "n_doadores_t", "idade_posse", "genero_fem"]
    tab = rdd.teste_continuidade_covariaveis(painel, covs)
    falhas = tab[tab["p_valor"] < 0.05]
    assert len(falhas) <= 1, f"descontinuidade em covariáveis:\n{tab}"


def test_cortes_placebo_nao_produzem_salto(painel):
    tab = rdd.teste_cortes_placebo(painel, DESFECHO,
                                   cortes=(-0.05, -0.03, 0.03, 0.05))
    n_signif = int((tab["p_valor"] < 0.05).sum())
    assert n_signif <= 1, f"salto em cortes sem regra:\n{tab}"


def test_densidade_nao_acusa_manipulacao(painel):
    r = rdd.teste_densidade(painel)
    assert "p_valor" in r, r
    assert r["p_valor"] > 0.05


def test_donut_nao_derruba_o_efeito(painel):
    tab = rdd.teste_donut(painel, DESFECHO, buracos=(0.0, 0.002, 0.005))
    taus = tab["tau"].dropna()
    assert len(taus) == 3
    assert (taus > 0).all(), f"efeito some ao excluir o entorno do corte:\n{tab}"


# ---------------------------------------------------------------------
# Unitários do estimador, sem banco
# ---------------------------------------------------------------------
def test_kernel_triangular():
    w = rdd.kernel_triangular(np.array([-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0]), h=1.0)
    assert w[0] == 0 and w[-1] == 0
    assert w[3] == pytest.approx(1.0)
    assert w[2] == pytest.approx(0.5)
    assert (w >= 0).all()


def test_local_linear_em_dgp_analitico():
    """Salto conhecido num DGP fechado, sem banco e sem SQL no caminho."""
    rng = np.random.default_rng(7)
    n = 8000
    x = rng.uniform(-1, 1, n)
    tau = 1.5
    y = 0.4 * x + tau * (x >= 0) + rng.normal(0, 0.3, n)
    r = rdd.local_linear(y, x, h=0.3)
    assert abs(r.tau - tau) < 4 * r.erro_padrao


def test_janela_menor_reduz_amostra_e_aumenta_incerteza(painel):
    pequena = rdd.estimar_rdd(painel, DESFECHO, janela=0.01, metodo="local")
    grande = rdd.estimar_rdd(painel, DESFECHO, janela=0.05, metodo="local")
    assert pequena.n < grande.n
    assert pequena.erro_padrao > grande.erro_padrao


def test_binscatter_nao_cruza_o_corte(painel):
    """Nenhum bin pode misturar eleitos e não eleitos: um bin a cavalo do
    corte suaviza visualmente exatamente o salto que o gráfico existe
    para mostrar."""
    bins = rdd.binscatter(painel, DESFECHO, janela=0.08, n_bins=20)
    assert len(bins) > 4
    assert not (bins["x"].abs() < 1e-12).any()
    assert set(bins["lado"]) == {"eleito", "nao_eleito"}
