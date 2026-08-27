"""Deflator IPCA.

Por que isto existe: comparar o gasto de campanha de 2018 com o de 2024
em reais nominais é errado, e o erro aparece direto nos gráficos — a
inflação acumulada no período é grande o bastante para inventar uma
"tendência de alta" que não existe.

Como funciona
-------------
`IPCA_ANUAL` guarda a variação acumulada no ano (dezembro/dezembro,
IBGE — SIDRA tabela 1737). A partir dela o módulo encadeia um índice de
nível de preços com base 100 em `ANO_BASE`. O SQL usa
`fator = 100 / indice`, de modo que

    valor_real = valor_nominal * fator

converte para reais do ano-base.

Limitações declaradas
---------------------
1. Deflacionar um fluxo anual por um índice de fim de período é uma
   aproximação. O rigoroso seria deflacionar cada lançamento pela data
   da transação, usando a série mensal — o schema guarda `data_receita`
   e `data_despesa` justamente para permitir isso depois.
2. Anos sem taxa registrada aqui ficam SEM deflação, e a validação da
   carga imprime "ano sem deflator IPCA" com contagem diferente de zero.
   O pipeline não inventa fator 1 em silêncio.
3. Antes de publicar, conferir a série contra o SIDRA. As taxas abaixo
   são as oficiais divulgadas até o fechamento de cada ano; ano corrente
   e anos futuros não entram até fechar.

Para atualizar: acrescente o ano em IPCA_ANUAL e rode
`python -m python.ingest.deflator` para conferir o índice resultante.
"""

from __future__ import annotations

#: Ano de referência dos valores reais reportados no projeto.
ANO_BASE = 2024

#: IPCA — variação acumulada no ano (% a.a., dez/dez). Fonte: IBGE/SIDRA.
IPCA_ANUAL: dict[int, float] = {
    2014: 6.41,
    2015: 10.67,
    2016: 6.29,
    2017: 2.95,
    2018: 3.75,
    2019: 4.31,
    2020: 4.52,
    2021: 10.06,
    2022: 5.79,
    2023: 4.62,
    2024: 4.83,
    # 2025 em diante: preencher com o dado fechado do IBGE antes de usar
    # qualquer eleição desses anos. Sem a linha aqui, o ano entra sem
    # deflação e a validação avisa.
}


def construir_indice(taxas: dict[int, float] = IPCA_ANUAL,
                     ano_base: int = ANO_BASE) -> dict[int, float]:
    """Encadeia as taxas anuais num índice de nível de preços, base 100.

    `taxas[ano]` é a inflação DE `ano-1` PARA `ano`, então o índice do
    ano é o do anterior corrigido por essa taxa.
    """
    anos = sorted(taxas)
    if ano_base not in anos:
        raise ValueError(f"ano-base {ano_base} não está na série de taxas")

    indice = {anos[0]: 100.0}
    for ano in anos[1:]:
        indice[ano] = indice[ano - 1] * (1 + taxas[ano] / 100)

    escala = 100.0 / indice[ano_base]
    return {ano: round(v * escala, 6) for ano, v in indice.items()}


#: Índice pronto para carga na tabela `ipca`.
SERIE_IPCA: dict[int, float] = construir_indice()


def fator(ano: int) -> float | None:
    """Multiplicador que leva reais nominais de `ano` para reais do ano-base."""
    i = SERIE_IPCA.get(ano)
    return None if i is None else 100.0 / i


if __name__ == "__main__":
    print(f"índice IPCA (base 100 = {ANO_BASE})\n")
    print(f"{'ano':>6} {'índice':>10} {'fator':>8}")
    for ano, i in SERIE_IPCA.items():
        print(f"{ano:>6} {i:>10.3f} {100 / i:>8.4f}")
