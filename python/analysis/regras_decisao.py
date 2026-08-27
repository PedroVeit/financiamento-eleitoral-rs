"""Regras de decisão pré-registradas.

Este módulo aplica, de forma mecânica, os critérios fixados em
`docs/nota_metodologica_rdd.md` (seção 8) ANTES de qualquer execução
sobre dados reais. O ponto é tirar da mão de quem escreve o relatório a
decisão de quando um resultado "conta".

O veredito possível é um de três:

    IDENTIFICADO      os pressupostos testáveis passaram; o efeito pode
                      ser reportado como estimativa causal local.
    CONDICIONAL       o efeito existe, mas a amostra do desfecho é
                      selecionada pelo próprio tratamento; só pode ser
                      reportado com o rótulo de condicional.
    NAO_IDENTIFICADO  algum pressuposto falhou; o número NÃO deve ser
                      apresentado como efeito causal, com ou sem
                      ressalva.

"Não foi possível identificar um efeito robusto" é uma conclusão
publicável, e é a conclusão correta quando os pressupostos falham.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

#: nível de significância usado em todos os testes de validade
ALFA = 0.05

#: quantos placebos podem falhar por acaso antes de virar padrão.
#: Testar k covariáveis a 5% produz, sob a hipótese nula, cerca de
#: 0,05*k falsos positivos — um deles falhar é esperado, vários não.
MAX_PLACEBOS_FALHOS = 1

#: variação relativa tolerada do efeito ao longo da varredura de janelas
TOLERANCIA_INSTABILIDADE = 0.50


@dataclass
class Veredito:
    status: str                                   # IDENTIFICADO | CONDICIONAL | NAO_IDENTIFICADO
    motivos: list[str] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        linhas = [f"veredito: {self.status}"]
        linhas += [f"  motivo:  {m}" for m in self.motivos]
        linhas += [f"  alerta:  {a}" for a in self.alertas]
        return "\n".join(linhas)

    def como_dict(self) -> dict:
        return {"status": self.status, "motivos": self.motivos,
                "alertas": self.alertas}


def _p(d: dict | pd.Series, chave: str = "p_valor") -> float | None:
    v = d.get(chave)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(v) else v


def avaliar(relatorio: dict, desfecho_principal: str) -> Veredito:
    """Aplica as regras ao dicionário produzido por run_pipeline.rodar."""
    motivos: list[str] = []
    alertas: list[str] = []
    bloqueado = False
    condicional = False

    # -- 1. manipulação da variável de corte --------------------------
    dens = relatorio.get("densidade", {}) or {}
    p_dens = _p(dens)
    if p_dens is None:
        alertas.append("teste de densidade não pôde ser calculado — "
                       "verificar manualmente antes de publicar")
    elif p_dens < ALFA:
        bloqueado = True
        motivos.append(f"densidade da variável de corte salta no corte "
                       f"(p = {p_dens:.4f}): há indício de manipulação, "
                       f"e o desenho pressupõe que não haja")

    # -- 2. continuidade de covariáveis pré-tratamento ----------------
    cov = pd.DataFrame(relatorio.get("placebo_covariaveis", []))
    if not cov.empty and "p_valor" in cov:
        falhas = cov[cov["p_valor"] < ALFA]
        if len(falhas) > MAX_PLACEBOS_FALHOS:
            bloqueado = True
            motivos.append(
                f"{len(falhas)} de {len(cov)} covariáveis pré-tratamento saltam no "
                f"corte ({', '.join(falhas['desfecho'])}): os dois lados não são "
                f"comparáveis")
        elif len(falhas) == 1:
            alertas.append(
                f"a covariável '{falhas['desfecho'].iloc[0]}' salta no corte "
                f"(p = {falhas['p_valor'].iloc[0]:.4f}). Uma falha em {len(cov)} "
                f"testes é o esperado por acaso, mas precisa ser reportada — e "
                f"merece atenção especial se for a mais correlacionada com o desfecho")

    # -- 3. cortes placebo --------------------------------------------
    plc = pd.DataFrame(relatorio.get("placebo_cortes", []))
    if not plc.empty and "p_valor" in plc:
        falhas = plc[plc["p_valor"] < ALFA]
        if len(falhas) > MAX_PLACEBOS_FALHOS:
            bloqueado = True
            motivos.append(
                f"salto significativo em {len(falhas)} de {len(plc)} cortes falsos: "
                f"o modelo está detectando curvatura da função, não o tratamento")
        elif len(falhas) == 1:
            alertas.append("um corte placebo deu significante — esperado por acaso, "
                           "mas reportar")

    # -- 4. estabilidade em relação à janela --------------------------
    var = pd.DataFrame(relatorio.get("varredura_janelas", []))
    if not var.empty and "tau" in var:
        taus = pd.to_numeric(var["tau"], errors="coerce").dropna()
        if len(taus) >= 3:
            if (taus > 0).any() and (taus < 0).any():
                bloqueado = True
                motivos.append("o efeito troca de sinal ao longo da varredura de "
                               "janelas: a conclusão está sendo escolhida pela janela")
            elif abs(taus).max() > 0 and \
                    (taus.max() - taus.min()) / abs(taus).max() > TOLERANCIA_INSTABILIDADE:
                alertas.append(
                    f"efeito varia {(taus.max() - taus.min()) / abs(taus).max():.0%} "
                    f"entre as janelas testadas — reportar a varredura inteira, não "
                    f"só a banda ótima")

    # -- 5. seleção de amostra pelo tratamento ------------------------
    est = pd.DataFrame(relatorio.get("estimativas", []))
    if not est.empty and "desfecho" in est:
        ext = est[est["desfecho"] == "concorreu_t1"]
        if len(ext):
            p_ext = _p(ext.iloc[0])
            if p_ext is not None and p_ext < 0.10:
                condicional = True
                motivos.append(
                    f"ser eleito muda a probabilidade de voltar a concorrer "
                    f"(τ = {float(ext['tau'].iloc[0]):+.4f}, p = {p_ext:.4f}). "
                    f"O desfecho de receita só é observado para quem voltou, então "
                    f"'{desfecho_principal}' é um efeito CONDICIONAL a recandidatar-se "
                    f"— reportar com esse rótulo, ou calcular limites de Lee")

    # -- 6. concordância entre estimadores ----------------------------
    comp = pd.DataFrame(relatorio.get("comparacao_estimadores", []))
    if len(comp) == 2:
        taus = pd.to_numeric(comp["tau"], errors="coerce")
        eps = pd.to_numeric(comp["erro_padrao"], errors="coerce")
        if abs(taus.iloc[0] - taus.iloc[1]) > 2 * eps.max():
            alertas.append("rdrobust e o estimador próprio divergem além de 2 "
                           "erros-padrão — revisar a implementação antes de publicar")

    if bloqueado:
        return Veredito("NAO_IDENTIFICADO", motivos, alertas)
    if condicional:
        return Veredito("CONDICIONAL", motivos, alertas)
    return Veredito("IDENTIFICADO",
                    ["os pressupostos testáveis do desenho não foram rejeitados"],
                    alertas)
