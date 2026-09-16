from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

DIR_RAW_PADRAO = RAIZ / "data" / "raw"

#: efeito causal verdadeiro de ser eleito em t sobre ln(receita) em t+1
TAU_PADRAO = 0.55

PARTIDOS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"]
CATEGORIAS = ["PUBLICIDADE POR MATERIAIS IMPRESSOS", "DESPESA COM PESSOAL",
              "PUBLICIDADE POR INTERNET", "COMBUSTIVEIS E LUBRIFICANTES",
              "SERVICOS PRESTADOS POR TERCEIROS", "ALUGUEL DE BENS MOVEIS"]
FONTES_TSE = [
    ("Fundo Especial de Financiamento de Campanha", "Recursos de partido politico"),
    ("Doacoes de pessoas fisicas", "Recursos de pessoas fisicas"),
    ("Recursos proprios", "Recursos proprios"),
    ("Doacoes de outros candidatos", "Recursos de outros candidatos"),
    ("Fundo Partidario", "Recursos de partido politico"),
]
PESOS_FONTE = [0.35, 0.30, 0.15, 0.10, 0.10]


def _brl(v: float) -> str:
    """Decimal no formato do TSE: vírgula decimal, sem separador de milhar."""
    return f"{v:.2f}".replace(".", ",")


def _csv(linhas: list[dict], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(linhas).to_csv(caminho, sep=";", index=False,
                                encoding="latin-1", quoting=1)


# ---------------------------------------------------------------------
# Geração
# ---------------------------------------------------------------------
def gerar(
    dir_raw: Path | str = DIR_RAW_PADRAO,
    anos: tuple[int, int] = (2020, 2024),
    n_municipios: int = 90,
    listas_por_municipio: int = 6,
    candidatos_por_lista: int = 12,
    efeito_verdadeiro: float = TAU_PADRAO,
    prob_recandidatura: float = 0.55,
    bonus_recand_eleito: float = 0.15,
    frac_cpf_publicado: float = 0.6,
    frac_homonimos: float = 0.02,
    semente: int = 20260827,
) -> dict:

   
    dir_raw = Path(dir_raw)
    rng = np.random.default_rng(semente)
    ano_t, ano_t1 = anos

    pessoas: list[dict] = []
    cand_t, voto_t, rec_t, desp_t = [], [], [], []
    sq = ano_t * 10_000_000

    # ---- eleição t --------------------------------------------------
    for m in range(n_municipios):
        cd_mun = f"{80000 + m}"
        nm_mun = f"MUNICIPIO {m:03d}"
        for li in range(listas_por_municipio):
            partido = PARTIDOS[li % len(PARTIDOS)]
            id_lista = f"{ano_t}{m:03d}{li}"
            n_cand = candidatos_por_lista
            # cadeiras da lista: aproxima quociente eleitoral + sobras,
            # sem relação com os candidatos individuais
            cadeiras = int(rng.integers(1, min(5, n_cand)))

            qualidade = rng.normal(size=n_cand)
            ln_receita = 9.0 + 0.60 * qualidade + rng.normal(0, 0.50, n_cand)
            receita = np.exp(ln_receita)
            votos = np.maximum(
                np.round(np.exp(5.2 + 0.45 * qualidade + rng.normal(0, 0.55, n_cand))),
                1).astype(int)

            ordem = np.argsort(-votos)
            eleito = np.zeros(n_cand, dtype=bool)
            eleito[ordem[:cadeiras]] = True

            for i in range(n_cand):
                sq += 1
                nome = f"CANDIDATO {m:03d} {li} {i:02d}"
                if rng.random() < frac_homonimos:
                    nome = f"CANDIDATO HOMONIMO {li} {i:02d}"   # repete entre municípios
                cpf = f"{rng.integers(10**10, 10**11)}"
                genero = "FEMININO" if rng.random() < 0.35 else "MASCULINO"
                idade = int(rng.integers(21, 70))
                posicao = int(np.where(ordem == i)[0][0]) + 1
                situacao = ("ELEITO POR QP" if eleito[i]
                            else ("SUPLENTE" if posicao <= cadeiras + 4 else "NAO ELEITO"))

                cand_t.append(_linha_cand(
                    sq, ano_t, cd_mun, nm_mun, partido, id_lista, nome, cpf,
                    genero, idade, i, publicar_cpf=rng.random() < frac_cpf_publicado))
                voto_t.append(dict(
                    ANO_ELEICAO=ano_t, NR_TURNO=1, SQ_CANDIDATO=sq,
                    CD_MUNICIPIO=cd_mun, NR_ZONA=1,
                    QT_VOTOS_NOMINAIS=int(votos[i]),
                    DS_SIT_TOT_TURNO=situacao))
                _lancamentos(rec_t, desp_t, sq, ano_t, float(receita[i]), rng)

                pessoas.append(dict(
                    sq_t=sq, nome=nome, cpf=cpf, cd_mun=cd_mun, nm_mun=nm_mun,
                    partido=partido, m=m, li=li, i=i,
                    qualidade=float(qualidade[i]), eleito=bool(eleito[i]),
                    genero=genero, idade=idade))

    # ---- eleição t+1 ------------------------------------------------
    cand_t1, voto_t1, rec_t1, desp_t1 = [], [], [], []
    concorrentes: list[dict] = []
    sq = ano_t1 * 10_000_000

    for p in pessoas:
        limiar = prob_recandidatura + (bonus_recand_eleito if p["eleito"] else 0.0)
        if rng.random() > limiar:
            continue                                    # não se recandidatou
        sq += 1
        # AQUI entra o efeito causal verdadeiro
        ln_receita = (9.0 + 0.60 * p["qualidade"]
                      + efeito_verdadeiro * p["eleito"]
                      + rng.normal(0, 0.50))
        votos = int(max(round(np.exp(5.2 + 0.45 * p["qualidade"]
                                     + 0.30 * p["eleito"]
                                     + rng.normal(0, 0.55))), 1))
        concorrentes.append(dict(sq_t1=sq, pessoa=p, votos=votos,
                                 receita=float(np.exp(ln_receita)),
                                 id_lista=f"{ano_t1}{p['m']:03d}{p['li']}"))

    # eleitos em t+1: mesma regra (cadeiras da lista, mais votados dentro dela)
    df = pd.DataFrame([{"sq_t1": c["sq_t1"], "id_lista": c["id_lista"],
                        "votos": c["votos"]} for c in concorrentes])
    eleitos_t1: set[int] = set()
    for id_lista, grupo in df.groupby("id_lista"):
        cadeiras = min(int(rng.integers(1, 5)), max(len(grupo) - 1, 1))
        eleitos_t1.update(grupo.nlargest(cadeiras, "votos")["sq_t1"].tolist())

    for c in concorrentes:
        p, sq_ = c["pessoa"], c["sq_t1"]
        foi_eleito = sq_ in eleitos_t1
        cand_t1.append(_linha_cand(
            sq_, ano_t1, p["cd_mun"], p["nm_mun"], p["partido"], c["id_lista"],
            p["nome"], p["cpf"], p["genero"], p["idade"] + 4, p["i"],
            publicar_cpf=rng.random() < frac_cpf_publicado,
            reeleicao="S" if p["eleito"] else "N"))
        voto_t1.append(dict(
            ANO_ELEICAO=ano_t1, NR_TURNO=1, SQ_CANDIDATO=sq_,
            CD_MUNICIPIO=p["cd_mun"], NR_ZONA=1,
            QT_VOTOS_NOMINAIS=c["votos"],
            DS_SIT_TOT_TURNO="ELEITO POR QP" if foi_eleito else "NAO ELEITO"))
        _lancamentos(rec_t1, desp_t1, sq_, ano_t1, c["receita"], rng)

    # ---- escrita ----------------------------------------------------
    for ano, cands, votos_, recs, desps in [
        (ano_t, cand_t, voto_t, rec_t, desp_t),
        (ano_t1, cand_t1, voto_t1, rec_t1, desp_t1),
    ]:
        _csv(cands, dir_raw / "candidatos" / str(ano) / f"consulta_cand_{ano}_RS.csv")
        _csv(votos_, dir_raw / "resultados" / str(ano) /
             f"votacao_candidato_munzona_{ano}_RS.csv")
        _csv(recs, dir_raw / "contas" / str(ano) / f"receitas_candidatos_{ano}_RS.csv")
        _csv(desps, dir_raw / "contas" / str(ano) /
             f"despesas_contratadas_candidatos_{ano}_RS.csv")
        print(f"  {ano}: {len(cands):,} candidaturas, {len(recs):,} receitas, "
              f"{len(desps):,} despesas")

    gabarito = pd.DataFrame([
        {"sq_t": c["pessoa"]["sq_t"], "sq_t1": c["sq_t1"],
         "nome": c["pessoa"]["nome"], "eleito_t": c["pessoa"]["eleito"],
         "qualidade": c["pessoa"]["qualidade"]}
        for c in concorrentes])
    return {"efeito_verdadeiro": efeito_verdadeiro, "anos": anos,
            "n_pessoas": len(pessoas), "gabarito_painel": gabarito}


def _linha_cand(sq, ano, cd_mun, nm_mun, partido, id_lista, nome, cpf,
                genero, idade, i, publicar_cpf: bool, reeleicao: str = "N") -> dict:
    return {
        "ANO_ELEICAO": ano, "NR_TURNO": 1, "SG_UF": "RS",
        "SG_UE": cd_mun, "NM_UE": nm_mun,
        "CD_CARGO": 13, "DS_CARGO": "VEREADOR",
        "SQ_CANDIDATO": sq,
        "NM_CANDIDATO": nome,
        "NM_URNA_CANDIDATO": nome.replace("CANDIDATO ", "CAND "),
        "NR_CANDIDATO": f"{PARTIDOS.index(partido) + 10}{i:03d}",
        "SG_PARTIDO": partido, "NR_PARTIDO": PARTIDOS.index(partido) + 10,
        "SQ_COLIGACAO": id_lista, "NM_COLIGACAO": f"LISTA {partido}",
        # o TSE deixou de publicar o CPF completo em parte dos arquivos
        "NR_CPF_CANDIDATO": cpf if publicar_cpf else "",
        "DS_GENERO": genero,
        "DS_COR_RACA": "BRANCA",
        "DS_GRAU_INSTRUCAO": "SUPERIOR COMPLETO",
        "DS_OCUPACAO": "OUTROS",
        "NR_IDADE_DATA_POSSE": idade,
        "ST_REELEICAO": reeleicao,
        "DS_SITUACAO_CANDIDATURA": "APTO",
    }


def _lancamentos(receitas, despesas, sq, ano, receita_total, rng) -> None:
    """Quebra o total do candidato em lançamentos por fonte, como no TSE."""
    pesos = rng.dirichlet(np.array(PESOS_FONTE) * 6)
    for (fonte, origem), peso in zip(FONTES_TSE, pesos):
        valor = receita_total * peso
        if valor < 1:
            continue
        receitas.append({
            "ANO_ELEICAO": ano, "SQ_CANDIDATO": sq,
            "SQ_RECEITA": f"{sq}-{len(receitas)}",
            "DS_FONTE_RECEITA": fonte,
            "DS_ORIGEM_RECEITA": origem,
            "VR_RECEITA": _brl(valor),
            "DT_RECEITA": f"{int(rng.integers(1, 29)):02d}/09/{ano}",
            "NR_CPF_CNPJ_DOADOR": f"{rng.integers(10**10, 10**11)}",
        })
    total_desp = receita_total * float(rng.uniform(0.88, 1.0))
    n_tx = int(rng.integers(3, 8))
    partes = rng.dirichlet(np.ones(n_tx)) * total_desp
    for k, v in enumerate(partes):
        despesas.append({
            "ANO_ELEICAO": ano, "SQ_CANDIDATO": sq,
            "SQ_DESPESA": f"{sq}-d{k}",
            "DS_TIPO_DESPESA": CATEGORIAS[k % len(CATEGORIAS)],
            "VR_DESPESA_CONTRATADA": _brl(float(v)),
            "DT_DESPESA": f"{int(rng.integers(1, 29)):02d}/09/{ano}",
            "NR_CPF_CNPJ_FORNECEDOR": f"{rng.integers(10**13, 10**14)}",
        })


# ---------------------------------------------------------------------
# Atalho: gerar + carregar + parear, devolvendo o banco pronto
# ---------------------------------------------------------------------
def construir_banco(banco: Path | str, dir_raw: Path | str | None = None,
                    quieto: bool = True, **kwargs):
    """Gera CSVs, carrega no DuckDB e monta o painel.

    Devolve `(conexão, gabarito)`. O gabarito traz o efeito verdadeiro e
    o pareamento correto entre eleições — é contra ele que os testes
    conferem o estimador e o algoritmo de painel.
    """
    import contextlib
    import io as _io
    import tempfile

    from python.analysis.build_panel import construir_painel
    from python.ingest.load_to_duckdb import carregar_tse, criar_banco

    tmp = None
    if dir_raw is None:
        tmp = tempfile.TemporaryDirectory()
        dir_raw = Path(tmp.name)

    silencio = contextlib.redirect_stdout(_io.StringIO()) if quieto \
        else contextlib.nullcontext()
    with silencio:
        info = gerar(dir_raw=dir_raw, **kwargs)
        ano_t, ano_t1 = info["anos"]
        con = criar_banco(banco, recriar=True)
        import python.ingest.load_to_duckdb as mod
        raw_original = mod.DIR_RAW
        mod.DIR_RAW = Path(dir_raw)
        try:
            carregar_tse(con, [ano_t, ano_t1])
        finally:
            mod.DIR_RAW = raw_original
        construir_painel(con, ano_t, ano_t1)

    info["_tmpdir"] = tmp    # referência viva: o diretório some se for coletado
    return con, info


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gera os CSVs sintéticos de teste.")
    p.add_argument("--raw", type=Path, default=DIR_RAW_PADRAO)
    p.add_argument("--municipios", type=int, default=90)
    p.add_argument("--efeito", type=float, default=TAU_PADRAO)
    p.add_argument("--anos", type=int, nargs=2, default=[2020, 2024])
    p.add_argument("--semente", type=int, default=20260827)
    args = p.parse_args(argv)

    print(f"gerando dados sintéticos (TAU verdadeiro = {args.efeito})")
    info = gerar(dir_raw=args.raw, anos=tuple(args.anos),
                 n_municipios=args.municipios, efeito_verdadeiro=args.efeito,
                 semente=args.semente)
    print(f"\n{info['n_pessoas']:,} pessoas em t; CSVs em {args.raw}/")
    print("Agora rode: python -m python.ingest.load_to_duckdb")
    return 0


if __name__ == "__main__":
    sys.exit(main())
