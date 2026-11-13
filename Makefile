PY := .venv/bin/python

.PHONY: help setup app demo demo-html demo-html-multi demo-interactive demo-llm demo-fake test pipeline dataset train evaluate evaluate-llm evaluate-capped evaluate-multi snapshot clean-cache

help:
	@echo "make setup             create .venv and install requirements"
	@echo "make demo              scripted multi-turn demo (offline)"
	@echo "make demo-interactive  type your own updates"
	@echo "make app               interactive web app: type any start city + destination, then revise"
	@echo "make demo-html         visual replay of a test episode (all coordinators side by side)"
	@echo "make demo-html-multi   visual demo of a budget cut that needs several repairs"
	@echo "make demo-fake         exercise every LLM code path offline"
	@echo "make demo-llm          demo with the provider configured in .env"
	@echo "make test              run the test suite (offline, no key needed)"
	@echo "make pipeline          dataset -> train (3 seeds) -> evaluate, ~3 min on CPU"
	@echo "make evaluate          full offline test evaluation -> results/ (canonical)"
	@echo "make evaluate-llm      30 validation episodes with the configured provider -> results/runs/"
	@echo "make evaluate-capped   matched-budget runs (1 and 2 LLM calls per turn) -> results/runs/"
	@echo "make evaluate-multi    multi-component test family + fixed synthetic stress suite"
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

app:
	$(PY) scripts/app.py

demo-html:
	$(PY) scripts/demo_html.py

demo-html-multi:
	$(PY) scripts/demo_html.py --split test_multi

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
	$(PY) scripts/evaluate.py --canonical --seeds 0 1 2

evaluate-multi:
	$(PY) scripts/evaluate.py --split test_multi --seeds 0 1 2 --skip-recovery --out results/runs/test-multi
	$(PY) scripts/evaluate_challenges.py --seed 0 --seeds 0 1 2 --out results/runs/challenges/challenges.json

pipeline: dataset train evaluate evaluate-capped evaluate-multi

evaluate-llm:
	$(PY) scripts/evaluate.py --require-llm --split val --limit 30 --seeds 0 --skip-recovery

evaluate-capped:
	$(PY) scripts/evaluate.py --call-cap 1 --seeds 0 1 2
	$(PY) scripts/evaluate.py --call-cap 2 --seeds 0 1 2

snapshot:
	$(PY) scripts/make_snapshot.py

clean-cache:
	rm -rf cache/llm
