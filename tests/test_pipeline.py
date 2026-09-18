"""Testes do pareamento entre eleições, das regras de decisão e do deflator.

O pareamento é a peça mais frágil do pipeline: o TSE não publica um
identificador estável de pessoa, e um homônimo pareado errado vira
efeito espúrio. O gerador sintético injeta homônimos e omite o CPF de
parte dos registros justamente para que esses testes tenham o que pegar.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from python.analysis import regras_decisao as regras   # noqa: E402
from python.analysis.build_panel import normalizar     # noqa: E402
from python.ingest.deflator import (ANO_BASE, IPCA_ANUAL,  # noqa: E402
                                    construir_indice, fator)


# ---------------------------------------------------------------------
# Pareamento entre eleições
# ---------------------------------------------------------------------
def test_pareamento_acerta_a_pessoa(con, gabarito):
    """Contra o gabarito do simulador: quem o pipeline pareou é mesmo a
    pessoa certa? Erro aqui não aparece em nenhuma estatística de
    ajuste — só num teste contra a verdade conhecida."""
    link = con.execute("SELECT sq_t, sq_t1 FROM painel_link").df()
    verdade = gabarito["gabarito_painel"][["sq_t", "sq_t1"]]
    m = link.merge(verdade, on="sq_t", how="inner", suffixes=("_obs", "_real"))
    assert len(m) > 100, "pareamento pequeno demais para o teste ter poder"
    acerto = (m["sq_t1_obs"] == m["sq_t1_real"]).mean()
    assert acerto == 1.0, f"pareamento errou {1 - acerto:.2%} dos pares"


def test_pareamento_cobre_a_maior_parte_dos_reincidentes(con, gabarito):
    """A cobertura não precisa ser total, mas precisa ser reportável."""
    n_link = con.execute("SELECT COUNT(*) FROM painel_link").fetchone()[0]
    n_real = len(gabarito["gabarito_painel"])
    assert n_link / n_real > 0.90, (
        f"cobertura de {n_link / n_real:.1%} — investigar a cascata antes de usar")


def test_pareamento_nao_reutiliza_candidatura_de_t1(con):
    """Cada candidatura de t+1 pode ser destino de no máximo um par."""
    n = con.execute("""
        SELECT COUNT(*) FROM (SELECT sq_t1 FROM painel_link
                              GROUP BY 1 HAVING COUNT(*) > 1)
    """).fetchone()[0]
    assert n == 0


def test_cpf_ausente_cai_para_pareamento_por_nome(con):
    """O TSE deixou de publicar o CPF em parte dos arquivos. A cascata
    tem que continuar funcionando sem ele — e registrar o nível usado."""
    niveis = con.execute("SELECT DISTINCT nivel_match FROM painel_link").df()
    assert 1 in niveis["nivel_match"].values, "nenhum par por CPF"
    assert 2 in niveis["nivel_match"].values, (
        "nenhum par por nome — a cascata não está sendo exercitada")


def test_normalizar_remove_acento_e_pontuacao():
    assert normalizar("José D'Ávila  Júnior") == "JOSE D AVILA JUNIOR"
    assert normalizar(None) == ""
    assert normalizar("  maria   silva ") == "MARIA SILVA"


# ---------------------------------------------------------------------
# Regras de decisão
# ---------------------------------------------------------------------
def _relatorio_base() -> dict:
    return {
        "densidade": {"p_valor": 0.5},
        "placebo_covariaveis": [{"desfecho": f"c{i}", "p_valor": 0.4}
                                for i in range(5)],
        "placebo_cortes": [{"corte_placebo": c, "p_valor": 0.6}
                           for c in (-0.04, -0.02, 0.02, 0.04)],
        "varredura_janelas": [{"janela": h, "tau": 0.50 + 0.01 * i}
                              for i, h in enumerate((0.01, 0.02, 0.03, 0.05))],
        "estimativas": [{"desfecho": "concorreu_t1", "tau": 0.004, "p_valor": 0.80}],
        "comparacao_estimadores": [{"tau": 0.5, "erro_padrao": 0.08},
                                   {"tau": 0.5, "erro_padrao": 0.06}],
    }


def test_regra_identificado_quando_tudo_passa():
    v = regras.avaliar(_relatorio_base(), "ln_receita_t1_cond")
    assert v.status == "IDENTIFICADO"
    assert not v.alertas


def test_regra_bloqueia_com_densidade_rejeitada():
    r = _relatorio_base()
    r["densidade"] = {"p_valor": 0.001}
    v = regras.avaliar(r, "ln_receita_t1_cond")
    assert v.status == "NAO_IDENTIFICADO"
    assert any("densidade" in m for m in v.motivos)


def test_regra_bloqueia_com_covariaveis_descontinuas():
    r = _relatorio_base()
    r["placebo_covariaveis"] = [{"desfecho": "c1", "p_valor": 0.001},
                                {"desfecho": "c2", "p_valor": 0.01},
                                {"desfecho": "c3", "p_valor": 0.40}]
    v = regras.avaliar(r, "ln_receita_t1_cond")
    assert v.status == "NAO_IDENTIFICADO"


def test_uma_covariavel_falha_vira_alerta_e_nao_bloqueio():
    r = _relatorio_base()
    r["placebo_covariaveis"][0]["p_valor"] = 0.01
    v = regras.avaliar(r, "ln_receita_t1_cond")
    assert v.status == "IDENTIFICADO"
    assert v.alertas


def test_regra_marca_condicional_quando_ha_selecao():
    """Se ser eleito muda a chance de voltar a concorrer, o efeito sobre
    receita passa a ser condicional a recandidatar-se."""
    r = _relatorio_base()
    r["estimativas"] = [{"desfecho": "concorreu_t1", "tau": 0.08, "p_valor": 0.01}]
    v = regras.avaliar(r, "ln_receita_t1_cond")
    assert v.status == "CONDICIONAL"
    assert any("CONDICIONAL" in m for m in v.motivos)


def test_regra_bloqueia_com_troca_de_sinal_entre_janelas():
    r = _relatorio_base()
    r["varredura_janelas"] = [{"janela": 0.01, "tau": 0.4},
                              {"janela": 0.02, "tau": -0.3},
                              {"janela": 0.05, "tau": 0.5}]
    v = regras.avaliar(r, "ln_receita_t1_cond")
    assert v.status == "NAO_IDENTIFICADO"


def test_regra_alerta_quando_estimadores_divergem():
    r = _relatorio_base()
    r["comparacao_estimadores"] = [{"tau": 0.50, "erro_padrao": 0.02},
                                   {"tau": 0.95, "erro_padrao": 0.02}]
    v = regras.avaliar(r, "ln_receita_t1_cond")
    assert any("divergem" in a for a in v.alertas)


def test_regra_bloqueia_com_ciclos_significativos_e_opostos():
    """Dois ciclos, cada um individualmente significativo, com sinais
    opostos: contradição real, não ruído -- tem de bloquear."""
    r = _relatorio_base()
    r["heterogeneidade_ciclo"] = [
        {"ciclo": 2020, "tau": 0.45, "p_valor": 0.01},
        {"ciclo": 2016, "tau": -0.38, "p_valor": 0.02},
    ]
    v = regras.avaliar(r, "ln_receita_t1_cond")
    assert v.status == "NAO_IDENTIFICADO"
    assert any("ciclo" in m for m in v.motivos)


def test_regra_alerta_com_sinais_diferentes_mas_nao_ambos_significativos():
    """Sinais diferentes entre ciclos, mas só um é significativo --
    compatível com ruído de amostra por ciclo. Alerta, não bloqueio:
    dois grupos têm bem menos poder para revelar tendência que os sete
    pontos da varredura de janela."""
    r = _relatorio_base()
    r["heterogeneidade_ciclo"] = [
        {"ciclo": 2020, "tau": 0.45, "p_valor": 0.01},
        {"ciclo": 2016, "tau": -0.05, "p_valor": 0.80},
    ]
    v = regras.avaliar(r, "ln_receita_t1_cond")
    assert v.status == "IDENTIFICADO"
    assert any("ciclo" in a for a in v.alertas)


def test_regra_ignora_heterogeneidade_com_um_ciclo_so():
    r = _relatorio_base()
    r["heterogeneidade_ciclo"] = [{"ciclo": 2020, "tau": 0.45, "p_valor": 0.01}]
    v = regras.avaliar(r, "ln_receita_t1_cond")
    assert v.status == "IDENTIFICADO"
    assert not any("ciclo" in m for m in v.motivos + v.alertas)


# ---------------------------------------------------------------------
# Deflator
# ---------------------------------------------------------------------
def test_indice_tem_base_100_no_ano_base():
    idx = construir_indice()
    assert idx[ANO_BASE] == pytest.approx(100.0)


def test_indice_e_monotonico():
    """Com inflação positiva em todos os anos da série, o nível de preços
    só sobe."""
    idx = construir_indice()
    anos = sorted(idx)
    assert all(idx[b] > idx[a] for a, b in zip(anos, anos[1:]))


def test_fator_converte_para_o_ano_base():
    """Deflacionar um ano anterior tem que aumentar o valor."""
    ano_antigo = min(IPCA_ANUAL)
    assert fator(ano_antigo) > 1.0
    assert fator(ANO_BASE) == pytest.approx(1.0)
    assert fator(1900) is None


def test_ano_sem_taxa_nao_recebe_deflacao_silenciosa():
    """Ano fora da série volta None, e a validação da carga acusa —
    inventar fator 1 em silêncio seria comparar reais de anos
    diferentes sem avisar."""
    assert fator(max(IPCA_ANUAL) + 5) is None
