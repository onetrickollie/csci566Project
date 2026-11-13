# Architecture

## The problem in one paragraph

A user has a valid 3-day itinerary and keeps revising their requirements. After each revision, the system has to decide **how much** of the plan to change:
- nothing,
- one component (transport, accommodation, meals, attractions),
- everything,
- or nothing, because the request can't be satisfied, so it asks the user instead.

The **coordinator** makes that decision step by step. We train a small neural coordinator by imitation (BC, trajectory augmentation, DAgger) and compare it with hand-written and LLM coordinators.

## Data flow

```
TravelPlanner CSVs (Hugging Face, CC BY 4.0)
   │  taskflow/data/travelplanner.py   parse each query's database slice
   ▼
Query + CityDB (flights, ground transport, hotels, restaurants, attractions)
   │  taskflow/data/tasks.py           base constraints → split by query → update chains + text
   ▼
data/tasks/v0/{train,val,test}.jsonl  (Episode = base constraints + list of Turns)
   │  taskflow/env/episode.py: run_episode(episode, query, coordinator, llm=None)
   ▼
for each turn:
   user text ──► Constraint Tracker ──► ConstraintDiff ──► Constraints (system belief)
   verifier runs once on the current plan
   repeat until KEEP_PLAN / STOP / ASK_CLARIFICATION / 10 steps:
       coordinator.act(env) ──► action
         SEARCH_*          refresh one cache (transport / accommodation / dining)
         REPLAN_LOCAL_<g>  component agent re-plans group g, others fixed
         REPLAN_GLOBAL     every agent re-plans from scratch
         VERIFY            verifier → Report (violations + offending slots)
   score against the episode's ground truth → TurnResult
   │
   ▼
taskflow/eval/metrics.py → results/metrics.json → results/REPORT.md + figures
```

## Modules

| Module | Responsibility | Key functions/classes |
|---|---|---|
| `taskflow/data/travelplanner.py` | Download and parse TravelPlanner | `load_queries`, `parse_reference_information`, `Query`, `CityDB` |
| `taskflow/data/tasks.py` | Build evolving-constraint episodes | `build_dataset`, `make_episode`, `candidate_diffs`, `TEMPLATES` |
| `taskflow/env/state.py` | Shared types and constants | `Constraints`, `ConstraintDiff`, `ACTIONS`, `SLOTS`, `ACTION_COST` |
| `taskflow/env/tools.py` | Search tools, pricing, per-component cache | `Cache`, `search_*`, `acc_cost`, `TransportOption` |
| `taskflow/env/verifier.py` | Deterministic checker | `verify`, `Report`, `Violation`, `plan_cost` |
| `taskflow/env/episode.py` | Turn environment and episode runner | `TurnEnv`, `run_episode`, `TurnResult` |
| `taskflow/agents/tracker.py` | Text → structured update | `parse` (rules), `parse_llm`, `parse_any`, `validate` |
| `taskflow/agents/planners.py` | Component planners + composer | `replan_local`, `compose_global`, `is_feasible` |
| `taskflow/agents/llm_planners.py` | LLM component agents with validation | `accommodation`, `transport`, `meals`, `attractions` |
| `taskflow/coordinators/oracle.py` | Privileged expert (labels any state) | `Oracle`, `minimal_fix` |
| `taskflow/coordinators/baselines.py` | Hand-written coordinators | `StaticRules`, `AlwaysGlobal` |
| `taskflow/coordinators/llm_coordinator.py` | LLM coordinator / LLM teacher | `LLMCoordinator`, `state_summary` |
| `taskflow/learning/encode.py` | Non-privileged observation (~95 features) | `encode`, `action_mask` |
| `taskflow/learning/imitation.py` | BC, augmentation, DAgger | `collect`, `train`, `dagger`, `LearnedPolicy` |
| `taskflow/llm/` | LLM client, prompts, fake backend | `get_client`, `LLMClient`, `prompts.py`, `fake.py` |
| `taskflow/eval/` | Metrics and report rendering | `summarize`, `breakdown`, `write_report` |
| `taskflow/data/world.py` | Merged database of every TravelPlanner city for the app; distance-based driving/taxi estimates for routes without records | `build_world`, `World.trip_query`, `World.resolve` |
| `scripts/app.py` | Interactive web app (stdlib HTTP server, localhost only) | `api_trip`, `api_update` |
| `scripts/` | Command-line entry points | `build_dataset`, `train`, `evaluate`, `evaluate_challenges`, `demo`, `demo_html`, `app`, `make_snapshot` |

## Core types

- **Plan:** `dict[slot, value]` with 13 slots in four groups.
  - `transport`: `transport_out`, `transport_back`. Values look like `flight:F123`, `self-driving` or `taxi`.
  - `accommodation`: `accommodation`.
  - `meals`: 6 slots, from day-1 dinner to day-3 lunch.
  - `attractions`: 4 slots.
- **Constraints:**
  - budget, people, room_type, house_rules, cuisines, transport
  - min_rating (restaurant rating floor)
  - priority: `cost` means total ≤ 85% of budget; `quality` means accommodation rating ≥ 4.
- **ConstraintDiff:** `op` is add, delete, replace or reprioritize. The diff also carries `target_type`, `old`, `new` and `nl` (the user's text).
- **Report:** `passed`, `total_cost`, `component_cost`, and `violations`, each with `kind`, `detail` and `slots`.
- **Actions** (12):
  - Terminal: `KEEP_PLAN`, `STOP`, `ASK_CLARIFICATION`.
  - `SEARCH_*` refreshes a cache.
  - `REPLAN_LOCAL_*` re-plans one component; `REPLAN_GLOBAL` re-plans everything.
  - `VERIFY` re-runs the checker.

## Semantics that matter

- **Stale caches.** Each cache remembers the constraints it was searched under. If a constraint changes, a local re-plan on a stale cache can pick options the new constraint forbids. Searching first is part of what the coordinator must learn.
- **Stale reports.** Any re-plan makes the verifier report stale until the next `VERIFY`.
- **Infeasible updates.** If an update can't be satisfied, the correct action is `ASK_CLARIFICATION`. The user then withdraws the update and the plan returns to its start-of-turn state.
- **Belief vs. truth.** The system carries its own tracked constraints from turn to turn. Ground truth from the episode file is used only for scoring, so a tracker mistake persists.
- **Completeness.** A valid itinerary fills all 13 slots, which is stricter than upstream TravelPlanner (`verify(..., require_complete=False)` relaxes it).
- **Shared evidence.** `learning/encode.candidate_evidence` gives both the learned policy and the LLM coordinator the same facts from the caches: cheapest options, candidate counts and uncovered cuisines. Static rules use the same facts to decide when to ask.
- **Matched budget.** `run_episode(..., call_cap=N)` ends a turn as `BUDGET_EXHAUSTED` when an action would exceed N cost-model LLM calls.
- **LLM failures.** `LLMFatalError` (bad key, model or endpoint) always propagates. Other failures fall back to the deterministic component and are counted in `client.usage.fallbacks`.
- **Determinism.** Offline runs are fully deterministic given the seeds. LLM runs are cached on disk by request hash, so re-runs are free and repeatable.

## Coordinators

| Coordinator | Information | Behaviour |
|---|---|---|
| `oracle` | Privileged: simulates repairs, knows feasibility | VERIFY if stale → KEEP/STOP if valid → if infeasible, refresh searches then ASK → smallest local repair (search first if stale) → global |
| `static_rules` | Update type + verifier | Fixed script per update type, then VERIFY, one global fallback, then ASK |
| `always_global` | — | REPLAN_GLOBAL every turn |
| `llm_coordinator` | Same state as the learned policy, as JSON | LLM picks each action; invalid reply → static-rule action |
| learned (`bc`, `bc_aug`, `bc_dagger{1,2,3}`, `bc_aug_dagger3`) | Non-privileged features | MLP argmax with action mask |

## Where to extend

- **New constraint type:**
  1. Add it to `Constraints`, `ConstraintDiff.apply` and `DIFF_TYPES`.
  2. Add a check in `verifier.verify`.
  3. Add a filter in `tools.search_*` and include it in `Constraints.cache_key`.
  4. Add candidates in `tasks.candidate_diffs`, templates in `TEMPLATES`, and tracker rules.
  5. Add a `KINDS` entry in `encode.py`.
- **New coordinator:** any object with `name` and `act(env) -> action`. Register it in `common.baseline_policies`.
- **New LLM component:** add a prompt in `llm/prompts.py`, a fake answer in `llm/fake.py`, then validate the reply and fall back to the deterministic choice.
- **Multi-city:** generalize `SLOTS` to per-day slots, make `transport_options` per leg, and make `compose_global` choose the city order.
