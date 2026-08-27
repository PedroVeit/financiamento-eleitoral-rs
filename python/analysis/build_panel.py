"""Pareia a MESMA PESSOA entre duas eleições e popula `painel_link`.

O problema
----------
O TSE não publica um identificador estável de pessoa entre eleições:
SQ_CANDIDATO muda a cada pleito, e o CPF deixou de ser publicado
integralmente em parte dos arquivos. O pareamento é, portanto,
probabilístico e imperfeito — e a taxa de erro precisa ser reportada,
não escondida.

Cascata, do mais forte ao mais fraco:

    nível 1  hash do CPF                              (determinístico)
    nível 2  nome completo normalizado + município
    nível 3  nome completo normalizado + UF           (cobre mudança de município)
    nível 4  nome de urna normalizado + município + partido

Cada par carrega o nível que o produziu. A análise principal roda com os
níveis 1-2; os níveis 3-4 entram só em teste de robustez, e o resultado
não pode depender deles.

**Ambiguidade é descartada, não resolvida.** Se um nome aparece mais de
uma vez de qualquer lado, o par é jogado fora. Homônimo pareado por
heurística vira efeito espúrio, e um efeito espúrio é pior que uma
observação a menos.

Uso:
    python -m python.analysis.build_panel --de 2020 --para 2024
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

import duckdb
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

BANCO_PADRAO = RAIZ / "data" / "db" / "financiamento.duckdb"

#: (nível, colunas-chave, descrição)
CASCATA: list[tuple[int, list[str], str]] = [
    (1, ["cpf_hash"],                            "hash do CPF"),
    (2, ["nome_n", "cd_municipio"],              "nome completo + município"),
    (3, ["nome_n", "uf"],                        "nome completo + UF"),
    (4, ["urna_n", "cd_municipio", "partido"],   "nome de urna + município + partido"),
]

#: níveis considerados confiáveis para a análise principal
NIVEIS_PRINCIPAIS = (1, 2)


def normalizar(nome: str | None) -> str:
    """Maiúsculas, sem acento, sem pontuação, espaços colapsados."""
    if not nome or (isinstance(nome, float) and pd.isna(nome)):
        return ""
    s = unicodedata.normalize("NFKD", str(nome))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = "".join(c if c.isalnum() or c == " " else " " for c in s.upper())
    return " ".join(s.split())


def _carregar_lado(con, ano: int) -> pd.DataFrame:
    df = con.execute("""
        SELECT sq_candidato, nome_candidato, nome_urna, cd_municipio, uf,
               partido, cpf_hash
        FROM candidatos WHERE ano_eleicao = ? AND turno = 1
    """, [ano]).df()
    df["nome_n"] = df["nome_candidato"].map(normalizar)
    df["urna_n"] = df["nome_urna"].map(normalizar)
    return df


def _casar(esq: pd.DataFrame, dir_: pd.DataFrame,
           chaves: list[str], nivel: int, regra: str) -> pd.DataFrame:
    """Junta por `chaves`, mantendo apenas pares 1-para-1."""
    vazio = pd.DataFrame(columns=["sq_t", "sq_t1", "nivel_match", "regra"])

    e = esq[~esq["_usado"]].dropna(subset=chaves)
    d = dir_.dropna(subset=chaves)
    for c in chaves:                       # string vazia não é chave válida
        if e[c].dtype == object:
            e = e[e[c].astype(str).str.len() > 0]
            d = d[d[c].astype(str).str.len() > 0]
    if e.empty or d.empty:
        return vazio

    unico_e = e.groupby(chaves, dropna=False)["sq_candidato"].transform("size") == 1
    unico_d = d.groupby(chaves, dropna=False)["sq_candidato"].transform("size") == 1
    m = e[unico_e].merge(d[unico_d], on=chaves, suffixes=("_t", "_t1"))
    if m.empty:
        return vazio

    return pd.DataFrame({
        "sq_t": m["sq_candidato_t"].astype("int64"),
        "sq_t1": m["sq_candidato_t1"].astype("int64"),
        "nivel_match": nivel,
        "regra": regra,
    })


def parear(con, ano_t: int, ano_t1: int, verbose: bool = True) -> pd.DataFrame:
    a = _carregar_lado(con, ano_t)
    b = _carregar_lado(con, ano_t1)
    a["_usado"] = False

    pares: list[pd.DataFrame] = []
    for nivel, chaves, regra in CASCATA:
        p = _casar(a, b, chaves, nivel, regra)
        if not p.empty:
            # não reutiliza um candidato de t+1 já pareado num nível mais forte
            ja_usados_t1 = pd.concat(pares)["sq_t1"] if pares else pd.Series(dtype="int64")
            p = p[~p["sq_t1"].isin(ja_usados_t1)]
            a.loc[a["sq_candidato"].isin(p["sq_t"]), "_usado"] = True
        pares.append(p)

    link = pd.concat(pares, ignore_index=True).drop_duplicates("sq_t")
    link["ano_t"] = ano_t
    link["ano_t1"] = ano_t1

    if verbose:
        print(f"\npareamento {ano_t} -> {ano_t1}")
        print(f"  candidaturas em {ano_t}: {len(a):,}")
        print(f"  candidaturas em {ano_t1}: {len(b):,}")
        for nivel, _, regra in CASCATA:
            n = int((link["nivel_match"] == nivel).sum())
            print(f"    nível {nivel} ({regra}): {n:,}")
        print(f"  pareados: {len(link):,} "
              f"({len(link) / max(len(a), 1):.1%} das candidaturas de {ano_t})")
        print(f"  usados na análise principal (níveis {NIVEIS_PRINCIPAIS}): "
              f"{int(link['nivel_match'].isin(NIVEIS_PRINCIPAIS).sum()):,}")
    return link[["sq_t", "sq_t1", "ano_t", "ano_t1", "nivel_match", "regra"]]


def construir_painel(con, ano_t: int, ano_t1: int, verbose: bool = True) -> int:
    """Popula `painel_link` e reaplica as views que dependem dela."""
    from python.ingest.load_to_duckdb import aplicar_views

    link = parear(con, ano_t, ano_t1, verbose=verbose)
    con.execute("DELETE FROM painel_link WHERE ano_t = ? AND ano_t1 = ?",
                [ano_t, ano_t1])
    con.register("_link", link)
    con.execute("INSERT INTO painel_link SELECT * FROM _link")
    con.unregister("_link")
    aplicar_views(con)

    n = con.execute("SELECT COUNT(*) FROM vw_painel_rdd WHERE concorreu_t1").fetchone()[0]
    if verbose:
        print(f"  vw_painel_rdd com desfecho observado: {n:,}")
    return len(link)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--de", type=int, required=True)
    p.add_argument("--para", type=int, required=True)
    p.add_argument("--banco", default=str(BANCO_PADRAO))
    args = p.parse_args(argv)

    con = duckdb.connect(args.banco)
    construir_painel(con, args.de, args.para)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
