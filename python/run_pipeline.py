"""Roda o pipeline inteiro: descritiva -> RDD -> robustez -> figuras.

    python -m python.run_pipeline --sintetico       # dados de teste
    python -m python.run_pipeline --banco data/db/financiamento.duckdb

Saídas: tabelas em outputs/tabelas/, figuras em outputs/figures/ e um
relatório consolidado em outputs/relatorio_rdd.json.

Ordem deliberada: a validação e as contagens por janela vêm ANTES da
estimativa causal. Escolher o recorte depois de ver o resultado é como
se fabrica falso positivo — e num projeto de portfólio o histórico de
commits denuncia isso.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from python.analysis import descriptive as desc          # noqa: E402
from python.analysis import rdd_model as rdd             # noqa: E402
from python.analysis import regras_decisao as regras     # noqa: E402
from python.ingest.load_to_duckdb import (               # noqa: E402
    aplicar_views, criar_banco, validar)
from python.viz import plots                             # noqa: E402

DIR_OUT = RAIZ / "outputs"
DIR_TAB = DIR_OUT / "tabelas"

# Desfechos do desenho causal.
#
# A separação entre margem EXTENSIVA e INTENSIVA é deliberada. Misturar
# as duas num único ln(1 + receita) põe uma pilha de zeros (quem não
# voltou a concorrer) no meio de valores na casa de ln(receita) ~ 11:
# infla a variância e transforma um efeito sobre captação num efeito
# sobre "continuar na política" mal disfarçado.
DESFECHOS: dict[str, tuple[str, str]] = {
    "concorreu_t1":       ("voltou a concorrer na eleição seguinte (0/1)", "extensiva"),
    "ln_receita_t1_cond": ("ln(receita na eleição seguinte)", "intensiva"),
    "ln_receita_t1":      ("ln(1 + receita), zeros inclusos", "mista"),
    "eleito_t1":          ("eleito na eleição seguinte (0/1)", "extensiva"),
    "share_fefc_t1":      ("participação do FEFC na receita seguinte", "composição"),
}
DESFECHO_PRINCIPAL = "ln_receita_t1_cond"

# Covariáveis fixadas ANTES do resultado eleitoral: têm de ser contínuas
# no corte. Só entram variáveis que variam DENTRO da lista — atributos
# constantes por lista (nº de candidatos, cadeiras) são contínuos por
# construção, já que os dois lados do corte vêm da mesma lista, e testá-los
# produz um placebo que passa de graça.
COVARIAVEIS_PLACEBO = ["ln_receita_t", "ln_despesa_t", "share_fefc_t",
                       "n_doadores_t", "idade_posse", "genero_fem"]


def _salvar(df: pd.DataFrame, nome: str, verbose: bool = True) -> None:
    DIR_TAB.mkdir(parents=True, exist_ok=True)
    df.to_csv(DIR_TAB / nome, index=False)
    if verbose:
        print(f"    -> outputs/tabelas/{nome}")


def rodar(con, janela: float | None = None, tau_ref: float | None = None,
          niveis_match: tuple[int, ...] = (1, 2)) -> dict:
    aplicar_views(con)
    relatorio: dict = {}

    # -- 0. validação -------------------------------------------------
    checagens, ok = validar(con)
    relatorio["validacao"] = checagens
    if not ok:
        raise RuntimeError(
            "checagem estrutural falhou — a análise causal não deve ser rodada. "
            "Ver o relatório de validação acima.")

    # -- 1. descritiva ------------------------------------------------
    print("\n=== 1. camada descritiva ===")
    resumo = desc.resumo_por_ano(con)
    print(resumo.to_string(index=False))
    comp = desc.composicao_receita(con)
    bruta = desc.taxa_sucesso_por_gasto(con)
    _salvar(resumo, "descritivo_resumo_por_ano.csv")
    _salvar(comp, "descritivo_composicao_receita.csv")
    _salvar(desc.gasto_por_decil(con), "descritivo_gasto_por_decil.csv")
    _salvar(bruta, "descritivo_gasto_vs_eleicao.csv")
    _salvar(desc.listas_descartadas(con), "descritivo_listas_descartadas.csv")
    plots.grafico_composicao_receita(comp)
    plots.grafico_gasto_vs_sucesso(bruta)
    relatorio["resumo_por_ano"] = resumo.to_dict("records")

    # -- 2. amostra ---------------------------------------------------
    print("\n=== 2. amostra do RDD ===")
    pareamento = desc.qualidade_pareamento(con)
    print(pareamento.to_string(index=False))
    _salvar(pareamento, "rdd_qualidade_pareamento.csv")

    contagens = desc.contagem_por_janela(con)
    print(contagens.to_string(index=False))
    _salvar(contagens, "rdd_contagem_por_janela.csv")
    relatorio["contagem_por_janela"] = contagens.to_dict("records")

    painel = desc.painel_rdd(con)
    principal_df = painel[painel["nivel_match"].isin(niveis_match)
                          | painel["nivel_match"].isna()]
    print(f"  painel: {len(painel):,} candidaturas | "
          f"{int(painel['concorreu_t1'].sum()):,} com desfecho observado | "
          f"níveis de match usados: {niveis_match}")
    relatorio["n_painel"] = len(principal_df)

    # -- 3. estimativas -----------------------------------------------
    print("\n=== 3. estimativas de RDD ===")
    linhas = []
    for y, (rotulo, tipo) in DESFECHOS.items():
        if y not in principal_df.columns:
            continue
        try:
            r = rdd.estimar_rdd(principal_df, y, janela=janela)
        except Exception as e:
            print(f"  [pulado] {y}: {e}")
            continue
        print(" ", r)
        d = r.como_dict()
        d["rotulo"], d["tipo_margem"] = rotulo, tipo
        linhas.append(d)
    tab_rdd = pd.DataFrame(linhas)
    _salvar(tab_rdd, "rdd_estimativas.csv")
    relatorio["estimativas"] = linhas

    principal = tab_rdd[tab_rdd["desfecho"] == DESFECHO_PRINCIPAL]
    h_otimo = float(principal["janela"].iloc[0]) if len(principal) else janela

    # -- 4. robustez --------------------------------------------------
    print("\n=== 4. robustez ===")

    print("\n  4.1 dois estimadores na mesma banda")
    comparacao = rdd.comparar_estimadores(principal_df, DESFECHO_PRINCIPAL)
    print(comparacao[["metodo", "tau", "erro_padrao", "p_valor", "n"]]
          .to_string(index=False))
    _salvar(comparacao, "rdd_comparacao_estimadores.csv")
    relatorio["comparacao_estimadores"] = comparacao.to_dict("records")

    print("\n  4.2 varredura de janelas")
    varredura = rdd.varredura_janelas(principal_df, DESFECHO_PRINCIPAL)
    print(varredura[["janela", "tau", "erro_padrao", "p_valor", "n"]]
          .to_string(index=False))
    _salvar(varredura, "rdd_varredura_janelas.csv")
    relatorio["varredura_janelas"] = varredura.to_dict("records")

    print("\n  4.3 continuidade de covariáveis pré-tratamento (esperado: sem salto)")
    placebo_cov = rdd.teste_continuidade_covariaveis(
        principal_df, COVARIAVEIS_PLACEBO, janela=janela)
    if not placebo_cov.empty:
        print(placebo_cov[["desfecho", "tau", "p_valor", "passou_a_5pct"]]
              .to_string(index=False))
    _salvar(placebo_cov, "rdd_placebo_covariaveis.csv")
    relatorio["placebo_covariaveis"] = placebo_cov.to_dict("records")

    print("\n  4.4 cortes placebo (esperado: sem salto onde não há regra)")
    placebo_cortes = rdd.teste_cortes_placebo(principal_df, DESFECHO_PRINCIPAL,
                                              janela=janela)
    if not placebo_cortes.empty:
        print(placebo_cortes[["corte_placebo", "tau", "p_valor", "n"]]
              .to_string(index=False))
    _salvar(placebo_cortes, "rdd_placebo_cortes.csv")
    relatorio["placebo_cortes"] = placebo_cortes.to_dict("records")

    print("\n  4.5 donut (exclui observações coladas no corte)")
    donut = rdd.teste_donut(principal_df, DESFECHO_PRINCIPAL, janela=janela)
    if not donut.empty:
        print(donut[["buraco", "tau", "erro_padrao", "p_valor", "n"]]
              .to_string(index=False))
    _salvar(donut, "rdd_donut.csv")
    relatorio["donut"] = donut.to_dict("records")

    print("\n  4.6 densidade no corte (manipulação)")
    dens = rdd.teste_densidade(painel)
    print(f"    {dens}")
    _salvar(pd.DataFrame([dens]), "rdd_teste_densidade.csv")
    relatorio["densidade"] = dens

    print("\n  4.7 normalização alternativa (margem sobre votos da disputa)")
    try:
        alt = rdd.estimar_rdd(principal_df, DESFECHO_PRINCIPAL,
                              running="margem_rel_disputa")
        print(" ", alt)
        relatorio["normalizacao_alternativa"] = alt.como_dict()
    except Exception as e:
        print(f"    [pulado] {e}")

    print("\n  4.8 amostra restrita à fronteira da lista")
    # mesma regra da view vw_amostra_fronteira: só listas com o par completo
    g = principal_df.groupby("id_lista_disputa")
    completo = (g["eh_ultimo_eleito"].transform("max").astype(bool)
                & g["eh_primeiro_suplente"].transform("max").astype(bool))
    fronteira = principal_df[completo & (principal_df["eh_ultimo_eleito"]
                                         | principal_df["eh_primeiro_suplente"])]
    try:
        r_front = rdd.estimar_rdd(fronteira, DESFECHO_PRINCIPAL, janela=janela)
        print(" ", r_front)
        relatorio["amostra_fronteira"] = r_front.como_dict()
    except Exception as e:
        print(f"    [pulado] {e}")

    print("\n  4.9 heterogeneidade por ciclo eleitoral")
    # conta só ciclos com desfecho observável -- o ano mais recente
    # carregado nunca tem par de saída (ver docstring da função) e não
    # deve contar como um "ciclo" de comparação
    n_ciclos = principal_df.dropna(subset=[DESFECHO_PRINCIPAL])["ano_eleicao"].nunique()
    if n_ciclos < 2:
        print(f"    [pulado] só {n_ciclos} ciclo eleitoral no painel -- "
              f"nada a comparar. Roda de novo depois de empilhar mais de "
              f"um par de eleições (ver docs/plano_execucao.md).")
        heterog = pd.DataFrame()
    else:
        heterog = rdd.teste_heterogeneidade_por_ciclo(principal_df, DESFECHO_PRINCIPAL,
                                                      janela=janela)
        if not heterog.empty:
            print(heterog[["ciclo", "tau", "erro_padrao", "p_valor", "n"]]
                  .to_string(index=False))
    _salvar(heterog, "rdd_heterogeneidade_ciclo.csv")
    relatorio["heterogeneidade_ciclo"] = heterog.to_dict("records")

    # -- 5. figuras ---------------------------------------------------
    print("\n=== 5. figuras ===")
    # janela do gráfico um pouco maior que a banda ótima, para que a
    # faixa sombreada apareça como faixa e não tome a figura inteira
    janela_fig = float(h_otimo) * 1.6 if h_otimo else 0.08
    bins = rdd.binscatter(principal_df, DESFECHO_PRINCIPAL, janela=janela_fig)
    caminhos = [
        plots.grafico_descontinuidade(
            bins, principal_df, DESFECHO_PRINCIPAL, h_otimo=h_otimo,
            janela=janela_fig,
            titulo="Efeito de vencer por um fio sobre o dinheiro na eleição seguinte",
            rotulo_y=DESFECHOS[DESFECHO_PRINCIPAL][0]),
        plots.grafico_varredura(varredura, tau_ref=tau_ref),
        plots.grafico_densidade(painel),
    ]
    for c in caminhos:
        print(f"    -> {c.relative_to(RAIZ)}")

    # -- 6. regra de decisão pré-registrada ---------------------------
    print("\n=== 6. leitura do resultado (regras fixadas antes da execução) ===")
    veredito = regras.avaliar(relatorio, DESFECHO_PRINCIPAL)
    print(veredito)
    relatorio["veredito"] = veredito.como_dict()

    DIR_OUT.mkdir(parents=True, exist_ok=True)
    (DIR_OUT / "relatorio_rdd.json").write_text(
        json.dumps(relatorio, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    print("\nrelatório consolidado: outputs/relatorio_rdd.json")

    relatorio["_painel"] = principal_df
    return relatorio


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--banco", default=str(RAIZ / "data" / "db" / "financiamento.duckdb"))
    p.add_argument("--sintetico", action="store_true",
                   help="gera e usa o banco sintético de teste")
    p.add_argument("--janela", type=float, default=None,
                   help="janela fixa; se omitido, usa a banda MSE-ótima")
    p.add_argument("--municipios", type=int, default=90,
                   help="tamanho do dado sintético")
    args = p.parse_args(argv)

    tau_ref = None
    if args.sintetico:
        from python.synthetic.gerar_dados_sinteticos import (TAU_PADRAO,
                                                             construir_banco)
        print("[modo sintético] dados simulados — NÃO são dados reais do TSE")
        con, _ = construir_banco(RAIZ / "data" / "db" / "sintetico.duckdb",
                                 n_municipios=args.municipios, quieto=False)
        tau_ref = TAU_PADRAO
    else:
        # Conecta ao banco já carregado, SEM recriar o schema. criar_banco()
        # roda schema.sql, que começa com DROP TABLE em tudo — usá-la aqui
        # apagaria os dados reais que já foram carregados via
        # load_to_duckdb.py antes de rodar a análise.
        import duckdb as _duckdb
        con = _duckdb.connect(str(args.banco))
        aplicar_views(con)

    try:
        rodar(con, janela=args.janela, tau_ref=tau_ref)
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
