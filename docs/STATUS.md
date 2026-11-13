# Project status

Last updated: 2026-11-13. Task IDs refer to the task board in [ENGINEERING_PLAN.md](ENGINEERING_PLAN.md).

**Review status** (details in [SUPERVISOR_REVIEW.md](SUPERVISOR_REVIEW.md) and [review/LATEST_PROGRESS_REVIEW.md](review/LATEST_PROGRESS_REVIEW.md)):
- **Independently verified:**
  - All datasets rebuild byte for byte, and all 18 models retrain to identical weights.
  - Every evaluation reproduces exactly.
  - All 3,667 feasibility labels (v0 and multi family) agree with an exact solver.
  - All 3,054 passing expert plans pass the adapted upstream TravelPlanner checks. These are the upstream check functions run on per-query data slices, not the official CLI or full database. A few substring-name cost differences remain and are documented in `LICENSES.md`.
- **Fixed in response to the latest review:** R1–R5 (app route realism, how asks are scored, input validation, return-leg display, recovery start plan), each with a regression test.
- **Open:** H4 (live LLM run), owned by teammates.
- **For prompt work:** use validation episodes and keep test frozen.

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
| Demo | Scripted and interactive (terminal), visual replay (`demo_html.py`), and an interactive web app with any start city and destination (`app.py`) | `scripts/` | `tests/test_app.py` |

## Implemented but caveated (`done*` / `partial`)

| Item | Caveat | What to do |
|---|---|---|
| LLM tracker, LLM agents, LLM coordinator/teacher | Only tested with the fake backend. Prompts are first drafts. | Run with a real model on ~30 episodes, read the transcripts in `cache/llm/`, iterate on `taskflow/llm/prompts.py`. |
| Cost numbers in `results/REPORT.md` | Offline numbers come from the simulated cost model (`ACTION_COST` in `taskflow/env/state.py`). | Re-run `evaluate.py --llm ...`; report the "Measured" columns instead. |
| Feasibility labels | "Feasible" means the current plan already works or the greedy planner finds one. All 3,667 labels agree with an exact solver under the all-13-slots completeness rule. | Keep the exact check in the review tooling when the task schema changes. |
| Local vs. global | The v0 tasks never require a rebuild. In the multi-component family (one-turn budget cuts from an approved expensive itinerary), the expert now searches repairs of up to three components, so no cut needs a global rebuild. Difficulty levels are chosen with the same expert, so results measure imitation of its decision boundary. The cost-aware static baseline is close: the learned coordinator is about 20% better on excess edits with the same success and calls. The 12-case synthetic stress suite has been inspected repeatedly, so it's a regression check, not an untouched holdout. | Add non-budget multi-component updates and multi-turn sequences, developed on train/val, with a frozen new test set. |
| Scripted expert | Restricted to deterministic planners and refuses to run in LLM mode; not an optimality bound (bounded local search, greedy planners). | — |
| Action mask | The learned coordinator may not repeat the previous re-plan/search back to back. That's harmless with deterministic planners (the expert never does it), but LLM or sampled re-plans aren't idempotent, so retries could help there. | Revisit during H4. |
| Held-out phrasing | Template set B and the rule-based tracker were written together, so 100% tracker accuracy proves little. | Paraphrase test updates with an LLM and re-score the tracker (T10). |
| Always-Global preservation | Sampled regeneration keeps 31% of untouched slots, the deterministic control 93%. The instability is simulated. | Measure with a real LLM regenerating the plan. |
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
| — | Final report, slides, recorded demo | everyone | Week 12. |

## Suggested order for the next week

1. **Everyone:** run `make setup demo test` and read [ARCHITECTURE.md](ARCHITECTURE.md).
2. **Agents:** get one real provider working (`docs/LLM_SETUP.md`). Run `make demo-llm`, then `make evaluate-llm` (30 *validation* episodes), and fix the prompts. Check the report's fallback table; a DEGRADED run isn't an LLM result.
3. **Bench:** new multi-component update types (non-budget) and multi-turn sequences, with a frozen new test set.
4. **Learning:** train with `--teacher llm --limit 100` and compare against the oracle-taught models.
5. **Eval:** CI; report per-level results against both static baselines (`static_rules`, `static_cost_aware`).
