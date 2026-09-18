"""Testes da camada SQL — variável de corte e integridade dos dados.

O erro mais provável e mais caro deste projeto é calcular a margem no
ranking da disputa inteira em vez de dentro da lista. Vários testes aqui
existem só para travar esse comportamento, porque é o tipo de coisa que
se reintroduz sem perceber numa refatoração.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from python.ingest.load_to_duckdb import criar_banco   # noqa: E402


# ---------------------------------------------------------------------
# Variável de corte
# ---------------------------------------------------------------------
def test_sinal_da_margem_bate_com_eleito(con):
    """margem > 0 <=> eleito. Sem exceção, e margem nunca é zero."""
    n = con.execute("SELECT COUNT(*) FROM vw_check_sinal_margem").fetchone()[0]
    assert n == 0, f"{n} candidaturas com sinal de margem inconsistente"


def test_margem_simetrica_dentro_da_lista(con):
    """A folga do último eleito e a do primeiro suplente são a mesma
    distância, com sinais opostos. Assimetria = bug no cálculo do corte."""
    df = con.execute("""
        SELECT * FROM vw_check_simetria_margem
        WHERE margem_pos IS NOT NULL AND margem_neg IS NOT NULL
    """).df()
    assert len(df) > 0, "nenhuma lista com par de fronteira: amostra vazia"
    assert ((df["margem_pos"] + df["margem_neg"]).abs() < 1e-9).all()


def test_listas_sem_corte_sao_excluidas(con):
    """Lista que elegeu todo mundo (ou ninguém) não tem contrafactual
    interno e não pode entrar na amostra."""
    df = con.execute("""
        SELECT id_lista_disputa,
               COUNT(*) FILTER (WHERE eleito)     AS n_eleitos,
               COUNT(*) FILTER (WHERE NOT eleito) AS n_nao_eleitos
        FROM vw_margem_candidato GROUP BY 1
    """).df()
    assert (df["n_eleitos"] >= 1).all()
    assert (df["n_nao_eleitos"] >= 1).all()


def test_empate_no_corte_e_descartado(con):
    """No Brasil o empate é desempatado pela idade, não por votos: nesses
    casos o tratamento não é função da variável de corte."""
    n = con.execute("""
        SELECT COUNT(*) FROM vw_margem_candidato m
        JOIN vw_corte_lista k USING (id_lista_disputa)
        WHERE k.v_ultimo_eleito = k.v_primeiro_suplente
    """).fetchone()[0]
    assert n == 0


def test_descartes_sao_contados_e_nao_silenciosos(con):
    """Toda lista fora da amostra tem que aparecer com motivo declarado."""
    df = con.execute("SELECT * FROM vw_listas_descartadas").df()
    assert set(df.columns) == {"motivo", "n_listas"}
    assert (df["n_listas"] > 0).all()


def test_amostra_de_fronteira_so_tem_par_completo(con):
    """Uma lista pode perder um dos lados do par quando há empate em
    votos entre dois candidatos dela (os empatados saem da amostra).
    Meio par não é comparação, então a amostra de fronteira exclui a
    lista inteira nesse caso."""
    df = con.execute("""
        SELECT id_lista_disputa,
               COUNT(*) FILTER (WHERE eh_ultimo_eleito)     AS n_ue,
               COUNT(*) FILTER (WHERE eh_primeiro_suplente) AS n_ps
        FROM vw_amostra_fronteira GROUP BY 1
    """).df()
    assert len(df) > 100
    assert (df["n_ue"] >= 1).all()
    assert (df["n_ps"] >= 1).all()


def test_amostra_de_fronteira_esta_contida_na_amostra_principal(con):
    a = con.execute("SELECT COUNT(*) FROM vw_amostra_fronteira").fetchone()[0]
    b = con.execute("SELECT COUNT(*) FROM vw_amostra_rdd").fetchone()[0]
    assert 0 < a < b


def test_margem_nao_usa_ranking_da_disputa(con):
    """Teste de regressão do erro conceitual.

    Em lista aberta existem candidatos eleitos que NÃO estão entre os N
    mais votados do município — eleitos pela força da lista. Se a margem
    fosse calculada no ranking geral, essa gente teria margem negativa.
    O teste documenta que o fenômeno existe nos dados: é a razão de a
    margem ser calculada por lista.
    """
    n = con.execute("""
        SELECT COUNT(*) FROM (
            SELECT eleito,
                   RANK() OVER (PARTITION BY ano_eleicao, municipio
                                ORDER BY votos_nominais DESC) AS rank_disputa,
                   SUM(CASE WHEN eleito THEN 1 ELSE 0 END)
                       OVER (PARTITION BY ano_eleicao, municipio) AS cadeiras
            FROM vw_financas_candidato
        ) WHERE eleito AND rank_disputa > cadeiras
    """).fetchone()[0]
    assert n > 0, ("nenhum eleito fora do topo do ranking municipal — o dado "
                   "sintético deixou de reproduzir a lista aberta e o teste "
                   "perdeu o sentido")


# ---------------------------------------------------------------------
# Integridade das finanças
# ---------------------------------------------------------------------
def test_receita_bate_com_a_soma_dos_lancamentos(con):
    """A view agregada não pode divergir da tabela de lançamentos."""
    a = con.execute("SELECT ROUND(SUM(valor), 2) FROM receitas").fetchone()[0]
    b = con.execute("SELECT ROUND(SUM(receita_total), 2) "
                    "FROM vw_financas_candidato").fetchone()[0]
    assert abs(float(a) - float(b)) < 1.0


def test_candidatura_sem_receita_nao_desaparece(con):
    """LEFT JOIN: quem não arrecadou aparece com 0, não some da amostra.
    Excluir esses casos em silêncio enviesa a média de gasto para cima."""
    a = con.execute("SELECT COUNT(*) FROM candidatos c JOIN resultados r "
                    "ON r.sq_candidato = c.sq_candidato "
                    "WHERE c.situacao_candidatura = 'APTO'").fetchone()[0]
    b = con.execute("SELECT COUNT(*) FROM vw_financas_candidato").fetchone()[0]
    assert a == b


def test_deflacao_e_aplicada(con):
    """Valor real e nominal têm de diferir nos anos que não são o ano-base."""
    from python.ingest.deflator import ANO_BASE
    df = con.execute("""
        SELECT ano_eleicao, ANY_VALUE(fator_deflator) AS fator,
               ANY_VALUE(deflacionado) AS ok
        FROM vw_financas_candidato GROUP BY 1 ORDER BY 1
    """).df()
    assert df["ok"].all(), "algum ano ficou sem deflator IPCA"
    for _, r in df.iterrows():
        if int(r["ano_eleicao"]) == ANO_BASE:
            assert abs(r["fator"] - 1.0) < 1e-6
        else:
            assert r["fator"] > 1.0, "ano anterior ao base deveria ter fator > 1"


def test_hash_nao_guarda_documento_em_claro(con):
    """Nenhum CPF/CNPJ pode sobreviver à ingestão em texto legível."""
    n = con.execute("""
        SELECT COUNT(*) FROM receitas
        WHERE doador_hash IS NOT NULL AND length(doador_hash) < 32
    """).fetchone()[0]
    assert n == 0
    amostra = con.execute("SELECT doador_hash FROM receitas "
                          "WHERE doador_hash IS NOT NULL LIMIT 1").fetchone()[0]
    assert not amostra.isdigit(), "doador_hash parece ser o documento em claro"


# ---------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------
def test_schema_aplica_em_banco_vazio(tmp_path):
    """schema.sql + views rodam do zero, sem dado nenhum."""
    c = criar_banco(tmp_path / "vazio.duckdb", recriar=True)
    assert c.execute("SELECT COUNT(*) FROM vw_financas_candidato").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM vw_painel_rdd").fetchone()[0] == 0
    c.close()


def test_schema_e_reexecutavel(tmp_path):
    """Rodar a carga duas vezes não pode duplicar candidatura."""
    from python.ingest.load_to_duckdb import aplicar_views
    c = criar_banco(tmp_path / "re.duckdb", recriar=True)
    aplicar_views(c)
    aplicar_views(c)
    assert c.execute("SELECT COUNT(*) FROM vw_amostra_rdd").fetchone()[0] == 0
    c.close()


# ---------------------------------------------------------------------
# Formato legado de prestação de contas (anos < 2018)
#
# O TSE usava, antes de 2018, cabeçalho em português por extenso em vez
# dos códigos ALLCAPS do resto do pipeline, com uma armadilha real: o
# nome da coluna do número do documento tem acento em "despesas"
# ("Número do documento") e NÃO tem em "receitas" ("Numero do
# documento"). Sem este teste, o pipeline só descobriria isso ao rodar
# contra o dado de 2016 de verdade -- tarde demais para corrigir sem
# recarregar tudo.
# ---------------------------------------------------------------------
def _escrever_legado(caminho, cabecalho: list[str], linhas: list[list[str]]) -> None:
    import csv
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="latin-1", newline="") as fh:
        w = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_ALL)
        w.writerow(cabecalho)
        for linha in linhas:
            w.writerow(linha)


def test_carga_legado_receitas_e_despesas(tmp_path, monkeypatch):
    from python.ingest import load_to_duckdb as mod

    monkeypatch.setattr(mod, "DIR_RAW", tmp_path)
    monkeypatch.setitem(mod.FORMATO_CONTAS_LEGADO, 2016, {
        "receitas_prefixo": "receitas_candidatos_prestacao_contas_final",
        "despesas_prefixo": "despesas_candidatos_prestacao_contas_final",
        "extensao": "txt",
    })

    # cabeçalho real de receitas 2016, com "Numero do documento" SEM acento
    cab_receitas = [
        "Cód. Eleição", "Desc. Eleição", "Data e hora", "CNPJ Prestador Conta",
        "Sequencial Candidato", "UF", "Sigla da UE", "Nome da UE",
        "Sigla  Partido", "Numero candidato", "Cargo", "Nome candidato",
        "CPF do candidato", "CPF do vice/suplente", "Numero Recibo Eleitoral",
        "Numero do documento", "CPF/CNPJ do doador", "Nome do doador",
        "Nome do doador (Receita Federal)", "Sigla UE doador",
        "Número partido doador", "Número candidato doador",
        "Cod setor econômico do doador", "Setor econômico do doador",
        "Data da receita", "Valor receita", "Tipo receita", "Fonte recurso",
        "Especie recurso", "Descricao da receita",
        "CPF/CNPJ do doador originário", "Nome do doador originário",
        "Tipo doador originário", "Setor econômico do doador originário",
        "Nome do doador originário (Receita Federal)",
    ]
    # "Tipo receita" leva a categoria detalhada de verdade (é o que a
    # classificação usa); "Fonte recurso" leva um valor grosseiro típico
    # do arquivo real ("Outros Recursos"), para não mascarar o bug real
    # que este teste existe para travar -- ver docs/decisoes.md, D17.
    linha_receita = ["2", "Eleição Municipal 2016", "01/10/2016", "", "999",
                     "RS", "12345", "MUNICIPIO TESTE", "AAA", "10123",
                     "Vereador", "FULANO DE TAL", "11122233344", "", "REC1",
                     "DOC1", "55566677788", "DOADOR TESTE", "", "", "", "",
                     "", "", "15/09/2016", "1.234,56", "Recursos de Pessoas Físicas",
                     "Outros Recursos", "Dinheiro", "Doação para campanha",
                     "", "", "", "", ""]

    # cabeçalho real de despesas 2016, com "Número do documento" COM acento
    cab_despesas = [
        "Cód. Eleição", "Desc. Eleição", "Data e hora", "CNPJ Prestador Conta",
        "Sequencial Candidato", "UF", "Sigla da UE", "Nome da UE",
        "Sigla  Partido", "Número candidato", "Cargo", "Nome candidato",
        "CPF do candidato", "CPF do vice/suplente", "Tipo de documento",
        "Número do documento", "CPF/CNPJ do fornecedor", "Nome do fornecedor",
        "Nome do fornecedor (Receita Federal)", "Cod setor econômico do fornecedor",
        "Setor econômico do fornecedor", "Data da despesa", "Valor despesa",
        "Tipo despesa", "Descriçao da despesa",
    ]
    linha_despesa = ["2", "Eleição Municipal 2016", "01/10/2016", "", "999",
                     "RS", "12345", "MUNICIPIO TESTE", "AAA", "10123",
                     "Vereador", "FULANO DE TAL", "11122233344", "", "Nota Fiscal",
                     "NF1", "99988877766", "FORNECEDOR TESTE", "", "", "",
                     "20/09/2016", "500,00", "Publicidade por materiais impressos",
                     "Panfletos"]

    _escrever_legado(
        tmp_path / "contas" / "2016" /
        "receitas_candidatos_prestacao_contas_final_2016_RS.txt",
        cab_receitas, [linha_receita])
    _escrever_legado(
        tmp_path / "contas" / "2016" /
        "despesas_candidatos_prestacao_contas_final_2016_RS.txt",
        cab_despesas, [linha_despesa])

    con = criar_banco(tmp_path / "legado.duckdb", recriar=True)
    con.execute("""
        INSERT INTO candidatos (sq_candidato, ano_eleicao, turno, cargo, uf,
                                municipio, partido, id_lista, situacao_candidatura)
        VALUES (999, 2016, 1, 'VEREADOR', 'RS', 'MUNICIPIO TESTE', 'AAA', 'AAA', 'APTO')
    """)

    n_rec = mod.carregar_receitas(con, 2016)
    n_desp = mod.carregar_despesas(con, 2016)
    assert n_rec == 1, "receita legada não foi inserida"
    assert n_desp == 1, "despesa legada não foi inserida"

    rec = con.execute("SELECT valor, fonte, data_receita, doador_tipo "
                      "FROM receitas WHERE ano_eleicao = 2016").fetchone()
    assert float(rec[0]) == 1234.56, "decimal brasileiro não foi convertido certo"
    assert rec[1] == "doacao_pf", f"classificação de fonte errada: {rec[1]}"
    assert str(rec[2]) == "2016-09-15", "data da receita não foi parseada certo"
    assert rec[3] == "PF"

    desp = con.execute("SELECT valor, categoria, data_despesa, fornecedor_tipo "
                       "FROM despesas WHERE ano_eleicao = 2016").fetchone()
    assert float(desp[0]) == 500.00, "decimal brasileiro não foi convertido certo (despesa)"
    assert "PUBLICIDADE" in desp[1].upper()
    assert str(desp[2]) == "2016-09-20"
    assert desp[3] == "PF"
    con.close()


def test_receita_legada_usa_tipo_receita_nao_fonte_recurso(tmp_path, monkeypatch):
    """Regressão do bug real encontrado em produção: 92% das receitas de
    2016 (140.820 de 153.587) caíram no balaio 'outros' porque a
    classificação lia a coluna 'Fonte recurso' -- que no arquivo real só
    tem DOIS valores possíveis ('Outros Recursos' / 'Fundo Partidario'),
    grosseiro demais -- em vez de 'Tipo receita', que é onde mora a
    categoria detalhada de verdade.

    Este teste reproduz o padrão exato do arquivo real: quatro categorias
    diferentes de receita, todas com 'Fonte recurso' = 'Outros Recursos'
    (constante, sem informação nenhuma para diferenciar), diferenciadas
    SÓ por 'Tipo receita'. Se o código voltar a ler a coluna errada, as
    quatro caem todas em 'outros' e o teste falha.
    """
    from python.ingest import load_to_duckdb as mod

    monkeypatch.setattr(mod, "DIR_RAW", tmp_path)
    monkeypatch.setitem(mod.FORMATO_CONTAS_LEGADO, 2016, {
        "receitas_prefixo": "receitas_candidatos_prestacao_contas_final",
        "despesas_prefixo": "despesas_candidatos_prestacao_contas_final",
        "extensao": "txt",
    })

    cab = [
        "Cód. Eleição", "Desc. Eleição", "Data e hora", "CNPJ Prestador Conta",
        "Sequencial Candidato", "UF", "Sigla da UE", "Nome da UE",
        "Sigla  Partido", "Numero candidato", "Cargo", "Nome candidato",
        "CPF do candidato", "CPF do vice/suplente", "Numero Recibo Eleitoral",
        "Numero do documento", "CPF/CNPJ do doador", "Nome do doador",
        "Nome do doador (Receita Federal)", "Sigla UE doador",
        "Número partido doador", "Número candidato doador",
        "Cod setor econômico do doador", "Setor econômico do doador",
        "Data da receita", "Valor receita", "Tipo receita", "Fonte recurso",
        "Especie recurso", "Descricao da receita",
        "CPF/CNPJ do doador originário", "Nome do doador originário",
        "Tipo doador originário", "Setor econômico do doador originário",
        "Nome do doador originário (Receita Federal)",
    ]

    def _linha(sq, tipo_receita, valor):
        return ["2", "Eleição Municipal 2016", "01/10/2016", "", str(sq),
                "RS", "12345", "MUNICIPIO TESTE", "AAA", "10123",
                "Vereador", "FULANO DE TAL", "11122233344", "", f"REC{sq}",
                f"DOC{sq}", "55566677788", "DOADOR TESTE", "", "", "", "",
                "", "", "15/09/2016", valor, tipo_receita,
                "Outros Recursos",  # <- constante nas quatro linhas, de propósito
                "Dinheiro", "Doação para campanha", "", "", "", "", ""]

    linhas = [
        _linha(101, "Recursos de pessoas físicas", "100,00"),
        _linha(101, "Recursos próprios", "200,00"),
        _linha(101, "Recursos de partido político", "300,00"),
        _linha(101, "Recursos de outros candidatos", "400,00"),
    ]
    _escrever_legado(
        tmp_path / "contas" / "2016" /
        "receitas_candidatos_prestacao_contas_final_2016_RS.txt",
        cab, linhas)

    con = criar_banco(tmp_path / "legado_fonte.duckdb", recriar=True)
    con.execute("""
        INSERT INTO candidatos (sq_candidato, ano_eleicao, turno, cargo, uf,
                                municipio, partido, id_lista, situacao_candidatura)
        VALUES (101, 2016, 1, 'VEREADOR', 'RS', 'MUNICIPIO TESTE', 'AAA', 'AAA', 'APTO')
    """)
    n = mod.carregar_receitas(con, 2016)
    assert n == 4

    fontes = dict(con.execute(
        "SELECT valor, fonte FROM receitas WHERE ano_eleicao = 2016"
    ).fetchall())
    assert fontes[Decimal("100.00")] == "doacao_pf"
    assert fontes[Decimal("200.00")] == "proprio"
    assert fontes[Decimal("300.00")] == "doacao_partido"
    assert fontes[Decimal("400.00")] == "doacao_partido"
    # nenhuma das quatro pode cair em 'outros' -- se cair, é a coluna
    # errada sendo lida de novo
    assert "outros" not in fontes.values()
    con.close()


def test_glob_aceita_extensao_diferente_de_csv(tmp_path, monkeypatch):
    """Trava de regressão para o bug real que causou silêncio no
    --inspecionar: o glob de leitura tinha .csv fixo no código, então um
    ano cujos arquivos são .txt (2016) parecia ter zero arquivos, quando
    na verdade só faltava pedir a extensão certa."""
    from python.ingest.load_to_duckdb import _glob
    padrao_csv = _glob("contas", 2020, "receitas_candidatos")
    padrao_txt = _glob("contas", 2016, "receitas_candidatos_prestacao_contas_final",
                       extensao="txt")
    assert padrao_csv.endswith(".csv")
    assert padrao_txt.endswith(".txt")
