# Project status

Last updated: 2026-11-13. Task IDs refer to the task board in [ENGINEERING_PLAN.md](ENGINEERING_PLAN.md).

## TL;DR

- **The whole pipeline runs today without an API key:** data → tasks → planners → coordinators → training → evaluation → demo.
- **Every LLM component is implemented behind one switch,** `TASKFLOW_LLM_PROVIDER`. When no key is set, each one falls back to a deterministic version, so nothing breaks offline.
- **The LLM paths have only been exercised with the offline `fake` backend.** No real model has been run yet.
- **The most important remaining work:**
  1. Run the system with a real model.
  2. Measure real cost.
  3. Add the single-agent LLM baseline.
  4. Settle the open validity questions in [VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md).

## Done

| Area | What works | Where | Evidence |
|---|---|---|---|
| Data (T02) | TravelPlanner download and parsing of each query's database slice; 383 three-day single-city queries | `taskflow/data/travelplanner.py` | `tests/test_verifier.py` |
| Verifier (T05) | Commonsense + hard constraints + rating floor + priority; each violation names the slots that cause it | `taskflow/env/verifier.py` | Accepts all 15 annotated reference plans |
| Tasks (T07–T09) | Query-level splits; add/delete/replace/reprioritize chains; feasibility labels; held-out test conditions | `taskflow/data/tasks.py`, `data/tasks/v0/` | `tests/test_pipeline.py` |
| Tracker | Rule-based parser (100% on both template sets) + LLM parser with schema validation and fallback | `taskflow/agents/tracker.py` | `tests/test_pipeline.py`, `tests/test_llm.py` |
| Component agents (T12) | Deterministic planners + LLM agents choosing from shortlists, validated, with fallback | `taskflow/agents/planners.py`, `llm_planners.py` | `tests/test_llm.py` |
| Environment (T11) | Multi-turn runner, stale-cache semantics, cost-model accounting, measured LLM usage | `taskflow/env/episode.py` | deterministic replay test |
| Coordinators (T13–T15) | Privileged oracle, static rules, always-global, LLM coordinator (also usable as the LLM teacher) | `taskflow/coordinators/` | `tests/` |
| Learning (T16–T18) | MLP coordinator; BC, trajectory augmentation, DAgger with oracle or LLM teacher | `taskflow/learning/`, `scripts/train.py` | `models/training_log.json` |
| Evaluation (T19–T21) | Proposal metrics, breakdowns, forced-mistake recovery, error vs step, figures; offline and LLM modes | `scripts/evaluate.py`, `taskflow/eval/` | `results/REPORT.md` |
| LLM client (T06) | Offline / fake / OpenAI-compatible / Anthropic; disk cache; retries; usage counters; `.env` support | `taskflow/llm/` | `tests/test_llm.py` |
| Demo | Scripted and interactive, offline or with any backend | `scripts/demo.py` | run it |

## Implemented but caveated (`done*` / `partial`)

| Item | Caveat | What to do |
|---|---|---|
| LLM tracker, LLM agents, LLM coordinator/teacher | Only tested with the fake backend. Prompts are first drafts. | Run with a real model on ~30 episodes, read the transcripts in `cache/llm/`, iterate on `taskflow/llm/prompts.py`. |
| Cost numbers in `results/REPORT.md` | Offline numbers come from the simulated cost model (`ACTION_COST` in `taskflow/env/state.py`). | Re-run `evaluate.py --llm ...`; report the "Measured" columns instead. |
| Feasibility labels | "Feasible" means the current plan already works or the greedy planner finds one. The greedy planner can miss plans that exist. | Exhaustive or ILP check on a sample (checklist item 4). |
| Held-out phrasing | Template set B and the rule-based tracker were written together, so 100% tracker accuracy proves little. | Paraphrase test updates with an LLM and re-score the tracker (T10). |
| Always-Global preservation (33%) | Offline instability of full regeneration is simulated by sampling. | Measure it with a real LLM regenerating the plan. |
| Test-split constraints | TravelPlanner hides test constraints, so starting budgets and constraints for those queries are sampled. | Fine for our benchmark; state it in the report. |

## Not started

| ID | Task | Suggested owner | Notes |
|---|---|---|---|
| — | **Single-agent LLM baseline** | agents | One LLM call per turn sees the full conversation and all candidates and outputs the whole plan as JSON. Add `coordinators/single_agent.py` and a `REPLAN_SINGLE` path, or a planner that bypasses the coordinator. |
| T10 | LLM paraphrases with back-verification | bench | Generate phrasings for test updates, keep a phrasing only if the tracker recovers the structured diff. |
| — | FlexTravelBench | bench | Loader plus base constraints; check its license first. |
| — | Multi-city trips (5- and 7-day TravelPlanner queries) | bench + agents | City order comes from the flights in the reference info; plan slots need to go per day. |
| T03 | JSON Schema export of the interfaces | bench | dataclasses → `schemas/*.json`. |
| T01 | CI | eval | GitHub Actions: `pip install -r requirements.txt && pytest -q` (offline, no key needed). |
| T22 | Release package | bench | Dataset card + datasheet for `data/tasks/`, pip-installable harness. |
| — | Matched-budget comparison | eval | Cap LLM calls per turn (e.g. 1 and 2) and compare static rules vs. learned (proposal's rejection criterion). |
| — | Final report, slides, recorded demo | everyone | Week 12. |

## Suggested order for the next week

1. **Everyone:** run `make setup demo test` and read [ARCHITECTURE.md](ARCHITECTURE.md).
2. **Agents:** get one real provider working (`docs/LLM_SETUP.md`). Run `make demo-llm`, then `evaluate.py --llm <provider> --limit 30 --seeds 0 --skip-recovery`, and fix the prompts.
3. **Bench:** checklist items 2–4 (parser, verifier against the official evaluator, feasibility labels).
4. **Learning:** train with `--teacher llm --limit 100` and compare against the oracle-taught models.
5. **Eval:** the matched-budget comparison and CI.
