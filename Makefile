PY ?= python
.PHONY: setup test sample run large benchmark reconcile clean
setup:
	$(PY) -m pip install -r requirements.txt
test:
	$(PY) -m pytest -q
sample:
	$(PY) -m yottaflex_de generate --out data/sample --labels data/sample_labels --orders 1000 --seed 42
run:
	$(PY) -m yottaflex_de run --input data/sample --db output/warehouse.duckdb
large:
	$(PY) -m yottaflex_de generate --out data/large --labels data/large_labels --orders 200000 --seed 7
	$(PY) -m yottaflex_de run --input data/large --db output/large.duckdb
reconcile:
	$(PY) -m yottaflex_de reconcile --db output/large.duckdb --labels data/large_labels/expected_rejects.json --out reports/reconciliation.md
benchmark:
	$(PY) -m yottaflex_de benchmark --db output/large.duckdb --out reports/benchmark.md
clean:
	rm -rf output .pytest_cache
