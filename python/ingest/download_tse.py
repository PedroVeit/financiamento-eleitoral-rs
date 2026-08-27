"""Baixa os pacotes do Repositório de Dados Eleitorais do TSE.

Três conjuntos, por ano de eleição:

  consulta_cand ............. cadastro de candidaturas
  votacao_candidato_munzona . votação nominal por município e zona
  prestacao_de_contas ....... receitas e despesas de campanha

Uso:
    python -m python.ingest.download_tse --anos 2020 2024
    python -m python.ingest.download_tse --anos 2026 --inspecionar
    python -m python.ingest.download_tse --anos 2018 2020 2022 2024 --uf RS

MANUTENÇÃO
----------
O TSE renomeia arquivos e colunas entre eleições, sem aviso. Duas
defesas:

1. As URLs ficam centralizadas em FONTES — a quebra é de uma linha só.
2. `--inspecionar` baixa o pacote e imprime o cabeçalho de cada CSV, sem
   extrair nada. É o primeiro comando a rodar ao abrir um ano novo:
   compare a saída com COLMAP em load_to_duckdb.py.

Os arquivos são grandes (a prestação de contas de um ano geral passa de
1 GB descompactada). Nada é rebaixado se o zip já existe.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
import zipfile
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[2]
DIR_RAW = RAIZ / "data" / "raw"

CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele"

#: Chave = subpasta em data/raw/. Conferir na página do dataset do ano
#: em dadosabertos.tse.jus.br se um download falhar com 404.
FONTES = {
    "candidatos": f"{CDN}/consulta_cand/consulta_cand_{{ano}}.zip",
    "resultados": f"{CDN}/votacao_candidato_munzona/votacao_candidato_munzona_{{ano}}.zip",
    "contas": f"{CDN}/prestacao_contas/prestacao_de_contas_eleitorais_candidatos_{{ano}}.zip",
}

ANOS_SUPORTADOS = (2018, 2020, 2022, 2024, 2026)
TIMEOUT = 180
BLOCO = 1 << 20


def baixar(url: str, destino: Path, forcar: bool = False) -> Path:
    if destino.exists() and destino.stat().st_size > 0 and not forcar:
        print(f"  [cache]   {destino.name} ({destino.stat().st_size / 1e6:.0f} MB)")
        return destino

    destino.parent.mkdir(parents=True, exist_ok=True)
    print(f"  [baixando] {url}")
    parcial = destino.with_suffix(destino.suffix + ".part")
    with requests.get(url, stream=True, timeout=TIMEOUT) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0))
        feito = 0
        with open(parcial, "wb") as fh:
            for bloco in resp.iter_content(chunk_size=BLOCO):
                fh.write(bloco)
                feito += len(bloco)
                if total:
                    print(f"\r    {100 * feito / total:5.1f}%  "
                          f"({feito / 1e6:.0f}/{total / 1e6:.0f} MB)", end="", flush=True)
        print()
    parcial.rename(destino)
    sha = hashlib.sha256(destino.read_bytes()).hexdigest()[:16]
    print(f"  [ok]      {destino.name}  sha256:{sha}")
    return destino


def extrair(zip_path: Path, dir_saida: Path, apenas_uf: str | None = None) -> list[Path]:
    """Extrai os CSVs. Com `apenas_uf`, só os daquela UF — os pacotes do
    TSE trazem o Brasil inteiro e o resto é disco jogado fora."""
    dir_saida.mkdir(parents=True, exist_ok=True)
    extraidos: list[Path] = []
    with zipfile.ZipFile(zip_path) as zf:
        for nome in zf.namelist():
            if not nome.lower().endswith((".csv", ".txt")):
                continue
            if apenas_uf and f"_{apenas_uf.upper()}." not in nome.upper():
                continue
            zf.extract(nome, dir_saida)
            extraidos.append(dir_saida / nome)
    if not extraidos:
        with zipfile.ZipFile(zip_path) as zf:
            print(f"  [aviso]   nenhum CSV extraído de {zip_path.name}. "
                  f"Conteúdo: {zf.namelist()[:5]}")
    else:
        print(f"  [extraído] {len(extraidos)} arquivo(s) de {zip_path.name}")
    return extraidos


def inspecionar(zip_path: Path, apenas_uf: str | None = None) -> None:
    """Imprime o cabeçalho de cada CSV sem extrair. Use ao abrir um ano novo."""
    with zipfile.ZipFile(zip_path) as zf:
        for nome in zf.namelist():
            if not nome.lower().endswith(".csv"):
                continue
            if apenas_uf and f"_{apenas_uf.upper()}." not in nome.upper():
                continue
            with zf.open(nome) as fh:
                cabecalho = io.TextIOWrapper(fh, encoding="latin-1").readline()
            cols = [c.strip('"') for c in cabecalho.rstrip("\r\n").split(";")]
            print(f"\n  {nome}\n    {len(cols)} colunas: {cols}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Baixa dados eleitorais do TSE.")
    p.add_argument("--anos", nargs="+", type=int, default=[2020, 2024],
                   help=f"anos de eleição (suportados: {ANOS_SUPORTADOS})")
    p.add_argument("--uf", default="RS",
                   help="extrair apenas os CSVs desta UF (TODAS para não filtrar)")
    p.add_argument("--forcar", action="store_true", help="rebaixa mesmo se o zip existir")
    p.add_argument("--inspecionar", action="store_true",
                   help="imprime os cabeçalhos dos CSVs e sai, sem extrair")
    args = p.parse_args(argv)

    uf = None if args.uf.upper() == "TODAS" else args.uf.upper()
    houve_erro = False

    for ano in args.anos:
        if ano not in ANOS_SUPORTADOS:
            print(f"[aviso] {ano} fora da lista suportada; tentando mesmo assim.")
        print(f"\n=== Eleição {ano} ===")
        for chave, molde in FONTES.items():
            url = molde.format(ano=ano)
            zip_path = DIR_RAW / "zip" / f"{chave}_{ano}.zip"
            try:
                baixar(url, zip_path, forcar=args.forcar)
            except requests.RequestException as e:
                houve_erro = True
                print(f"  [erro]    {chave} {ano}: {e}\n"
                      f"            confira a URL do recurso em dadosabertos.tse.jus.br "
                      f"e ajuste FONTES['{chave}'].", file=sys.stderr)
                continue
            if args.inspecionar:
                inspecionar(zip_path, apenas_uf=uf)
            else:
                extrair(zip_path, DIR_RAW / chave / str(ano), apenas_uf=uf)

    return 1 if houve_erro else 0


if __name__ == "__main__":
    sys.exit(main())
