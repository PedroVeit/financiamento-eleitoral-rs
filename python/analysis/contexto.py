"""Contexto estrutural: vantagem bruta x efeito causal, e peso do dinheiro público.

Roda DEPOIS de run_pipeline (lê o τ do RDD em outputs/relatorio_rdd.json):

    python -m python.analysis.contexto --banco data/db/financiamento.duckdb

Nenhuma métrica aqui é recortada por partido, coligação ou candidato.
O objeto é o mecanismo de financiamento, não os atores.

A peça central é a comparação entre dois números:

    vantagem bruta  = média de ln(receita t+1) dos que venceram em t
                      − média dos que perderam em t (entre recandidatos)
    efeito causal   = τ do RDD (só candidatos colados no corte)

A diferença entre os dois é, aproximadamente, a parte da "vantagem de
quem está no cargo" que vem de SELEÇÃO — quem vence já era mais
competitivo antes de vencer — e não do mandato em si. As duas
comparações condicionam a recandidatura, então a ressalva de seleção da
nota metodológica (seção 3) vale para ambas igualmente.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

DIR_OUT = RAIZ / "outputs"
DIR_TAB = DIR_OUT / "tabelas"
DIR_FIG = DIR_OUT / "figures"
SQL_CTX = RAIZ / "sql" / "04_contexto_sistema.sql"
DESFECHO = "ln_receita_t1_cond"


def aplicar(con) -> None:
    con.execute(SQL_CTX.read_text(encoding="utf-8"))


def financiamento_publico(con) -> pd.DataFrame:
    return con.execute("SELECT * FROM vw_ctx_financiamento_publico").df()


def checar_fefc(fp: pd.DataFrame) -> list[str]:
    """Sanidade: o FEFC existe desde as eleições de 2018, então um share
    ~0 em ano municipal posterior é erro de classificação, não achado
    (D18). Devolve a lista de avisos (vazia se tudo certo)."""
    ruins = fp.loc[(fp["ano_eleicao"] >= 2020)
                   & (fp["share_fefc"].fillna(0) < 0.01), "ano_eleicao"]
    return [f"share_fefc ~ 0 em {int(a)}: classificação de fonte suspeita "
            f"(ver docs/decisoes.md, D18) -- NÃO publicar o gráfico"
            for a in ruins]


def vantagem_bruta(con) -> pd.DataFrame:
    """Diferença de médias de ln(receita t+1), eleitos − não eleitos,
    empilhando todos os anos de origem com painel. Erro-padrão de Welch."""
    df = con.execute(f"""
        SELECT eleito, {DESFECHO} AS y
        FROM vw_painel_rdd
        WHERE {DESFECHO} IS NOT NULL
          AND ano_eleicao IN (SELECT DISTINCT ano_t FROM painel_link)
    """).df()
    if df.empty or df["eleito"].nunique() < 2:
        raise ValueError("painel sem eleitos e não eleitos com receita em t+1")
    a = df.loc[df["eleito"].astype(bool), "y"].to_numpy(float)
    b = df.loc[~df["eleito"].astype(bool), "y"].to_numpy(float)
    dif = a.mean() - b.mean()
    ep = float(np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)))
    return pd.DataFrame([{
        "comparacao": "bruta (todos os candidatos)",
        "tau": dif, "erro_padrao": ep,
        "ic95_lo": dif - 1.96 * ep, "ic95_hi": dif + 1.96 * ep,
        "n": len(a) + len(b), "n_eleitos": len(a), "n_nao_eleitos": len(b),
    }])


def tau_rdd(caminho: Path = DIR_OUT / "relatorio_rdd.json") -> dict | None:
    """τ principal do RDD, lido do relatório da última execução."""
    if not caminho.exists():
        return None
    rel = json.loads(caminho.read_text(encoding="utf-8"))
    for e in rel.get("estimativas", []):
        if e.get("desfecho") == DESFECHO:
            return {"comparacao": "causal (RDD, colados no corte)",
                    "tau": e["tau"], "erro_padrao": e["erro_padrao"],
                    "ic95_lo": e["ic95_lo"], "ic95_hi": e["ic95_hi"],
                    "n": e["n"]}
    return None


def pct(ln_dif: float) -> float:
    """Diferença em log -> diferença percentual."""
    return float(np.expm1(ln_dif) * 100)


# ---------------------------------------------------------------------
# Figuras
# ---------------------------------------------------------------------
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.dpi": 130, "savefig.dpi": 200, "font.size": 10,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.alpha": 0.25, "figure.facecolor": "white",
    })
    return plt


def figura_bruto_vs_causal(tab: pd.DataFrame,
                           nome: str = "ctx_bruto_vs_causal.png") -> Path:
    plt = _plt()
    cores = ["#8c8c8c", "#2b6ca3"]
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    y = np.arange(len(tab))[::-1]
    for yi, (_, r), cor in zip(y, tab.iterrows(), cores):
        ax.plot([pct(r["ic95_lo"]), pct(r["ic95_hi"])], [yi, yi],
                color=cor, lw=3, solid_capstyle="round")
        ax.plot(pct(r["tau"]), yi, "o", color=cor, ms=11, zorder=3)
        ax.text(pct(r["ic95_hi"]) + 2, yi, f"{pct(r['tau']):+.0f}%",
                va="center", fontsize=11, color=cor, fontweight="bold")
    ax.axvline(0, color="black", lw=1, ls="--", alpha=0.7)
    ax.set_yticks(y)
    ax.set_yticklabels([
        "Comparação simples\nvencedores × perdedores",
        "Efeito causal (RDD)\nsó quem venceu/perdeu por um fio",
    ], fontsize=10)
    ax.set_xlabel("receita na eleição seguinte: diferença de quem venceu (%), com IC 95%")
    ax.set_ylim(-0.7, len(tab) - 0.3)
    ax.set_title("Quanto da vantagem de quem venceu é efeito do mandato?",
                 loc="left", fontweight="bold", fontsize=12)
    DIR_FIG.mkdir(parents=True, exist_ok=True)
    caminho = DIR_FIG / nome
    fig.savefig(caminho, bbox_inches="tight")
    plt.close(fig)
    return caminho


def figura_dinheiro_publico(fp: pd.DataFrame,
                            nome: str = "ctx_dinheiro_publico.png") -> Path:
    plt = _plt()
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    anos = fp["ano_eleicao"].astype(str)
    fefc = fp["share_fefc"].fillna(0).to_numpy() * 100
    fpart = fp["share_fundo_partidario"].fillna(0).to_numpy() * 100
    ax.bar(anos, fefc, color="#2b6ca3", label="Fundo Eleitoral (FEFC)", width=0.55)
    ax.bar(anos, fpart, bottom=fefc, color="#9dbdd6",
           label="Fundo Partidário", width=0.55)
    for i, tot in enumerate(fefc + fpart):
        ax.text(i, tot + 1.5, f"{tot:.0f}%", ha="center", fontweight="bold")
    ax.set_ylim(0, max(100, (fefc + fpart).max() + 12))
    ax.set_ylabel("% da receita total declarada")
    ax.set_title("Participação de recursos públicos na campanha de vereadores (RS)",
                 loc="left", fontweight="bold", fontsize=12)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    DIR_FIG.mkdir(parents=True, exist_ok=True)
    caminho = DIR_FIG / nome
    fig.savefig(caminho, bbox_inches="tight")
    plt.close(fig)
    return caminho


# ---------------------------------------------------------------------
def rodar(con, relatorio: Path = DIR_OUT / "relatorio_rdd.json",
          verbose: bool = True) -> dict:
    aplicar(con)
    DIR_TAB.mkdir(parents=True, exist_ok=True)

    fp = financiamento_publico(con)
    fp.to_csv(DIR_TAB / "ctx_financiamento_publico.csv", index=False)

    vb_ano = con.execute("SELECT * FROM vw_ctx_vantagem_bruta").df()
    vb_ano.to_csv(DIR_TAB / "ctx_vantagem_bruta_por_ano.csv", index=False)

    bruta = vantagem_bruta(con)
    causal = tau_rdd(relatorio)
    comp = pd.concat([bruta, pd.DataFrame([causal])] if causal else [bruta],
                     ignore_index=True)
    comp["diferenca_pct"] = comp["tau"].map(pct)
    comp.to_csv(DIR_TAB / "ctx_bruto_vs_causal.csv", index=False)

    avisos = checar_fefc(fp)
    figs = [figura_dinheiro_publico(fp)]
    if causal:
        figs.append(figura_bruto_vs_causal(comp))

    if verbose:
        print("\n=== contexto: peso do dinheiro público ===")
        print(fp[["ano_eleicao", "share_fefc", "share_fundo_partidario",
                  "share_publico", "share_doacao_pf", "share_propria"]]
              .round(3).to_string(index=False))
        print("\n=== contexto: recandidatura e receita seguinte, por status ===")
        print(vb_ano.round(3).to_string(index=False))
        print("\n=== contexto: vantagem bruta x efeito causal ===")
        print(comp[["comparacao", "tau", "ic95_lo", "ic95_hi",
                    "diferenca_pct", "n"]].round(3).to_string(index=False))
        if causal:
            fracao = 1 - causal["tau"] / bruta["tau"].iloc[0]
            print(f"\n  parcela da vantagem bruta NÃO explicada pelo mandato: "
                  f"~{fracao:.0%}")
        else:
            print("\n  [aviso] relatorio_rdd.json não encontrado — rode "
                  "run_pipeline antes para ter o τ causal")
        for a in avisos:
            print(f"\n  [ALERTA] {a}")
        for f in figs:
            print(f"    -> {f.relative_to(RAIZ)}")

    return {"financiamento_publico": fp, "comparacao": comp,
            "vantagem_por_ano": vb_ano}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--banco", default=str(RAIZ / "data" / "db" / "financiamento.duckdb"))
    args = p.parse_args(argv)
    con = duckdb.connect(args.banco)
    try:
        rodar(con)
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
