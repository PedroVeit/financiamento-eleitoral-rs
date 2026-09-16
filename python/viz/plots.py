from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np               # noqa: E402
import pandas as pd              # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]
DIR_FIG = RAIZ / "outputs" / "figures"

CINZA, AZUL, LARANJA = "#4a4a4a", "#2b6ca3", "#c1611f"

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 200, "font.size": 10,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "figure.facecolor": "white",
})


def _salvar(fig, nome: str) -> Path:
    DIR_FIG.mkdir(parents=True, exist_ok=True)
    caminho = DIR_FIG / nome
    fig.savefig(caminho, bbox_inches="tight")
    plt.close(fig)
    return caminho


def grafico_descontinuidade(bins: pd.DataFrame, dados: pd.DataFrame,
                            desfecho: str, running: str = "margem_rel_lista",
                            janela: float = 0.08, h_otimo: float | None = None,
                            titulo: str = "", rotulo_y: str = "",
                            nome: str = "rdd_descontinuidade.png") -> Path:
    """O gráfico central: médias por bin + ajuste linear local de cada lado."""
    fig, ax = plt.subplots(figsize=(7.4, 4.7))

    for lado, cor, rot in (("nao_eleito", CINZA, "Não eleito"),
                           ("eleito", AZUL, "Eleito")):
        b = bins[bins["lado"] == lado]
        if b.empty:
            continue
        ax.errorbar(b["x"], b["y"], yerr=b["ep"], fmt="o", ms=5, color=cor,
                    ecolor="#c4c4c4", elinewidth=1, capsize=2, zorder=3, label=rot)

    d = dados[[desfecho, running]].dropna()
    d = d[np.abs(d[running]) <= janela]
    for sinal, cor in ((-1, CINZA), (1, AZUL)):
        sub = d[d[running] < 0] if sinal < 0 else d[d[running] >= 0]
        if len(sub) < 10:
            continue
        h = h_otimo or janela
        peso = np.clip(1 - np.abs(sub[running]) / h, 0, None)
        if (peso > 0).sum() < 10:
            peso = np.ones(len(sub))
        coef = np.polyfit(sub[running], sub[desfecho], 1, w=np.sqrt(peso))
        grade = (np.linspace(max(sub[running].min(), -janela), 0, 60) if sinal < 0
                 else np.linspace(0, min(sub[running].max(), janela), 60))
        ax.plot(grade, np.polyval(coef, grade), color=cor, lw=2.2, zorder=4)

    ax.axvline(0, color="black", lw=1.1, ls="--", alpha=0.8)
    if h_otimo:
        ax.axvspan(-h_otimo, h_otimo, color="gold", alpha=0.07, zorder=0)
        ax.text(0.015, 0.03, f"faixa sombreada = banda ótima (h = {h_otimo:.4f})",
                transform=ax.transAxes, fontsize=8, color="#666")
    ax.set_xlabel("margem de votos até o corte da lista\n"
                  "(negativo = ficou de fora · positivo = elegeu-se)")
    ax.set_ylabel(rotulo_y or desfecho)
    ax.set_title(titulo or "Descontinuidade no corte de eleição",
                 loc="left", fontweight="bold")
    ax.legend(frameon=False, loc="upper left")
    return _salvar(fig, nome)


def grafico_varredura(varredura: pd.DataFrame, tau_ref: float | None = None,
                      nome: str = "rdd_varredura_janelas.png") -> Path:
    """Efeito estimado em função da janela. Estabilidade aqui é o que
    separa um resultado de um artefato de escolha de janela."""
    v = varredura.dropna(subset=["tau"])
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.errorbar(v["janela"], v["tau"],
                yerr=[v["tau"] - v["ic95_lo"], v["ic95_hi"] - v["tau"]],
                fmt="o-", color=AZUL, ecolor="#9dbdd6", capsize=3, lw=1.6, ms=5)
    ax.axhline(0, color="black", lw=1, ls="--", alpha=0.7)
    if tau_ref is not None:
        ax.axhline(tau_ref, color=LARANJA, lw=1.4, ls=":",
                   label=f"valor verdadeiro (simulação) = {tau_ref}")
        ax.legend(frameon=False, fontsize=8)
    ax.set_xlabel("janela (h), em fração dos votos nominais da lista")
    ax.set_ylabel("efeito estimado (τ)")
    ax.set_title("Sensibilidade do efeito à escolha da janela",
                 loc="left", fontweight="bold")
    for _, r in v.iterrows():
        ax.annotate(f"n={int(r['n'])}", (r["janela"], r["ic95_hi"]),
                    textcoords="offset points", xytext=(0, 6),
                    ha="center", fontsize=7, color=CINZA)
    return _salvar(fig, nome)


def grafico_densidade(dados: pd.DataFrame, running: str = "margem_rel_lista",
                      janela: float = 0.08, largura_bin: float = 0.005,
                      nome: str = "rdd_densidade.png") -> Path:
    """Histograma da variável de corte: procura acúmulo suspeito em 0."""
    x = dados[running].dropna()
    x = x[np.abs(x) <= janela]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ax.hist(x, bins=np.arange(-janela, janela + largura_bin, largura_bin),
            color="#c9c9c9", edgecolor="white")
    ax.axvline(0, color="black", lw=1, ls="--")
    ax.set_xlabel("margem de votos até o corte da lista")
    ax.set_ylabel("nº de candidaturas")
    ax.set_title("Densidade da variável de corte (teste de manipulação)",
                 loc="left", fontweight="bold")
    return _salvar(fig, nome)


def grafico_composicao_receita(comp: pd.DataFrame,
                               nome: str = "composicao_receita.png") -> Path:
    rotulos = {"share_fefc": "Fundo Eleitoral (FEFC)",
               "share_fundo_partidario": "Fundo Partidário",
               "share_doacao_pf": "Doação de pessoa física",
               "share_doacao_partido": "Repasse de partido/candidato",
               "share_propria": "Recursos próprios",
               "share_outros": "Outros"}
    fontes = [c for c in comp.columns if c.startswith("share_")]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    base = np.zeros(len(comp))
    cores = ["#2b6ca3", "#6fa3c9", "#c1611f", "#e0a06a", "#8c8c8c", "#d4d4d4"]
    for i, f in enumerate(fontes):
        v = comp[f].fillna(0).to_numpy(float)
        ax.bar(comp["ano_eleicao"].astype(str), v, bottom=base,
               label=rotulos.get(f, f), color=cores[i % len(cores)],
               edgecolor="white", linewidth=0.6)
        base += v
    ax.set_ylabel("participação na receita total")
    ax.set_xlabel("eleição")
    ax.set_ylim(0, 1)
    ax.set_title("De onde vem o dinheiro de campanha", loc="left", fontweight="bold")
    ax.legend(fontsize=8, frameon=False, ncol=2)
    return _salvar(fig, nome)


def grafico_gasto_vs_sucesso(tab: pd.DataFrame,
                             nome: str = "descritivo_gasto_vs_eleicao.png") -> Path:
    """Correlação bruta gasto × eleição — rotulada como NÃO causal."""
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.plot(tab["decil"], tab["pct_eleitos"], "o-", color=CINZA, lw=1.8)
    ax.set_xlabel("decil de gasto de campanha (1 = menor gasto)")
    ax.set_ylabel("% de candidaturas eleitas")
    ax.set_xticks(tab["decil"])
    ax.set_title("Associação bruta entre gasto e eleição", loc="left",
                 fontweight="bold")
    ax.text(0.0, -0.30,
            "Associação descritiva, não efeito causal: candidatos com mais chance de "
            "vencer\ntambém atraem mais doação. A estimativa causal está na figura de RDD.",
            transform=ax.transAxes, fontsize=8, color=CINZA, va="top")
    return _salvar(fig, nome)
