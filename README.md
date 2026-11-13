# TaskFlow-Travel

Imitation-learned coordination for multi-agent travel replanning under evolving user constraints (CSCI 566 project).

A user revises a 3-day itinerary over several turns: they add, delete, or replace constraints, or change their priorities. After each update, a coordinator decides what to do: keep the plan, ask for clarification, refresh a search, repair one component (transport / accommodation / meals / attractions), or regenerate everything. The coordinator is a small neural policy trained from an expert by **behavior cloning**, **trajectory augmentation** and **DAgger**. It is compared against static rules, full regeneration on every update, and the privileged expert itself.

## Start here

| If you want to... | Read / run |
|---|---|
| **Join the project and keep working** | [HANDOFF.md](HANDOFF.md): everything done so far, what's left, how to run it, team rules |
| Try it yourself (no key) | `make setup app`: type a start city and destination, get an itinerary, then revise it in plain language |
| Watch a recorded test episode | `make demo-html` (browser), `make demo` (terminal) |
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
make app                   # interactive web app at http://localhost:8566 (see below)
make demo-html             # visual: one test episode, every coordinator side by side, in your browser
make demo-html-multi       # visual: a budget cut that needs several components repaired
make demo                  # the same comparison in the terminal
make demo-interactive      # type your own updates
make test                  # offline test suite
make pipeline              # rebuild tasks, retrain (3 seeds), re-evaluate: ~3 min on CPU
```

Without `make`, use the Python commands directly: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`, then `.venv/bin/python scripts/demo.py`.

- **First run:** downloads the public TravelPlanner files (~37 MB) into `data/raw/`.
- **No retraining needed for the demo:** trained models (`models/`) and the generated task set (`data/tasks/v0/`) are committed.

### The interactive app (`make app`)

1. **Plan a trip.** Type a start city and a destination; typos get "did you mean" suggestions. Pick a start date in March 2022, the number of travelers, a budget and any requirements (room type, house rule, cuisines, transport). The app builds a 3-day itinerary.
2. **Change your mind.** Type a change, or click a suggestion. Four coordinators handle it, each on its own copy of the trip, and their answers appear side by side: always-regenerate, static rules, the learned coordinator, and the scripted expert (or the LLM coordinator when an API key is set). Each card shows the actions taken, the changed slots, cost, validity, and running totals.

What the data supports:
- **Cities:** 257 start cities and 220 destinations (every city in TravelPlanner).
- **Flights:** only where the TravelPlanner data has them, which is March 2022 and the routes its queries used. The app shows which start dates have flights for your route.
- **Driving and taxi:** recorded options are used where they exist. Other routes are **estimated** from the distance between the cities, using per-km rates fitted to the data, and labelled as estimated in the app.
- **Realism rules (app only):**
  - No driving estimates across water: both cities must be in the contiguous US.
  - No driving or taxi leg longer than 12 hours, since the trip is three days.
  - Routes that fail both flights and driving are refused with the reason and a list of destinations that do work from your start city (e.g. Los Angeles → Honolulu, New York → Seattle).
- **Clarification:** a coordinator that asks keeps your previous plan. The app scores the ask as correct only if an independent check confirms the change couldn't be met.
- **Typing:** offline, the tracker understands phrasings like the suggestions. With an LLM backend it understands free-form messages.

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

All numbers come from committed `metrics.json` files (offline runs). Each manifest records code, prompt, task and model fingerprints. Models are trained on the v0 train split plus the multi-component train family (`train_multi`), 3 seeds. The scripted expert searches repairs of up to three components before rebuilding.

There are two static baselines:
- **Static rules:** a fixed script per update type, with one global fallback.
- **Static rules (cost-aware):** asks at once when the cheapest options can't fit the budget; otherwise repairs components in order of how much each could save, verifying after each. Added after review as the stronger baseline.

### Main benchmark (v0 test split: 276 episodes / 689 turns) — `results/REPORT.md`

| System | Final pass | Revision success | Excess edits / turn | Edit-optimal preservation | LLM calls / turn |
|---|---|---|---|---|---|
| Always-Global (sampled regeneration) | 100.0 | 100.0 | 8.22 | 30.0 | 4.19 |
| Always-Global (deterministic control) | 100.0 | 100.0 | 1.52 | 86.9 | 4.19 |
| Static rules | 100.0 | 100.0 | 1.21 | 89.0 | 0.95 |
| Static rules (cost-aware) | 100.0 | 100.0 | 1.16 | 89.7 | 0.84 |
| BC | 99.4 ± 0.3 | 99.7 ± 0.2 | 1.16 | 89.6 | 0.72 |
| BC + augmentation | 100.0 | 100.0 | 1.16 | 89.6 | 0.72 |
| BC + DAgger (3 iters) | 99.5 ± 0.3 | 99.6 ± 0.3 | 1.17 | 89.6 | 0.72 |
| BC + aug + DAgger (3) | 99.8 ± 0.2 | 99.6 ± 0.1 | 1.17 | 89.5 | 0.72 |
| Scripted expert (deterministic) | 100.0 | 100.0 | 1.16 | 89.7 | 0.71 |

**Excess edits** are the slots changed beyond the exact minimum any valid repair needs. **Edit-optimal preservation** is 1 − excess / (13 − minimum). Both are computed by an exact solver after the run (`taskflow/eval/exact.py`), and failed turns get no credit.

### Matched LLM-call budget per turn (`make evaluate-capped`, `results/runs/test-offline-cap*`): revision success %

| Cap | Static rules | Static (cost-aware) | BC | BC + aug | BC + DAgger (3) | BC + aug + DAgger (3) | Expert |
|---|---|---|---|---|---|---|---|
| 1 call | 72.4 | 79.7 | 97.9 | 97.8 | 97.7 | 97.6 | 98.5 |
| 2 calls | 98.1 | 100.0 | 99.6 | 99.8 | 99.6 | 99.5 | 100.0 |

### Multi-component budget cuts (`make evaluate-multi`)

Each episode starts from an expensive itinerary the user already approved, then cuts the budget. The cut is impossible (ask), or needs 1, 2, or 3 components to change. Episodes come from each split's own trips.

**Real-trip family** (`test_multi`: 138 episodes from test trips):

| System | Revision success | Excess edits / turn | Global rebuild rate | LLM calls / turn |
|---|---|---|---|---|
| Always-Global (deterministic) | 100.0 | 4.71 | 100% | 4.08 |
| Static rules | 100.0 | 5.94 | 75% | 4.09 |
| Static rules (cost-aware) | 100.0 | 1.03 | 0% | 2.01 |
| BC | 98.8 ± 0.9 | 0.79 | 0% | 2.06 |
| BC + aug + DAgger (3) | 100.0 | 0.82 | 0% | 2.02 |
| Scripted expert | 100.0 | 0.78 | 0% | 2.01 |

Per difficulty level, with excess edits for the learned coordinator vs. cost-aware static rules:

| Level | Learned | Cost-aware static |
|---|---|---|
| 1 component | 0.13 | 0.33 |
| 2 components | 0.41 | 0.81 |
| 3 components | 1.79 | 1.79 |

All three have 100% success at every level (`results/runs/test-multi/REPORT.md`).

**Fixed synthetic stress suite** (12 cases, never trained on, but inspected during development): every system, and every learned seed, solves 12/12 (`results/runs/challenges/`).

### What the numbers say

1. **Partial vs. global replanning.**
   - Regenerating on every update costs about 5.8× the LLM calls of the learned coordinator.
   - How much it disturbs the plan depends on how unstable regeneration is: 8.2 unnecessary slot changes per turn with sampled regeneration (our stand-in for an LLM rebuilding from scratch), 1.5 with deterministic regeneration. The real figure needs a real LLM.
2. **The strong static baseline matters.**
   - Against the original static rules, the learned coordinator looked far better on multi-component cuts (0.8 vs 5.9 excess edits), but most of that gap came from a weak baseline.
   - Against the cost-aware static rules, the learned coordinator is about 20% better on excess edits (0.82 vs 1.03), with the same success and LLM calls.
   - On the main benchmark it uses about 14% fewer LLM calls (0.72 vs 0.84) at slightly lower success (99.6–100% vs 100%).
3. **Tight budgets are where learning clearly helps.** With 1 LLM call per turn, the learned coordinators reach about 98%, against 80% for cost-aware rules and 72% for the original rules. With 2 calls, the cost-aware rules catch up (100%).
4. **Compounding error and recovery.** Forced-mistake recovery (cases where the forced action left the plan broken):

   | Method | Recovery |
   |---|---|
   | BC | 90–96% |
   | BC+DAgger(3) | 83–100% (varies by mistake) |
   | BC+augmentation | 99–100% |
   | BC+aug+DAgger(3) | 99–100% |

   Augmentation is the reliable fix. Over a whole episode the gap is small: BC handles 98.6% of held-out 4th turns, seed 0.
5. **Against the proposal's rejection criterion.**
   - **Holds:** under a tight call budget, and on edit efficiency for multi-component cuts.
   - **Doesn't hold:** without a budget cap against the cost-aware rules, where success is equal or slightly lower, at modestly fewer calls.
   - Everything still needs confirming with real LLM agents.

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
- **"Feasible" means feasible for our planners:** the current plan already satisfies the update, or the greedy composer can find a plan. All 3,667 labels (v0 and multi family) agree with an exact solver under the all-13-slots completeness rule.
- **Simulated instability in global regeneration.** Global regeneration samples among near-best options, to mimic the instability of an LLM rebuilding a plan from scratch. The deterministic control (`always_global_det`) shows how much the preservation number depends on that choice: 31% vs. 93%.
- **No TravelPlanner leaderboard comparison.** Splits are re-drawn, so numbers aren't comparable with the official leaderboard. Upstream compatibility is checked by running the upstream check functions on per-query data slices (`docs/review/upstream_adapter.py`). All 3,054 passing expert plans pass. This is not the official CLI or full database, and a few cost differences come from upstream's substring name matching (`LICENSES.md`).
- **The expert searches up to three component repairs.** It used to stop at two and rebuild globally. A review showed three local repairs also solve those cases, so the search was extended, and the multi family no longer needs global rebuilds. Difficulty levels are still chosen with the same expert, so the results measure imitation of its decision boundary.
- **Action mask.** The learned coordinator may not repeat the previous re-plan or search back to back. That's safe with deterministic planners, but should be revisited with real LLM agents, whose retries aren't idempotent.
- **Tooling:** dataclasses instead of pydantic, and pip + `requirements.txt` instead of uv. There's no CI.

## Next steps

See [docs/STATUS.md](docs/STATUS.md) for the full list with suggested owners. In short:
1. Run with a real model and replace the simulated cost with measured cost.
2. Build the single-agent LLM baseline.
3. Settle the validity questions in the checklist.
4. Extend to LLM paraphrases, FlexTravelBench and multi-city trips.
5. Package the dataset and the verifier for release.
