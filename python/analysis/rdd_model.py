"""Estimação por regressão descontínua (sharp RDD) e testes de robustez.

Dois estimadores, de propósito
------------------------------
1. **`rdrobust`** (Calonico, Cattaneo, Farrell e Titiunik) — a
   implementação de referência da literatura, disponível em Python.
   Largura de banda MSE-ótima e inferência *robust bias-corrected*: o
   erro-padrão convencional subestima a incerteza quando a banda é
   escolhida pelo próprio dado. É o número que vai ao relatório.

2. **`local_linear`** — regressão linear local escrita à mão, kernel
   triangular, erros agrupados por lista. Não substitui o rdrobust:
   existe para que um teste automatizado confira que os dois concordam.
   Estimador que ninguém consegue reproduzir na mão é estimador em que
   ninguém deveria confiar.

Modelo do estimador próprio, dentro da janela |x| <= h:

    y_i = a + tau*T_i + b1*x_i + b2*(T_i * x_i) + e_i,   T = 1[x >= 0]

onde x é a margem (corte em 0). `tau` é o salto no corte.

Agrupamento: as duas observações de fronteira da mesma lista não são
independentes — o corte de uma é definido pela votação da outra. Por
isso o padrão é agrupar por `id_lista_disputa`.
"""

from __future__ import annotations

import warnings
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import norm

RUNNING_PADRAO = "margem_rel_lista"
CLUSTER_PADRAO = "id_lista_disputa"


# ---------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------
@dataclass
class ResultadoRDD:
    desfecho: str
    tau: float
    erro_padrao: float
    p_valor: float
    ic95: tuple[float, float]
    janela: float
    n: int
    n_tratados: int
    n_controles: int
    metodo: str
    cluster: str | None = None
    extras: dict = field(default_factory=dict)

    def __str__(self) -> str:
        lo, hi = self.ic95
        return (f"{self.desfecho:>22} | tau = {self.tau:+.4f} "
                f"(ep {self.erro_padrao:.4f}) | IC95 [{lo:+.4f}, {hi:+.4f}] "
                f"| p = {self.p_valor:.4f} | h = {self.janela:.4f} "
                f"| n = {self.n} ({self.n_tratados}/{self.n_controles})")

    def como_dict(self) -> dict:
        d = asdict(self)
        d["ic95_lo"], d["ic95_hi"] = d.pop("ic95")
        d.update(d.pop("extras"))
        return d


# ---------------------------------------------------------------------
# Estimador próprio
# ---------------------------------------------------------------------
def kernel_triangular(x: np.ndarray, h: float) -> np.ndarray:
    """Peso 1 no corte, caindo linearmente até 0 na borda da janela."""
    return np.clip(1.0 - np.abs(x) / h, 0.0, None)


def janela_regra_de_bolso(x: np.ndarray, corte: float = 0.0) -> float:
    """Janela por regra de bolso, usada só quando o rdrobust não roda.

    A conclusão do projeto nunca pode depender de uma janela específica —
    por isso `varredura_janelas` é obrigatória no relatório.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 20:
        return float(np.percentile(np.abs(x - corte), 50)) or 1e-6
    sigma = float(np.std(x, ddof=1))
    iqr = float(np.subtract(*np.percentile(x, [75, 25])))
    escala = min(sigma, iqr / 1.349) if iqr > 0 else sigma
    h = 1.84 * escala * n ** (-1 / 5)
    for _ in range(40):                       # garante massa dos dois lados
        n_esq = int(np.sum((x < corte) & (x >= corte - h)))
        n_dir = int(np.sum((x >= corte) & (x <= corte + h)))
        if min(n_esq, n_dir) >= 20:
            break
        h *= 1.25
    return float(h)


def local_linear(y: np.ndarray, x: np.ndarray, h: float,
                 cluster: np.ndarray | None = None,
                 desfecho: str = "") -> ResultadoRDD:
    """Regressão local-linear ponderada por kernel triangular."""
    dentro = np.abs(x) <= h
    y, x = y[dentro], x[dentro]
    cl = cluster[dentro] if cluster is not None else None
    if len(x) < 10:
        raise ValueError(f"amostra pequena demais na janela h={h:.4f}: n={len(x)}")

    T = (x >= 0).astype(float)
    X = np.column_stack([np.ones_like(x), T, x, T * x])
    w = kernel_triangular(x, h)

    modelo = sm.WLS(y, X, weights=w)
    if cl is not None:
        ajuste = modelo.fit(cov_type="cluster", cov_kwds={"groups": cl})
    else:
        ajuste = modelo.fit(cov_type="HC1")

    ic = ajuste.conf_int()[1]
    return ResultadoRDD(
        desfecho=desfecho,
        tau=float(ajuste.params[1]),
        erro_padrao=float(ajuste.bse[1]),
        p_valor=float(ajuste.pvalues[1]),
        ic95=(float(ic[0]), float(ic[1])),
        janela=float(h),
        n=int(len(x)),
        n_tratados=int(T.sum()),
        n_controles=int(len(T) - T.sum()),
        metodo="local-linear (kernel triangular)",
        cluster="sim" if cl is not None else None,
    )


# ---------------------------------------------------------------------
# Estimador principal
# ---------------------------------------------------------------------
def _preparar(df: pd.DataFrame, desfecho: str, running: str,
              cluster: str | None, covs: list[str] | None) -> pd.DataFrame:
    colunas = [desfecho, running]
    if cluster:
        colunas.append(cluster)
    colunas += covs or []
    return df[list(dict.fromkeys(colunas))].dropna()


def estimar_rdd(df: pd.DataFrame, desfecho: str,
                running: str = RUNNING_PADRAO,
                janela: float | None = None,
                corte: float = 0.0,
                cluster: str | None = CLUSTER_PADRAO,
                covs: list[str] | None = None,
                metodo: str = "rdrobust") -> ResultadoRDD:
    """Estima o salto no corte.

    metodo='rdrobust' usa banda MSE-ótima e inferência robusta com
    correção de viés. metodo='local' usa o estimador próprio. Se
    `janela` for informada com metodo='rdrobust', ela é imposta ao
    rdrobust (usado na varredura de robustez).
    """
    d = _preparar(df, desfecho, running, cluster, covs)
    if len(d) < 20:
        raise ValueError(f"amostra insuficiente para {desfecho}: n={len(d)}")
    y = d[desfecho].to_numpy(float)
    x = d[running].to_numpy(float)
    cl = d[cluster].to_numpy() if cluster else None

    if metodo == "local":
        h = janela if janela is not None else janela_regra_de_bolso(x - corte)
        r = local_linear(y, x - corte, h, cluster=cl, desfecho=desfecho)
        return r

    kw: dict = {"c": corte}
    if cl is not None:
        kw["cluster"] = cl
    if covs:
        kw["covs"] = d[covs].to_numpy(float)
    if janela is not None:
        kw["h"] = janela

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        r = rdrobust_seguro(y=y, x=x, **kw)

    return ResultadoRDD(
        desfecho=desfecho,
        tau=float(r.coef.loc["Conventional", "Coeff"]),
        erro_padrao=float(r.se.loc["Robust", "Std. Err."]),
        p_valor=float(r.pv.loc["Robust", "P>|z|"]),
        ic95=(float(r.ci.loc["Robust", "CI Lower"]),
              float(r.ci.loc["Robust", "CI Upper"])),
        janela=float(r.bws.loc["h", "left"]),
        n=int(r.N_h[0] + r.N_h[1]),
        n_tratados=int(r.N_h[1]),
        n_controles=int(r.N_h[0]),
        metodo="rdrobust (MSE-ótimo, robust bias-corrected)",
        cluster=cluster,
        extras={"tau_bias_corrected": float(r.coef.loc["Bias-Corrected", "Coeff"])},
    )


def rdrobust_seguro(**kw):
    from rdrobust import rdrobust
    return rdrobust(**kw)


def comparar_estimadores(df: pd.DataFrame, desfecho: str,
                         running: str = RUNNING_PADRAO,
                         cluster: str | None = CLUSTER_PADRAO) -> pd.DataFrame:
    """Roda os dois estimadores na mesma banda. Divergência grande é
    motivo para revisar, nunca para escolher o resultado mais bonito."""
    r1 = estimar_rdd(df, desfecho, running, cluster=cluster, metodo="rdrobust")
    r2 = estimar_rdd(df, desfecho, running, cluster=cluster,
                     janela=r1.janela, metodo="local")
    return pd.DataFrame([r1.como_dict(), r2.como_dict()])


# ---------------------------------------------------------------------
# Bateria de robustez
# ---------------------------------------------------------------------
def varredura_janelas(df: pd.DataFrame, desfecho: str,
                      running: str = RUNNING_PADRAO,
                      janelas=(0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12),
                      **kw) -> pd.DataFrame:
    """O efeito é estável quando a janela muda? Se não for, a conclusão
    está sendo escolhida pela janela, não pelos dados."""
    linhas = []
    for h in janelas:
        try:
            linhas.append(estimar_rdd(df, desfecho, running, janela=h,
                                      metodo="local", **kw).como_dict())
        except (ValueError, np.linalg.LinAlgError) as e:
            linhas.append({"desfecho": desfecho, "janela": h, "tau": np.nan,
                           "erro": str(e)[:80]})
    return pd.DataFrame(linhas)


def teste_continuidade_covariaveis(df: pd.DataFrame, covariaveis: list[str],
                                   running: str = RUNNING_PADRAO,
                                   **kw) -> pd.DataFrame:
    """Placebo: variáveis determinadas ANTES do resultado eleitoral não
    podem saltar no corte. Se saltarem, os dois lados não são
    comparáveis e o desenho não identifica nada."""
    linhas = []
    for cov in covariaveis:
        if cov not in df.columns or df[cov].notna().sum() < 50:
            continue
        try:
            r = estimar_rdd(df, cov, running, **kw)
            d = r.como_dict()
            d["passou_a_5pct"] = bool(r.p_valor > 0.05)
            linhas.append(d)
        except (ValueError, np.linalg.LinAlgError) as e:
            linhas.append({"desfecho": cov, "tau": np.nan, "erro": str(e)[:80]})
    return pd.DataFrame(linhas)


def teste_cortes_placebo(df: pd.DataFrame, desfecho: str,
                         running: str = RUNNING_PADRAO,
                         cortes=(-0.06, -0.04, -0.02, 0.02, 0.04, 0.06),
                         **kw) -> pd.DataFrame:
    """Salto em pontos onde nenhuma regra muda. Deve dar ~zero.

    Cada placebo usa apenas o lado da amostra correspondente, para não
    contaminar a estimativa com o corte verdadeiro.
    """
    linhas = []
    for c in cortes:
        sub = df[df[running] < 0] if c < 0 else df[df[running] > 0]
        try:
            r = estimar_rdd(sub, desfecho, running, corte=c, **kw)
            d = r.como_dict()
            d["corte_placebo"] = c
            linhas.append(d)
        except (ValueError, np.linalg.LinAlgError) as e:
            linhas.append({"desfecho": desfecho, "corte_placebo": c,
                           "tau": np.nan, "erro": str(e)[:80]})
    return pd.DataFrame(linhas)


def teste_donut(df: pd.DataFrame, desfecho: str, running: str = RUNNING_PADRAO,
                buracos=(0.0, 0.002, 0.005), **kw) -> pd.DataFrame:
    """Remove observações coladas no corte. Se o efeito some ao excluir
    os casos mais próximos, ele vinha de um punhado de observações
    possivelmente sujeitas a recontagem, judicialização ou erro de
    registro."""
    linhas = []
    for b in buracos:
        sub = df[df[running].abs() >= b]
        try:
            d = estimar_rdd(sub, desfecho, running, **kw).como_dict()
            d["buraco"] = b
            linhas.append(d)
        except (ValueError, np.linalg.LinAlgError) as e:
            linhas.append({"desfecho": desfecho, "buraco": b, "tau": np.nan,
                           "erro": str(e)[:80]})
    return pd.DataFrame(linhas)


def teste_heterogeneidade_por_ciclo(df: pd.DataFrame, desfecho: str,
                                    running: str = RUNNING_PADRAO,
                                    coluna_ciclo: str = "ano_eleicao",
                                    **kw) -> pd.DataFrame:
    """Estima o efeito separadamente para cada ciclo eleitoral de origem
    (cada ano_t empilhado no painel) e compara com o pooled.

    Existe para responder uma pergunta específica de quando o projeto
    passa a empilhar mais de um par de eleições (ex.: 2016->2020 e
    2020->2024): o efeito pooled pode estar escondendo que ele só existe
    num dos ciclos, ou que os ciclos apontam em direções opostas. Um
    efeito que aparece em todos os ciclos testados separadamente é muito
    mais convincente que um pooled que soma um ciclo positivo forte com
    um neutro.

    IMPORTANTE: o painel inclui candidaturas de TODOS os anos carregados
    como t0 -- inclusive as do ano mais recente, que nunca têm par de
    saída (ex.: candidatura de 2024 não tem "eleição seguinte" enquanto
    2028 não for carregado). Por isso a função descarta primeiro as
    linhas em que `desfecho` é nulo, e só então agrupa por ciclo -- do
    contrário o "último ano carregado" apareceria como um ciclo
    degenerado, sem nenhuma observação real. Isso pressupõe que o
    desfecho usa NULL para "não observado" (como ln_receita_t1_cond);
    um desfecho que usa 0 para essa mesma situação (como concorreu_t1)
    não se beneficia dessa proteção -- não é como este projeto o utiliza,
    mas vale checar antes de reaproveitar a função noutro contexto.

    Não precisa de pelo menos dois ciclos para rodar (com um só, devolve
    uma linha e nada a comparar) -- mas só ganha poder de diagnóstico
    quando há mais de um.
    """
    linhas = []
    if coluna_ciclo not in df.columns or desfecho not in df.columns:
        return pd.DataFrame(linhas)
    com_desfecho = df.dropna(subset=[desfecho])
    for ciclo, sub in com_desfecho.groupby(coluna_ciclo):
        try:
            d = estimar_rdd(sub, desfecho, running, **kw).como_dict()
            d["ciclo"] = ciclo
            linhas.append(d)
        except (ValueError, np.linalg.LinAlgError) as e:
            linhas.append({"desfecho": desfecho, "ciclo": ciclo, "tau": np.nan,
                           "erro": str(e)[:80]})
    return pd.DataFrame(linhas)


def teste_densidade(df: pd.DataFrame, running: str = RUNNING_PADRAO) -> dict:
    """Manipulação da variável de corte (Cattaneo-Jansson-Ma, sucessor do
    McCrary). H0: densidade contínua no corte. Rejeitar sugere que os
    candidatos conseguem controlar de que lado do corte caem, o que
    invalidaria o desenho.

    Neste desenho específico a manipulação precisa é implausível a
    priori: o corte depende do desempenho dos COLEGAS DE LISTA e do
    quociente eleitoral, não só do próprio voto. Mas implausível não é o
    mesmo que testado, e o teste continua obrigatório.

    Ressalva de leitura: na amostra restrita à fronteira (um par por
    lista) a simetria é imposta por construção e o teste tem pouco
    poder. Rode-o na amostra ampla.
    """
    x = df[running].dropna().to_numpy(float)
    if len(x) < 100:
        return {"erro": f"amostra pequena demais para o teste: n={len(x)}"}
    try:
        from rddensity import rddensity
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = rddensity(X=x)
        n = np.ravel(r.n)
        return {"metodo": "Cattaneo-Jansson-Ma (rddensity)",
                "estatistica_t": float(r.test["t_jk"]),
                "p_valor": float(r.test["p_jk"]),
                "n": int(n[0]), "n_esq": int(n[1]), "n_dir": int(n[2])}
    except Exception as e:                                    # pragma: no cover
        return {"metodo": "falhou", "erro": str(e)[:120],
                **_densidade_binada(x)}


def _densidade_binada(x: np.ndarray, largura_bin: float = 0.005,
                      janela: float = 0.06, n_boot: int = 400,
                      semente: int = 42) -> dict:
    """Alternativa no espírito do McCrary, caso o rddensity não esteja
    disponível: histograma fino, ajuste linear de cada lado, salto no
    corte, incerteza por bootstrap."""
    rng = np.random.default_rng(semente)
    x = x[np.abs(x) <= janela]

    def salto(amostra: np.ndarray) -> float:
        bins = np.arange(-janela, janela + largura_bin, largura_bin)
        cont, bordas = np.histogram(amostra, bins=bins)
        centros = (bordas[:-1] + bordas[1:]) / 2
        esq, dir_ = centros < 0, centros >= 0
        if esq.sum() < 2 or dir_.sum() < 2:
            return np.nan
        return float(np.polyval(np.polyfit(centros[dir_], cont[dir_], 1), 0.0)
                     - np.polyval(np.polyfit(centros[esq], cont[esq], 1), 0.0))

    obs = salto(x)
    boots = np.array([salto(rng.choice(x, size=len(x), replace=True))
                      for _ in range(n_boot)])
    boots = boots[~np.isnan(boots)]
    ep = float(np.std(boots, ddof=1)) if len(boots) > 2 else np.nan
    z = obs / ep if ep and ep > 0 else np.nan
    return {"metodo_alternativo": "binado (McCrary simplificado)",
            "salto_densidade": obs, "erro_padrao": ep, "z": z,
            "p_valor_alternativo": float(2 * (1 - norm.cdf(abs(z))))
            if np.isfinite(z) else np.nan}


def binscatter(df: pd.DataFrame, desfecho: str, running: str = RUNNING_PADRAO,
               janela: float = 0.08, n_bins: int = 20) -> pd.DataFrame:
    """Médias por bin da variável de corte — insumo do gráfico central.

    Os bins nunca cruzam o corte: 0 é sempre uma borda. Um bin que
    misture eleitos e não eleitos suaviza visualmente exatamente o salto
    que o gráfico existe para mostrar.
    """
    d = df[[desfecho, running]].dropna()
    d = d[np.abs(d[running]) <= janela].copy()
    lado = max(n_bins // 2, 2)
    bordas = np.concatenate([np.linspace(-janela, 0, lado + 1),
                             np.linspace(0, janela, lado + 1)[1:]])
    d["bin"] = pd.cut(d[running], bins=bordas, include_lowest=True)
    agr = (d.groupby("bin", observed=True)
             .agg(x=(running, "mean"), y=(desfecho, "mean"),
                  ep=(desfecho, "sem"), n=(desfecho, "size"))
             .reset_index(drop=True).dropna(subset=["x"]))
    agr["lado"] = np.where(agr["x"] >= 0, "eleito", "nao_eleito")
    return agr
