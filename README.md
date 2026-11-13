# TaskFlow-Travel — Engineering Plan

> Source of truth for scope, interfaces, and task ownership. Team leads assign the tasks.

---

## 1. What we are building (one paragraph)

A multi-agent travel planner that handles **multi-turn, evolving user constraints** (add / delete / replace / reprioritize). A small **learned coordinator** decides each step whether to keep the plan, ask for clarification, call a specialist agent, repair one component locally, or rebuild globally. It is trained by **behavior cloning + DAgger + trajectory augmentation** from expert demonstrations (an LLM teacher plus a privileged scripted oracle), and evaluated against a single agent, a rule-based multi-agent workflow, and an always-regenerate baseline. The evolving-constraint dataset and the verifier harness will be **released publicly**, so code quality and reproducibility matter.

Base data: TravelPlanner (Xie et al., ICML 2024) and FlexTravelBench / Flex-TravelPlanner (Oh et al., 2025).

---

## 2. Ground rules

1. **Frozen interfaces (Section 4) are contracts.** Do not change a schema silently. If a change is needed, edit `schemas/` + `CHANGELOG_SCHEMAS.md` in a dedicated commit and say so in the PR description.
2. **Determinism.** Every script takes `--seed`. No hidden randomness. Generated data is written with a manifest (git SHA, seed, config hash).
3. **No LLM calls in unit tests.** Use the fake LLM in `taskflow/llm/fake.py`. Real calls only in `scripts/` and always through `taskflow/llm/client.py` (which logs tokens + cost and reads the cache).
4. **Cache everything.** All LLM and tool calls go through a content-hash disk cache. Re-running an experiment must cost $0 if nothing changed.
5. **Never commit secrets or raw API keys.** Keys come from env vars only.
6. **Licenses.** Before adding any upstream data file to the repo, check `LICENSES.md`. Do not vendor upstream datasets; download them via `scripts/download_data.py`.
7. **Small PRs**, one task ID each (Section 6). Include tests and a one-line "how I verified it."
8. Python 3.11, `uv` for deps, `ruff` + `pytest`. Type hints everywhere; `pydantic` v2 for schemas.

---

## 3. Repo layout

```
taskflow-travel/
  README.md                 # this file
  LICENSES.md               # upstream licenses + redistribution notes
  schemas/                  # JSON Schema exports of the pydantic models (generated)
  taskflow/
    data/
      travelplanner.py      # loaders for TravelPlanner queries + local database
      flexbench.py          # loaders for FlexTravelBench
      splits.py             # split by ORIGINAL query id, before variant generation
      perturb.py            # structured update ops: add/delete/replace/priority
      paraphrase.py         # LLM paraphrase of ops (+ back-verification)
      feasibility.py        # is a variant satisfiable given the database?
    env/
      tools.py              # cached TravelPlanner tools (flights, hotels, restaurants, attractions, distance)
      state.py              # ConstraintState, Itinerary, ConversationState
      verifier.py           # deterministic checker -> VerifierReport
      episode.py            # multi-turn episode runner (gym-like step())
    agents/
      tracker.py            # NL update -> ConstraintDiff
      transport.py
      accommodation.py
      activity_dining.py
      composer.py
    coordinators/
      single_agent.py       # baseline 1
      static_rules.py       # baseline 2
      always_global.py      # baseline 3 (full regeneration every turn)
      oracle.py             # privileged scripted expert (sees full VerifierReport)
      llm_teacher.py        # strong-LLM expert, acts from ANY state
      learned.py            # small LM / MLP policy wrapper
    learning/
      encode.py             # state -> model input text/features
      bc.py                 # behavior cloning trainer
      dagger.py             # DAgger loop
      augment.py            # inject-error-then-recover trajectories
    eval/
      metrics.py
      recovery.py           # forced-bad-action perturbation eval
      report.py             # tables + plots
    llm/
      client.py             # single entry point, logging, cost, cache
      fake.py
  scripts/                  # CLI entry points (download, build_dataset, run_eval, train, ...)
  configs/                  # YAML configs per experiment
  tests/
```

---

## 4. Frozen interfaces (v0 — freeze by end of week 2)

Write these as pydantic models in `taskflow/env/state.py` and export JSON Schema to `schemas/`.

### 4.1 Constraint state

```json
{
  "constraints": [
    {"id": "c3", "type": "budget", "op": "<=", "value": 2200, "unit": "USD",
     "priority": 1, "active": true, "introduced_turn": 0, "last_modified_turn": 2}
  ],
  "priorities": ["cost", "convenience"],
  "turn": 2
}
```
Constraint `type` ∈ TravelPlanner hard/commonsense types plus our additions: `budget, dates, origin, destination, num_people, room_type, room_rule, cuisine, transportation, accommodation_location, attraction_must_include, priority`.

### 4.2 Constraint diff (one user update)

```json
{"op": "replace", "target_type": "budget", "old": 3000, "new": 2200,
 "nl": "Actually can we keep it under $2,200 total?", "paraphrase_id": "p17"}
```
`op` ∈ `add | delete | replace | reprioritize`.

### 4.3 Itinerary

Day-indexed slots, matching TravelPlanner's plan format so their evaluator can be reused:
```json
{"days": [{"day": 1, "current_city": "...", "transportation": "...", "breakfast": "...",
           "attraction": "...", "lunch": "...", "dinner": "...", "accommodation": "..."}]}
```
Each slot is addressable as `(day, slot)` — this is the argument space for `REPLAN_LOCAL`.

### 4.4 Verifier report

```json
{"pass": false,
 "violations": [{"constraint_id": "c3", "type": "budget", "detail": "total=2480 > 2200",
                 "components": [[2,"accommodation"],[3,"accommodation"]]}],
 "commonsense_ok": true, "hard_ok": false}
```
`components` lists the itinerary slots that cause the violation. This drives the oracle's local-vs-global decision and the stability metric.

### 4.5 Action

```json
{"name": "REPLAN_LOCAL", "args": {"targets": [[2,"accommodation"],[3,"accommodation"]]}}
```
`name` ∈ `KEEP_PLAN, ASK_CLARIFICATION, SEARCH_TRANSPORTATION, SEARCH_ACCOMMODATION, SEARCH_ACTIVITY_DINING, REPLAN_LOCAL, REPLAN_GLOBAL, VERIFY, STOP`.

### 4.6 Trajectory log (one line per step, JSONL)

```json
{"episode_id": "...", "task_id": "...", "turn": 2, "step": 4,
 "state": {...}, "action": {...}, "expert_action": {...} | null,
 "actor": "teacher|oracle|policy", "verifier": {...},
 "llm_calls": 1, "tokens_in": 812, "tokens_out": 140, "cost_usd": 0.0021}
```
`expert_action` is filled during DAgger relabeling even when `actor = policy`.

---

## 5. Key design decisions (do not re-litigate without the team)

- **Splits are by original query ID**, created *before* variants are generated. TravelPlanner's public splits are small/uneven (train has very few annotated plans), so we pool queries and re-split. Our numbers are therefore **not** comparable to the official leaderboard; say so in docs.
- **Paraphrases are not labels.** The structured `ConstraintDiff` is ground truth; paraphrases are back-verified (an LLM re-parses the paraphrase and must recover the same diff) or discarded.
- **Held-out test conditions:** unseen op combinations, unseen op orders, a different paraphrase template/model, and longer chains than seen in training.
- **The oracle must be able to act from any state**, not just replay a trajectory. This is what makes DAgger cheap. The LLM teacher is only queried where the oracle abstains (e.g., ambiguous/infeasible → clarification).
- **Coordinator model:** small LM (≈0.5–1.5B) with LoRA, outputting the action as constrained JSON; fallback is an MLP over features from `encode.py`. Same base LLM for all sub-agents and baselines.
- **Cost accounting** counts LLM calls and tokens (TravelPlanner tools are a local database and are free).

---

## 6. Task board

Status: `todo | doing | review | done`. Owner: sub-team (`bench`, `agents`, `learning`, `eval`); sub-teams assign individuals.

| ID | Task | Depends on | Acceptance criteria | Owner | Status |
|---|---|---|---|---|---|
| T01 | Repo scaffold, `uv`, ruff, pytest, CI | — | `uv run pytest` green in CI on empty tests | eval | todo |
| T02 | `download_data.py` + TravelPlanner/Flex loaders | T01 | Loads all query splits + database; counts printed and asserted in a test; `LICENSES.md` filled | bench | todo |
| T03 | pydantic models for Section 4 + JSON Schema export | T01 | Round-trip tests; `schemas/*.json` generated by script | bench | todo |
| T04 | Cached tool layer `env/tools.py` | T02 | Same API as TravelPlanner tools; cache hit test | bench | todo |
| T05 | Verifier `env/verifier.py` | T02,T03 | **Agrees with the official TravelPlanner evaluator on 100% of the reference plans**; emits `components` per violation | bench | todo |
| T06 | `llm/client.py` + `fake.py` (logging, cost, disk cache) | T01 | Cost per call logged; identical call served from cache | eval | todo |
| T07 | `splits.py` (by original query id) | T02 | No query id appears in two splits (test) | bench | todo |
| T08 | `perturb.py` structured ops + chain sampler | T03,T07 | Generates chains of length 1–4 for all four ops; deterministic under seed | bench | todo |
| T09 | `feasibility.py` | T04,T05,T08 | Marks each variant feasible/infeasible; infeasible → expected action ASK_CLARIFICATION | bench | todo |
| T10 | `paraphrase.py` with back-verification | T06,T08 | ≥95% agreement on a 50-item hand-check set | bench | todo |
| T11 | `episode.py` multi-turn runner | T03,T04,T05 | Gym-like `reset/step`; replays a logged trajectory exactly | agents | todo |
| T12 | Sub-agents + composer | T04,T06,T11 | Each agent unit-tested with fake LLM | agents | todo |
| T13 | Baselines: single_agent, static_rules, always_global | T12 | All run end-to-end on 20 dev tasks with logs in format 4.6 | agents | todo |
| T14 | Privileged oracle | T05,T11 | Beats static_rules on dev; deterministic | learning | todo |
| T15 | LLM teacher (acts from arbitrary state) | T06,T11 | Given a mid-episode state, returns a valid action | learning | todo |
| T16 | `encode.py` + `bc.py` | T03,T14 | Trains on oracle/teacher logs; reports per-action accuracy | learning | todo |
| T17 | `dagger.py` (β schedule 0.5→0.25→0, 3 iters) | T15,T16 | Each iteration adds relabeled states; dataset grows; metrics logged per iter | learning | todo |
| T18 | `augment.py` inject-error-then-recover | T14,T11 | Error types: unnecessary global, skipped verify, stale cache, wrong keep | learning | todo |
| T19 | `metrics.py` | T05 | Final Pass Rate, New Constraint Satisfaction, Retention Rate, Revision Success, Unaffected-Slot Preservation, LLM calls, tokens, cost | eval | todo |
| T20 | `recovery.py` forced-bad-action eval | T11,T19 | Recovery rate by injected step t and by DAgger iteration | eval | todo |
| T21 | `report.py` tables + plots | T19,T20 | Pareto plot (pass rate vs tokens) per change type; error-vs-step plot; ablation table | eval | todo |
| T22 | Release package: HF dataset card + datasheet, pip-installable harness, README quickstart | T05,T10,T19 | Fresh clone → `pip install` → run verifier on a sample in <5 min | bench | todo |

---

## 7. Experiments to support (configs in `configs/`)

Systems: `single_agent`, `static_rules`, `always_global`, `oracle` (upper bound), `bc`, `bc_aug`, `bc_dagger_{1,2,3}`, `bc_aug_dagger`.

Breakdowns: change type × chain length × {seen, held-out}.

Ablations: coordinator size; no verifier signal in state; no cache; number of DAgger iterations.

Headline figures:
1. **Partial vs global replanning:** Final Pass Rate (y) vs tokens or LLM calls per turn (x), one point per system, one panel per change type.
2. **Compounding error:** per-step action error vs step index, BC vs DAgger.
3. **Recovery:** pass rate after a forced bad action at step t.

---

## 8. Definition of done (per PR)

- [ ] Tests added/updated, `uv run pytest` and `ruff check` pass
- [ ] No schema changes, or schema change logged in `CHANGELOG_SCHEMAS.md`
- [ ] Any new script has `--seed`, `--config`, and writes a manifest
- [ ] No real LLM calls in tests
- [ ] PR description: task ID, what changed, how verified

## 9. Open questions (team decides)

- Final deadline. If it is earlier than 12 weeks out, cut to BC + augmentation + 1 DAgger round and chains ≤2.
- Base LLM and teacher LLM choice, and per-person API budget.
- GPU availability for LoRA training (else use the MLP coordinator).
- FlexTravelBench and TravelPlanner redistribution terms (blocks T22).
