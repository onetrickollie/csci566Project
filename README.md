# TaskFlow-Travel

Imitation-learned coordination for multi-agent travel replanning under evolving user constraints (CSCI 566 project).

A user revises a 3-day itinerary over several turns: they add, delete, or replace constraints, or change their priorities. After each update, a coordinator decides what to do: keep the plan, ask for clarification, refresh a search, repair one component (transport / accommodation / meals / attractions), or regenerate everything. The coordinator is a small neural policy trained from an expert by **behavior cloning**, **trajectory augmentation** and **DAgger**. It is compared against static rules, full regeneration on every update, and the privileged expert itself.

## Start here

| If you want to... | Read / run |
|---|---|
| See it work (2 minutes, no key) | `make setup demo`, then `make demo-interactive` |
| Know what's done and what's left | [docs/STATUS.md](docs/STATUS.md) |
| Understand the code | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Plug in an API key | [docs/LLM_SETUP.md](docs/LLM_SETUP.md) |
| Check the parts we're unsure about | [docs/VERIFICATION_CHECKLIST.md](docs/VERIFICATION_CHECKLIST.md) |
| See interfaces, task IDs, and owners | [docs/ENGINEERING_PLAN.md](docs/ENGINEERING_PLAN.md) |
| See the latest numbers | [results/REPORT.md](results/REPORT.md) |
| Share the whole project as one file | `make snapshot` → `project_snapshot.md` (docs + all source, ~170 KB) |
| Read the proposal | [docs/TaskFlow_Travel_PreProposal.pdf](docs/TaskFlow_Travel_PreProposal.pdf) |

## Quickstart

```bash
make setup                 # .venv + requirements + .env from .env.example
make demo                  # scripted 4-turn episode, compares all coordinators
make demo-interactive      # type your own updates
make test                  # offline test suite
make pipeline              # rebuild tasks, retrain (3 seeds), re-evaluate: ~3 min on CPU
```

Without `make`, use the Python commands directly: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`, then `.venv/bin/python scripts/demo.py`.

- **First run:** downloads the public TravelPlanner files (~37 MB) into `data/raw/`.
- **No retraining needed for the demo:** trained models (`models/`) and the generated task set (`data/tasks/v0/`) are committed.

### With an API key

Everything above works offline. To switch on the LLM-backed tracker, component agents and coordinator, and to get measured cost:

```bash
cp .env.example .env       # set TASKFLOW_LLM_PROVIDER, TASKFLOW_LLM_MODEL and a key
make demo-llm              # LLM coordinator + LLM agents
make evaluate-llm          # 30 validation episodes -> results/runs/<run>/REPORT.md
```

`make demo-fake` runs every LLM code path offline with a stand-in backend. Details are in [docs/LLM_SETUP.md](docs/LLM_SETUP.md).

## What is in the box

| Piece | Where | Notes |
|---|---|---|
| TravelPlanner loader | `taskflow/data/travelplanner.py` | Parses each query's database slice (flights, ground transport, hotels, restaurants, attractions). Detects the optional index column from layout, so names that start with digits survive; a name always identifies one record (first occurrence, as upstream resolves it). |
| Verifier | `taskflow/env/verifier.py` | TravelPlanner-style commonsense and hard constraints, plus restaurant rating floor and cost/quality priority. A valid itinerary fills all 13 slots (stricter than upstream). Each violation names the slots that cause it. Accepts all 15 annotated single-city reference plans when the completeness rule is relaxed (`tests/test_verifier.py`). |
| Evolving-constraint tasks | `taskflow/data/tasks.py` | Split by original query id **before** variants are generated. Four update types. On the test split, 63% of feasible updates break the plan the reference coordinator holds (generator target 75%), and 19% of turns are infeasible (correct response: ask). |
| Constraint tracker | `taskflow/agents/tracker.py` | Natural-language update to a structured diff. Rule-based offline; LLM-based when a provider is set, with a strict op/type schema, an explicit "no change" result, and rule fallback only for unusable replies. |
| Component planners + composer | `taskflow/agents/planners.py`, `llm_planners.py` | Local repair keeps the other components fixed; global regeneration rebuilds from scratch. With an LLM, agents choose from validated shortlists. |
| Multi-turn environment | `taskflow/env/episode.py` | Cached searches go stale when a relevant constraint changes. The system carries its own constraint belief between turns; ground truth is used only for scoring. Optional per-turn LLM-call cap for matched-budget runs. |
| Coordinators | `taskflow/coordinators/` | `oracle` (privileged expert), `static_rules` (asks on observable evidence), `always_global` and its deterministic control `always_global_det`, `llm_coordinator` (also the LLM teacher for DAgger). |
| LLM layer | `taskflow/llm/` | One client for offline / fake / OpenAI-compatible / Anthropic. Endpoint-aware disk cache, retries, usage and per-component fallback counters; bad keys/models/endpoints abort instead of silently falling back. All prompts live in `prompts.py`. |
| Learned coordinator | `taskflow/learning/` | MLP over a non-privileged observation (`encode.py`), trained with BC / augmentation / DAgger (`imitation.py`). |
| Evaluation | `scripts/evaluate.py`, `taskflow/eval/` | Proposal metrics, breakdowns, forced-mistake recovery, error vs. step. |

### Held-out test conditions

The test split differs from training in three ways:
- **Unseen trips:** different original queries.
- **Different phrasing templates:** a second handwritten template set. The rule-based tracker was written with both sets in view, so this checks template compatibility, not robustness to real paraphrases (that needs T10).
- **Longer chains:** 4-turn conversations, while training never goes past 3 turns.

## Results (test split, 276 episodes / 689 turns, 3 training seeds)

All numbers come from `results/metrics.json` (offline run; manifest records code, prompt, task and model fingerprints).

| System | Final pass | Revision success | Unaffected slots preserved | Slots edited | LLM calls / turn |
|---|---|---|---|---|---|
| Always-Global (sampled regeneration) | 100.0 | 100.0 | 31.3 | 73.1 | 4.19 |
| Always-Global (deterministic control) | 100.0 | 100.0 | 93.1 | 21.2 | 4.19 |
| Static rules | 100.0 | 100.0 | 95.4 | 18.9 | 0.95 |
| BC | 97.5 ± 1.5 | 98.6 ± 0.8 | 96.3 | 18.1 | 0.73 |
| BC + augmentation | 99.9 ± 0.2 | 100.0 ± 0.1 | 96.1 | 18.6 | 0.72 |
| BC + DAgger (3 iters) | 99.9 ± 0.2 | 100.0 ± 0.1 | 96.1 | 18.6 | 0.72 |
| BC + aug + DAgger (3) | 99.9 ± 0.2 | 100.0 ± 0.1 | 96.1 | 18.6 | 0.72 |
| Privileged oracle | 100.0 | 100.0 | 96.1 | 18.6 | 0.71 |

**Matched LLM-call budget per turn** (`make evaluate-capped`, `results/runs/test-offline-cap*`): revision success %.

| Cap | Static rules | BC | BC + aug | BC + DAgger (3) | BC + aug + DAgger (3) | Oracle |
|---|---|---|---|---|---|---|
| 1 call | 72.4 | 96.9 | 98.0 | 98.0 | 97.6 | 98.5 |
| 2 calls | 98.1 | 98.5 | 100.0 | 100.0 | 99.9 | 100.0 |

What the numbers say:

1. **Partial vs. global replanning.**
   - Regenerating on every update costs about 4.4× the LLM calls of static rules and 5.8× those of the learned coordinator. In 49% of turns it regenerates even though a local repair would have worked.
   - How much of the plan regeneration destroys depends on how unstable regeneration is. With sampled regeneration (our stand-in for an LLM rebuilding from scratch) it keeps 31% of the untouched slots. Deterministic regeneration keeps 93%. The real figure needs a real LLM.
2. **Compounding error.**
   - Plain BC succeeds on 100% of first turns but only 92.8% of held-out 4th turns (seed 0). Augmentation and DAgger both bring the 4th turn back to 98.6–100%.
   - In forced-mistake recovery, counting only cases where the forced action actually left the plan broken: BC recovers 83–88%, BC+DAgger(3) 91–99%, and augmentation, with or without DAgger, 100%.
   - A forced global rebuild always fixes the plan, so it says nothing about recovery.
3. **Against the proposal's rejection criterion.**
   - **Without a budget cap:** static rules reach 100% and the learned coordinator 99.9–100%. The learned coordinator uses about 24% fewer LLM calls (0.72 vs 0.95).
   - **With 1 call per turn:** the learned coordinators reach 96.9–98.1% revision success, while static rules drop to 72.4%.
   - **Verdict:** offline, the hypothesis holds under a tight budget, not without one. It still needs confirming with real LLM agents.
4. **Scope of the local/global question.** On this task distribution the oracle never needs a global rebuild (every feasible update is fixed by repairing one or two components). The results show *when to repair locally and when to ask*, not a learned local-vs-global trade-off. Independent multi-component scenarios are open work (`docs/STATUS.md`).

## Deviations from the plan (read before citing numbers)

- **Offline numbers.** The results above were produced offline:
  - The sub-agents are deterministic searches, the tracker is rule-based, and update phrasings come from templates.
  - The expert is the privileged scripted oracle.
  - Per-action LLM calls and tokens come from a fixed **cost model** (`ACTION_COST` in `taskflow/env/state.py`).
  - The LLM tracker, LLM agents, LLM coordinator and LLM teacher are implemented and tested with the offline `fake` backend and adversarial stubs, but **not yet run against a real model**.
  - The single-LLM-agent baseline isn't built yet.
- **Scope:** 3-day, single-city TravelPlanner queries only, and FlexTravelBench is not used yet.
  - Train and validation queries keep their original constraints.
  - Test-file queries have hidden constraints, so their starting budget and constraints are sampled: budget is 1.2–1.7× the cheapest plan.
- **"Feasible" means feasible for our planners:** the current plan already satisfies the update, or the greedy composer can find a plan. Under the all-13-slots completeness rule, a review's exact search found no turn wrongly labeled infeasible; this needs re-checking after the parser fixes.
- **Simulated instability in global regeneration.** Global regeneration samples among near-best options, to mimic the instability of an LLM rebuilding a plan from scratch. The deterministic control (`always_global_det`) shows how much the preservation number depends on that choice: 31% vs. 93%.
- **No TravelPlanner leaderboard comparison.** Splits are re-drawn, so numbers aren't comparable with the official leaderboard. The verifier is checked against annotated plans, not against the official evaluator script.
- **Tooling:** dataclasses instead of pydantic, and pip + `requirements.txt` instead of uv. There's no CI.

## Next steps

See [docs/STATUS.md](docs/STATUS.md) for the full list with suggested owners. In short:
1. Run with a real model and replace the simulated cost with measured cost.
2. Build the single-agent LLM baseline.
3. Settle the validity questions in the checklist.
4. Extend to LLM paraphrases, FlexTravelBench and multi-city trips.
5. Package the dataset and the verifier for release.
