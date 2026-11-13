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
make evaluate-llm          # 30 test episodes -> results/llm-<provider>/REPORT.md
```

`make demo-fake` runs every LLM code path offline with a stand-in backend. Details are in [docs/LLM_SETUP.md](docs/LLM_SETUP.md).

## What is in the box

| Piece | Where | Notes |
|---|---|---|
| TravelPlanner loader | `taskflow/data/travelplanner.py` | Parses each query's database slice (flights, ground transport, hotels, restaurants, attractions). |
| Verifier | `taskflow/env/verifier.py` | TravelPlanner-style commonsense and hard constraints, plus restaurant rating floor and cost/quality priority. Each violation names the slots that cause it. Accepts all 15 annotated single-city reference plans (`tests/test_verifier.py`). |
| Evolving-constraint tasks | `taskflow/data/tasks.py` | Split by original query id **before** variants are generated. Four update types. About 75% of feasible updates break the current plan; about 17% are infeasible (correct response: ask). |
| Constraint tracker | `taskflow/agents/tracker.py` | Natural-language update to a structured diff. Rule-based offline (100% on both template sets); LLM-based when a provider is set, with schema validation and fallback. |
| Component planners + composer | `taskflow/agents/planners.py`, `llm_planners.py` | Local repair keeps the other components fixed; global regeneration rebuilds from scratch. With an LLM, agents choose from validated shortlists. |
| Multi-turn environment | `taskflow/env/episode.py` | Cached searches go stale when a relevant constraint changes; per-action cost accounting. |
| Coordinators | `taskflow/coordinators/` | `oracle` (privileged expert), `static_rules`, `always_global`, `llm_coordinator` (also the LLM teacher for DAgger). |
| LLM layer | `taskflow/llm/` | One client for offline / fake / OpenAI-compatible / Anthropic, with disk cache, retries and usage counters. All prompts live in `prompts.py`. |
| Learned coordinator | `taskflow/learning/` | MLP over a non-privileged observation (`encode.py`), trained with BC / augmentation / DAgger (`imitation.py`). |
| Evaluation | `scripts/evaluate.py`, `taskflow/eval/` | Proposal metrics, breakdowns, forced-mistake recovery, error vs. step. |

### Held-out test conditions

The test split differs from training in three ways:
- **Unseen trips:** different original queries.
- **Unseen phrasing:** a different template set for the natural-language updates.
- **Longer chains:** 4-turn conversations, while training never goes past 3 turns.

## Results (test split, 292 episodes / 741 turns, 3 training seeds)

| System | Final pass | Revision success | Unaffected slots preserved | LLM calls / turn |
|---|---|---|---|---|
| Always-Global | 99.7 | 99.9 | 33.0 | 4.17 |
| Static rules | 100.0 | 100.0 | 95.1 | 1.63 |
| BC | 97.1 ± 0.3 | 98.4 ± 0.1 | 96.1 | 0.71 |
| BC + augmentation | 99.0 ± 0.3 | 99.3 ± 0.2 | 96.1 | 0.71 |
| BC + DAgger (3 iters) | 98.2 ± 0.9 | 98.9 ± 0.5 | 96.1 | 0.71 |
| BC + aug + DAgger (3) | 99.2 ± 0.6 | 99.5 ± 0.2 | 96.0 | 0.71 |
| Privileged oracle | 100.0 | 100.0 | 96.0 | 0.69 |

What the numbers say:

1. **Partial vs. global replanning.** Regenerating on every update keeps only a third of the parts of the itinerary that the update didn't touch, and costs about 6× the LLM calls of a learned coordinator. In 48% of turns it regenerates even though a local repair would have worked.
2. **Compounding error is real, and both mitigations help.**
   - Plain BC succeeds on 100% of first turns but only 91.9% of held-out 4th turns (seed 0). Augmentation or DAgger lifts the 4th turn to 96.5%.
   - When a mistake is forced at the start of a turn, BC recovers 86% of the time after a wrong accommodation repair. With augmentation it recovers 100%.
   - DAgger alone is noisy on forced mistakes (71–96% recovery for 3 iterations, depending on the mistake), because it only relabels states the policy visits on its own. Augmentation targets mistake states directly. The combination is best overall.
3. **Against the proposal's rejection criterion.**
   - **Efficiency:** the learned coordinator matches the oracle (0.71 vs 0.69 LLM calls per turn) and uses about 2.3× fewer calls than static rules.
   - **Accuracy:** it does *not* beat static rules. Static rules fall back to full regeneration when their script fails, so they always succeed eventually, and the learned coordinator trails them by 0.5 points of revision success.
   - **Verdict:** under a matched call budget the hypothesis is not yet established. This is the main open question for the LLM-backed version.

## Deviations from the plan (read before citing numbers)

- **Offline numbers.** The results above were produced offline:
  - The sub-agents are deterministic searches, the tracker is rule-based, and update phrasings come from templates.
  - The expert is the privileged scripted oracle.
  - Per-action LLM calls and tokens come from a fixed **cost model** (`ACTION_COST` in `taskflow/env/state.py`).
  - The LLM tracker, LLM agents, LLM coordinator and LLM teacher are implemented and tested with the offline `fake` backend, but **not yet run against a real model**.
  - The single-LLM-agent baseline isn't built yet.
- **Scope:** 3-day, single-city TravelPlanner queries only, and FlexTravelBench is not used yet.
  - Train and validation queries keep their original constraints.
  - Test-file queries have hidden constraints, so their starting budget and constraints are sampled: budget is 1.2–1.7× the cheapest plan.
- **"Feasible" means feasible for our planners:** the current plan already satisfies the update, or the greedy composer can find a plan.
- **Simulated instability in global regeneration.** Global regeneration samples among near-best options, to mimic the instability of an LLM rebuilding a plan from scratch. The 33% preservation for Always-Global depends on this choice.
- **No TravelPlanner leaderboard comparison.** Splits are re-drawn, so numbers aren't comparable with the official leaderboard. The verifier is checked against annotated plans, not against the official evaluator script.
- **Tooling:** dataclasses instead of pydantic, and pip + `requirements.txt` instead of uv. There's no CI.

## Next steps

See [docs/STATUS.md](docs/STATUS.md) for the full list with suggested owners. In short:
1. Run with a real model and replace the simulated cost with measured cost.
2. Build the single-agent LLM baseline.
3. Settle the validity questions in the checklist.
4. Extend to LLM paraphrases, FlexTravelBench and multi-city trips.
5. Package the dataset and the verifier for release.
