ANOS  ?= 2020 2024
UF    ?= RS
CARGO ?= VEREADOR
BANCO ?= data/db/financiamento.duckdb
DE    ?= 2020
PARA  ?= 2024

.PHONY: help demo inspecionar dados banco painel analise test limpar

help:
	@echo "make demo                      pipeline completo em dados sintéticos (~1 min)"
	@echo "make inspecionar ANOS='2024'   baixa e imprime os cabeçalhos dos CSVs do TSE"
	@echo "make dados   ANOS='2020 2024'  baixa e extrai os CSVs (UF=$(UF))"
	@echo "make banco   ANOS='2020 2024'  popula o DuckDB e valida os totais"
	@echo "make painel  DE=2020 PARA=2024 liga a mesma pessoa entre as eleições"
	@echo "make analise                   descritiva + RDD + robustez + figuras"
	@echo "make test                      suíte de testes"
	@echo "make limpar                    apaga banco e saídas regeneráveis"

demo:
	python -m python.run_pipeline --sintetico

inspecionar:
	python -m python.ingest.download_tse --anos $(ANOS) --uf $(UF) --inspecionar

dados:
	python -m python.ingest.download_tse --anos $(ANOS) --uf $(UF)

banco:
	python -m python.ingest.load_to_duckdb --anos $(ANOS) --uf $(UF) \
		--cargo $(CARGO) --banco $(BANCO) --recriar

painel:
	python -m python.analysis.build_panel --de $(DE) --para $(PARA) --banco $(BANCO)

analise:
	python -m python.run_pipeline --banco $(BANCO)

test:
	python -m pytest -q

limpar:
	rm -rf data/db/*.duckdb outputs/tabelas/*.csv outputs/*.json
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
