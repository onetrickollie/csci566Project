PY := .venv/bin/python

.PHONY: help setup demo demo-interactive demo-llm demo-fake test pipeline dataset train evaluate evaluate-llm snapshot clean-cache

help:
	@echo "make setup             create .venv and install requirements"
	@echo "make demo              scripted multi-turn demo (offline)"
	@echo "make demo-interactive  type your own updates"
	@echo "make demo-fake         exercise every LLM code path offline"
	@echo "make demo-llm          demo with the provider configured in .env"
	@echo "make test              run the test suite (offline, no key needed)"
	@echo "make pipeline          dataset -> train (3 seeds) -> evaluate, ~3 min on CPU"
	@echo "make evaluate-llm      evaluate 30 test episodes with the configured provider"
	@echo "make snapshot          bundle docs + source into project_snapshot.md"

setup:
	python3 -m venv .venv
	$(PY) -m pip install -q -r requirements.txt
	@test -f .env || cp .env.example .env
	@echo "ready: try 'make demo'"

demo:
	$(PY) scripts/demo.py

demo-interactive:
	$(PY) scripts/demo.py --interactive

demo-fake:
	$(PY) scripts/demo.py --llm fake --policy llm_coordinator

demo-llm:
	$(PY) scripts/demo.py --policy llm_coordinator

test:
	$(PY) -m pytest -q

dataset:
	$(PY) scripts/build_dataset.py --seed 0

train:
	$(PY) scripts/train.py --seeds 0 1 2

evaluate:
	$(PY) scripts/evaluate.py --seeds 0 1 2

pipeline: dataset train evaluate

evaluate-llm:
	$(PY) scripts/evaluate.py --limit 30 --seeds 0 --skip-recovery

snapshot:
	$(PY) scripts/make_snapshot.py

clean-cache:
	rm -rf cache/llm
