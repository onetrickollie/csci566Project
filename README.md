# TaskFlow-Travel

Imitation-learned coordination for multi-agent travel replanning under evolving user constraints (CSCI 566 project).

A user revises a 3-day itinerary over several turns: they add, delete, or replace constraints, or change their priorities. After each update, a coordinator decides what to do: keep the plan, ask for clarification, refresh a search, repair one component (transport / accommodation / meals / attractions), or regenerate everything. The coordinator is a small neural policy trained from an expert by **behavior cloning**, **trajectory augmentation** and **DAgger**. It is compared against static rules, full regeneration on every update, and the privileged expert itself.

## Start here

| If you want to... | Read / run |
|---|---|
| See it work (2 minutes, no key) | `make setup demo-html` (opens in your browser), `make demo`, `make demo-interactive` |
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
make demo-html             # visual: one episode, every coordinator side by side, in your browser
make demo-html-multi       # visual: a budget cut that needs several components repaired
make demo                  # the same comparison in the terminal
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

## Results

All numbers come from committed `metrics.json` files (offline runs). Each manifest records code, prompt, task and model fingerprints. Models are trained on the v0 train split plus the multi-component train family (`train_multi`), 3 seeds.

### Main benchmark (v0 test split: 276 episodes / 689 turns) — `results/REPORT.md`

| System | Final pass | Revision success | Excess edits / turn | Edit-optimal preservation | LLM calls / turn |
|---|---|---|---|---|---|
| Always-Global (sampled regeneration) | 100.0 | 100.0 | 8.22 | 30.0 | 4.19 |
| Always-Global (deterministic control) | 100.0 | 100.0 | 1.53 | 86.9 | 4.19 |
| Static rules | 100.0 | 100.0 | 1.21 | 89.0 | 0.95 |
| BC | 99.3 | 99.6 ± 0.1 | 1.16 | 89.6 | 0.73 |
| BC + augmentation | 99.9 ± 0.2 | 100.0 ± 0.1 | 1.16 | 89.7 | 0.72 |
| BC + DAgger (3 iters) | 99.9 ± 0.2 | 99.9 ± 0.1 | 1.16 | 89.7 | 0.72 |
| BC + aug + DAgger (3) | 99.5 ± 0.3 | 99.6 ± 0.3 | 1.16 | 89.6 | 0.72 |
| Scripted expert (deterministic) | 100.0 | 100.0 | 1.16 | 89.7 | 0.71 |

**Excess edits** are the slots changed beyond the exact minimum any valid repair needs. **Edit-optimal preservation** is 1 − excess / (13 − minimum). Both are computed by an exact solver after the run (`taskflow/eval/exact.py`), and failed turns get no credit.

### Matched LLM-call budget per turn (`make evaluate-capped`, `results/runs/test-offline-cap*`): revision success %

| Cap | Static rules | BC | BC + aug | BC + DAgger (3) | BC + aug + DAgger (3) | Expert |
|---|---|---|---|---|---|---|
| 1 call | 72.4 | 97.9 | 97.9 | 98.0 | 97.9 | 98.5 |
| 2 calls | 98.1 | 99.6 | 99.9 | 99.9 | 99.6 | 100.0 |

### Multi-component budget cuts (`make evaluate-multi`)

Each episode starts from an expensive itinerary the user already approved, then cuts the budget so that 1, 2, or 3+ components must change. Episodes come from each split's own trips.

**Real-trip family** (`test_multi`: 138 episodes from test trips): every system succeeds.

| System | Excess edits / turn | Global rebuild rate | LLM calls / turn |
|---|---|---|---|
| Always-Global (deterministic) | 5.94 | 100% | 4.00 |
| Static rules | 5.88 | 67% | 3.70 |
| BC + aug + DAgger (3) | 1.91 | 23% | 2.06 |
| Scripted expert | 1.75 | 20% | 1.99 |

**Fixed synthetic stress suite** (12 cases, never trained on; `results/runs/challenges/`):
- The retrained BC+aug+DAgger(3) solves 12/12 cases with every seed.
- Before the multi-component family was added, it solved 4/0/0 cases at the 1/2/3-component levels.

### What the numbers say

1. **Partial vs. global replanning.**
   - Regenerating on every update costs about 5.8× the LLM calls of the learned coordinator.
   - In 49% of turns it rebuilds even though a local repair would have worked.
   - How much of the plan it disturbs depends on how unstable regeneration is: 8.2 unnecessary slot changes per turn with sampled regeneration (our stand-in for an LLM rebuilding from scratch), 1.5 with deterministic regeneration. The real figure needs a real LLM.
2. **When to go global.**
   - On multi-component cuts, the learned coordinator rebuilds globally in about 23% of turns, close to the expert's 20%.
   - Static rules rebuild in 67% of turns, because their script only knows how to repair the accommodation.
   - So the learned coordinator changes about a third as many unneeded slots (1.9 vs 5.9) at roughly half the LLM calls.
3. **Compounding error and recovery.**
   - Forced-mistake recovery (cases where the forced action left the plan broken): BC recovers 88–96%, BC+DAgger(3) 98–100%, and augmentation, with or without DAgger, 100%.
   - Over a whole episode the gap is small on this benchmark: BC handles 98.6% of held-out 4th turns, seed 0.
4. **Against the proposal's rejection criterion.**
   - **Without a call cap:** static rules reach 100% and the learned coordinators 99.6–100%, with about 24% fewer LLM calls.
   - **With 1 call per turn:** the learned coordinators reach about 98%, static rules 72.4%.
   - **On multi-component cuts:** equal success, fewer edits and fewer calls.
   - **Verdict:** offline, the hypothesis holds under a tight budget and on multi-component cuts. It still needs confirming with real LLM agents.

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
