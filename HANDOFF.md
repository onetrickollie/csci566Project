# TaskFlow-Travel — Team Handoff

Everything a teammate needs to pick this project up and keep going: what the project is, what has been built and verified, how to run it, what's left (with owners and "done" criteria), and the rules we follow so results stay trustworthy.

Last updated: 2026-11-13 · Repo: https://github.com/onetrickollie/taskflow-travel · Website: https://onetrickollie.github.io/taskflow-travel/ · Course: CSCI 566

---

## 1. Start here (15 minutes)

```bash
git clone https://github.com/onetrickollie/taskflow-travel.git
cd taskflow-travel
make setup        # creates .venv, installs requirements, copies .env.example -> .env
make test         # 94 tests, offline, about 10 seconds (downloads TravelPlanner data on first run, ~37 MB)
make app          # interactive web app at http://localhost:8566
```

Without `make`:
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/app.py
```

Requirements: Python 3.11+ (developed on 3.14), about 1 GB disk for torch. No GPU. No API key needed for anything except the LLM experiments.

**Try this in the app:**
1. From **Chicago** to **Detroit**, March 10, 2 travelers, $3,000.
2. Type `Let's change the budget to $1,200.`
3. Then type `The place needs to allow pets.`
4. Then type `Let's change the budget to $50.` (this one is impossible; watch who asks).

### Reading order
1. This file.
2. [docs/TaskFlow_Travel_PreProposal.pdf](docs/TaskFlow_Travel_PreProposal.pdf): what we promised.
3. [README.md](README.md): results and caveats.
4. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how the code fits together.
5. [docs/STATUS.md](docs/STATUS.md): the short status table.
6. If you'll touch the LLM side: [docs/LLM_SETUP.md](docs/LLM_SETUP.md).
7. If you'll touch evaluation or data: [docs/SUPERVISOR_REVIEW.md](docs/SUPERVISOR_REVIEW.md) and [docs/VERIFICATION_CHECKLIST.md](docs/VERIFICATION_CHECKLIST.md).

---

## 2. What the project is

A user has a valid 3-day itinerary and keeps changing their mind: lower the budget, add a cuisine, require pets, no flights, prioritize quality, and so on. After each change, a **coordinator** decides what to do:
- keep the plan;
- ask for clarification;
- refresh a search;
- repair one component (transport, accommodation, meals, attractions);
- or rebuild everything.

The research question from the proposal is whether a small coordinator **learned by imitation** (behavior cloning + trajectory augmentation + DAgger) handles these revisions better than hand-written rules or full regeneration. "Better" means the same success, fewer unnecessary changes to the plan, and fewer LLM calls. The instructor's feedback asked us to handle compounding errors (DAgger / augmentation) and to release the dataset and verifier.

Data comes from the public **TravelPlanner** benchmark (osunlp/TravelPlanner, CC BY 4.0).

---

## 3. What has been done

### 3.1 Built

| Area | What exists | Where |
|---|---|---|
| Data loading | Parses TravelPlanner's per-query database slices. Handles optional index columns, names starting with digits, duplicate names (first record wins, like upstream), and escaped newlines. | `taskflow/data/travelplanner.py` |
| Verifier | Deterministic checker: TravelPlanner commonsense + hard constraints, plus our rating floor and cost/quality priority, plus completeness (all 13 slots filled). Each violation names the slots that cause it. | `taskflow/env/verifier.py` |
| Task set v0 | 355 three-day single-city trips, split by **original query** (train 215 / val 71 / test 69 queries) **before** generating variants. 1,420 episodes of 1–4 updates (add / delete / replace / reprioritize). About 18% of turns are infeasible (the right response is to ask). Test is held out three ways: unseen trips, a second phrasing template set, and 4-turn chains. | `taskflow/data/tasks.py`, `data/tasks/v0/{train,val,test}.jsonl` |
| Multi-component family | One-turn budget cuts from an approved expensive itinerary. Level 0 is impossible (ask); levels 1–3 need 1, 2 or 3 components changed. Built from each split's own trips, in separate files. | `data/tasks/v0/*_multi.jsonl` |
| Synthetic stress suite | 12 fixed cases (1, 2 or 3 components) used as a regression check, never trained on. | `taskflow/data/challenges.py` |
| Agents | Rule-based constraint tracker; deterministic component planners (local repair keeps the other components fixed; global rebuild starts from scratch). | `taskflow/agents/` |
| Environment | Multi-turn runner. Cached searches go stale when relevant constraints change. The system carries its own constraint belief (truth is used only for scoring). Per-action cost model and an optional call cap. | `taskflow/env/episode.py`, `state.py`, `tools.py` |
| Coordinators | `always_global` (+ deterministic control `always_global_det`), `static_rules`, `static_cost_aware` (the stronger baseline), `oracle` (privileged scripted expert: searches repairs of up to 3 components, deterministic mode only), `llm_coordinator`. | `taskflow/coordinators/` |
| Learned coordinator | MLP over ~96 non-privileged features. BC, BC+augmentation, BC+DAgger (1–3 iterations), BC+aug+DAgger(3), 3 seeds each (18 models, committed). | `taskflow/learning/`, `models/` |
| Evaluation | Proposal metrics, exact minimum-edit scoring, forced-mistake recovery, error vs. step, per-type/turn/level breakdowns, matched call budgets, figures. Every run has a manifest with code/prompt/data/model fingerprints. | `scripts/evaluate.py`, `taskflow/eval/` |
| LLM layer | One client (offline / fake / OpenAI-compatible / Anthropic) with a disk cache keyed by endpoint, retries, usage and fallback counters. Bad keys/models/endpoints abort. Every LLM component falls back to the deterministic one on invalid replies, and fallbacks are reported. | `taskflow/llm/`, `taskflow/agents/llm_planners.py`, `taskflow/coordinators/llm_coordinator.py` |
| Demos | Interactive web app with any start city and destination; visual replay of test episodes; terminal demos. | `scripts/app.py`, `demo_html.py`, `demo.py` |
| Review tooling | Adapter that runs upstream TravelPlanner check functions on our plans; exact feasibility audit; regression diagnostics. | `docs/review/` |

### 3.2 Verified

An independent reviewer audited the repo four times. Every finding was fixed with a regression test or documented. The latest re-review confirmed:
- **Reproducibility:** all datasets rebuild byte for byte from `--seed 0`; all 18 models retrain to identical weights; every evaluation reproduces exactly.
- **Labels:** all 3,667 feasibility labels agree with an independent exact solver.
- **Upstream compatibility:** all 3,054 passing expert plans pass the adapted upstream TravelPlanner checks. That means the upstream check functions run on per-query slices, not the official CLI or full database. A few cost differences remain from upstream's substring name matching; see `LICENSES.md`.
- **Tests:** 94 pass, including one regression test per review finding (`tests/test_review_fixes.py`, `test_handoff.py`, `test_multi.py`, `test_app.py`).

The full audit trail, with findings and responses, is in `docs/SUPERVISOR_REVIEW.md` and `docs/review/`.

### 3.3 How we got here (timeline)

1. Pre-proposal, then the engineering plan (`docs/ENGINEERING_PLAN.md`: interfaces, task board T01–T22).
2. Offline end-to-end prototype: data → tasks → planners → coordinators → BC/aug/DAgger → evaluation → demo.
3. Pluggable LLM layer and handoff docs.
4. Review 1 (20 issues): fixed the parser, duplicate names, completeness, state carried between turns, retention scoring, the LLM failure handling, the comparison baselines, and run manifests.
5. Review 2: exact-solver audit, upstream adapter, stress suite. The models failed multi-component cases, so we added the multi-component training family.
6. Interactive app with any city pair. It exposed out-of-range budget failures, fixed with feature clipping, a repeat mask, and impossible and near-floor cuts in training.
7. Review 3: app realism (no ocean drives, 12-hour leg limit), ask scoring, input validation. A **stronger cost-aware static baseline** revealed the expert's 2-repair limit, so the expert now searches 3-component repairs and the models were retrained.

---

## 4. Current results (offline)

The full tables are in `README.md` → Results and `results/REPORT.md`. The headline numbers:

| Setting | Learned (BC+aug+DAgger3) | Cost-aware static | Original static | Always regenerate |
|---|---|---|---|---|
| Main test: revision success | 99.6% | 100% | 100% | 100% |
| Main test: LLM calls / turn | **0.72** | 0.84 | 0.95 | 4.19 |
| Capped at 1 LLM call / turn | **97.6%** | 79.7% | 72.4% | 19.4% |
| Multi-component cuts: excess slot edits | **0.82** | 1.03 | 5.94 | 4.71 (deterministic) |

**The honest claim:**
- **Clear win:** under a tight LLM-call budget.
- **Modest win:** fewer unnecessary changes on multi-component cuts, and fewer calls on the main benchmark.
- **No win:** without a budget cap against a well-designed rule set.

All of this is **offline**. Agents are deterministic and LLM costs come from a cost model, so these numbers must be confirmed with real LLM agents (task H4 below).

---

## 5. How to run things

| Goal | Command | Output |
|---|---|---|
| Interactive app | `make app` | http://localhost:8566 |
| Replay a test episode in the browser | `make demo-html` / `make demo-html-multi` | `demo.html` (opens) |
| Terminal demo | `make demo` / `make demo-interactive` | stdout |
| All tests | `make test` | 94 passed |
| Rebuild tasks | `make dataset` | `data/tasks/v0/` (byte-identical if nothing changed) |
| Retrain all models (3 seeds) | `make train` | `models/*.pt`, `training_log.json` (~3 min CPU) |
| Canonical evaluation | `make evaluate` | `results/` (the only command that writes there) |
| Matched call budgets | `make evaluate-capped` | `results/runs/test-offline-cap{1,2}-*` |
| Multi-component + stress suite | `make evaluate-multi` | `results/runs/test-multi`, `results/runs/challenges` |
| Everything | `make pipeline` | all of the above, ~15 min |
| LLM wiring check (no key) | `make demo-fake` | — |
| LLM run (needs key) | `make demo-llm`, `make evaluate-llm` | `results/runs/val-<provider>-...` |
| One file with all docs + code | `make snapshot` | `project_snapshot.md` (git-ignored) |
| Website, local preview | `make site` | `site/index.html` (git-ignored) |

Any `evaluate.py` run without `--canonical` writes to its own `results/runs/<split>-<backend>-...-<hash>/` folder, so runs never overwrite each other.

---

### The website and CI

`.github/workflows/site.yml` runs on every push to `main`:
1. Install the requirements (CPU-only torch).
2. Run the full test suite.
3. Build the website with `scripts/build_site.py`: docs rendered to HTML, the result reports and figures, the headline table read from the committed `metrics.json`, and episode replays regenerated with the committed models.
4. Publish it to https://onetrickollie.github.io/taskflow-travel/.

On pull requests it only tests and builds.

- **If the tests fail, the site isn't updated.** Check the repo's **Actions** tab.
- **To add a page:** list the Markdown file in `PAGES` in `scripts/build_site.py`. Links between `.md` files become links between pages automatically.
- **The interactive app can't run on Pages** (it needs a Python server). The site shows recorded replays instead. Hosting the app would need a service that runs Python, such as Render, Railway or a Hugging Face Space.

## 6. What's left

Ordered by priority. Each item says who should own it (sub-teams from the engineering plan), what to do, and when it counts as done.

### P0 — needed for the final report

**H4. First real-LLM run (agents team)**
- **Why:** every LLM component has only been tested offline with a stand-in backend. All cost numbers are simulated.
- **Steps:**
  1. Set up `.env` following `docs/LLM_SETUP.md`.
  2. Run `make demo-fake`, then `make demo-llm`.
  3. Run one validation episode first: `.venv/bin/python scripts/evaluate.py --require-llm --split val --limit 1 --seeds 0 --skip-recovery --out results/runs/live-val-smoke-1`.
  4. Read the report's **LLM usage per system** table and the raw replies in `cache/llm/`.
  5. Fix the prompts in `taskflow/llm/prompts.py`, then scale to `make evaluate-llm` (30 validation episodes).
- **Done when:** a non-DEGRADED validation run with fallback rate under 5%, measured tokens per turn reported for every system, and prompts frozen.
- **Rules:** tune on **validation** only. Run the test split once at the end. Never commit `.env`.

**Single-agent LLM baseline (agents team)**
- **Why:** the proposal promised three systems: single agent, static multi-agent, and learned. The single agent is missing.
- **What:** `taskflow/coordinators/single_agent.py`: one LLM call per turn that sees the conversation and all candidate options and returns the whole plan as JSON. Validate it with the verifier; on failure, report it, don't fall back silently.
- **Done when:** it appears in `make evaluate-llm` results with measured cost.

**Final report, slides, recorded demo (everyone)**
- Use `README.md` → Results as the source of truth. Copy numbers from `results/**/metrics.json`, never retype them.
- Record the app walkthrough from Section 1.

### P1 — strengthens the claims

**New frozen test set with harder revisions (bench team)**
- **Why:** the multi-component family only contains budget cuts, and the 12-case stress suite has been looked at repeatedly, so it is no longer an untouched holdout.
- **What:**
  - Add non-budget multi-component updates (e.g. "entire room + pets" together, or a cuisine change that pushes cost over budget).
  - Add multi-turn sequences of such updates.
  - Develop them on train/val, then generate a new test file **and freeze it before any tuning**.
- **Done when:** new `*_multi2.jsonl` files and a committed evaluation, with the generator in `tasks.py` and tests for split hygiene.

**Add "add a traveler" and date changes (bench + agents)**
- **Why:** the proposal's examples include both, and we support neither.
- **What:**
  - **Travelers:** add `people` to `DIFF_TYPES`, the tracker, the generator and the static scripts. Costs already scale with people. This changes the encoder's one-hot size, so retrain afterwards.
  - **Dates:** TravelPlanner only has flights for each query's dates, so a date change mostly works for driving routes. Decide the scope with the team first.

**LLM teacher experiment (learning team)**
- **What:** `scripts/train.py --teacher llm --llm <provider> --limit 100`, then `evaluate.py --model-suffix _llmteacher`.
- **Note:** collection uses deterministic planners; only the labels come from the LLM.
- **Done when:** a comparison table, oracle-taught vs. LLM-taught.

**Revisit the action mask under real LLMs (learning team)**
- The learned policy may not repeat the previous re-plan or search back to back. That's fine with deterministic planners, but LLM re-plans aren't idempotent.
- After H4, check whether retries would help, and document the decision.

### P2 — release and engineering

| Task | Owner | Notes |
|---|---|---|
| CI | eval | Done: `.github/workflows/site.yml` runs the tests on every push and pull request. Next: add a lint step. |
| Dataset release (T22) | bench | Dataset card + datasheet for `data/tasks/v0`, citing TravelPlanner (CC BY 4.0). Check FlexTravelBench's license before using it. |
| LLM paraphrases (T10) | bench | Paraphrase test updates with an LLM; keep a paraphrase only if the tracker recovers the structured diff. Template set B was written alongside the tracker, so current "unseen phrasing" results are weak evidence. |
| Multi-city trips | bench + agents | 5- and 7-day TravelPlanner queries; per-day slots; city order. |
| JSON Schema export (T03) | bench | dataclasses → `schemas/*.json`. |
| FlexTravelBench | bench | Loader + base constraints, after the license check. |

---

## 7. Rules we follow (please keep them)

1. **Tests first.** Every behavior change comes with a test. Every review finding got a regression test, so keep that habit. `make test` must pass before pushing.
2. **Data, models and results change together.** If you change task generation, features, the expert or the planners, run `make dataset train evaluate evaluate-capped evaluate-multi` and commit all outputs in one go. Then rerun the evaluations once more at the clean commit, so the manifests say `git_dirty: false`. Don't hand-edit result files.
3. **Validation for development, test for reporting.** Prompt tuning, hyperparameters and generator choices happen on `val` / `val_multi`. Touch test only for the final numbers.
4. **Canonical results are opt-in.** Only `make evaluate` (full offline test run) writes `results/`. Everything else goes to `results/runs/`.
5. **Numbers in docs come from `metrics.json`.** Regenerate the README tables when results change.
6. **No secrets in git.** API keys live in `.env` (git-ignored). `cache/` is git-ignored too, since it holds raw LLM replies.
7. **App realism stays app-only.** `taskflow/data/world.py` (distance estimates, 12-hour limit) is never used to build benchmark data.
8. **The scripted expert is deterministic-only.** It refuses to run with LLM agents. In LLM mode, use `llm_coordinator` as the fallible teacher.
9. **No AI-tool attribution in the repo.** Don't add tool names, generated-by notes, co-author trailers or assistant config files (e.g. `AGENTS.md`). If you use an assistant, give it `HANDOFF.md` and `make snapshot` instead.

---

## 8. Where things live

```
HANDOFF.md            this file
README.md             overview, quickstart, results, caveats
Makefile              every common command
.env.example          LLM settings template (copy to .env)
LICENSES.md           data licenses and name-matching notes
docs/
  STATUS.md                 short status table
  ARCHITECTURE.md           data flow, modules, extension points
  LLM_SETUP.md              plugging in an API key
  ENGINEERING_PLAN.md       interfaces + task board (T01–T22)
  SUPERVISOR_REVIEW.md      review findings and responses (audit trail)
  VERIFICATION_CHECKLIST.md open questions and findings log
  review/                   reviewer tools: upstream adapter, exact audit, evidence JSON
taskflow/
  data/        travelplanner.py (loader) · tasks.py (episodes) · challenges.py (stress suite) · world.py (app database)
  env/         state.py (types, actions, cost model) · tools.py (search, cache) · verifier.py · episode.py (runner)
  agents/      tracker.py · planners.py · llm_planners.py
  coordinators/ oracle.py · baselines.py · llm_coordinator.py
  learning/    encode.py (features, mask) · imitation.py (MLP, BC, augmentation, DAgger)
  llm/         client.py · prompts.py · fake.py
  eval/        metrics.py · exact.py (minimum edits) · report.py
scripts/       build_dataset · train · evaluate · evaluate_challenges · app · demo · demo_html · make_snapshot
tests/         94 tests; test_review_fixes.py, test_handoff.py, test_multi.py, test_app.py hold the regressions
data/tasks/v0/ committed episodes (+ manifest, split_of_query.json)
models/        committed weights (18) + training_log.json
results/       canonical REPORT.md, metrics.json, figures; runs/ for every other evaluation
```

---

## 9. Key concepts

- **Slots:** a plan has 13: 2 transport legs, 1 stay, 6 meals, 4 attractions.
- **Feasible:** the current plan already satisfies the update, or the planners can build a plan that does. Verified against an exact solver.
- **Revision success:** the turn ends with a valid plan, or with a clarification question when the update truly can't be met.
- **Excess edits:** slots changed beyond the exact minimum any valid repair needs (`taskflow/eval/exact.py`).
- **Cost model:** offline LLM calls and tokens per action (`ACTION_COST` in `taskflow/env/state.py`). It isn't a measurement; real runs report "Measured" columns.
- **Stale cache:** search results are tied to the constraints they were made under. A local re-plan on a stale cache can pick options the new constraint forbids, so searching first is part of what the coordinator learns.
- **Belief vs. truth:** the system acts on what its tracker understood. Ground truth from the episode file is only used for scoring.
- **DEGRADED run:** any LLM error or fallback. The report flags it, and it isn't a valid LLM result.

---

## 10. Known limitations

- **Offline only so far.** The LLM paths have only been tested with the fake backend.
- **Scope:** 3-day single-city trips; March 2022 data. Test-file queries have hidden constraints, so their starting budgets and requirements were sampled.
- **Feasibility is relative to our planners.** It's checked by an exact solver under the all-13-slots rule, which is stricter than upstream TravelPlanner.
- **Always-regenerate's instability is simulated.** Its preservation number depends on that choice: 30% sampled vs 87% deterministic.
- **The expert defines the difficulty levels** it then demonstrates, so results measure imitation of its decision boundary.
- **App:**
  - Flights exist only for routes and dates in the data.
  - Other routes use distance-based driving estimates (contiguous US, at most 12 hours each way).
  - The offline tracker only understands phrasings like the suggestion buttons.
- **TravelPlanner quirks:** some hotel names were reused from other cities in the source data.

---

## 11. Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: torch` | Use `.venv/bin/python`, or run `make setup` |
| Tests fail on first run without internet | They download TravelPlanner (~37 MB) once into `data/raw/` |
| App says "No realistic way to get from X to Y" | That pair has no flights for that date and is more than a 12-hour drive. Pick a suggested destination or a flight date from the hint |
| App: "Couldn't read that as a change" | Offline tracker; use a suggested phrasing, or configure an LLM in `.env` |
| `set TASKFLOW_LLM_MODEL` / HTTP 401 / 404 | See `docs/LLM_SETUP.md` → Troubleshooting |
| Report says DEGRADED | The LLM failed or fell back; check the usage table and `cache/llm/` |
| Numbers differ after your change | Expected if you changed data, features, the expert or the planners. Regenerate everything together (rule 2) |
| Port 8566 busy | `.venv/bin/python scripts/app.py --port 9000` |

---

## 12. Contacts and ownership

| Sub-team | Owns |
|---|---|
| bench | data, tasks, verifier, release |
| agents | planners, tracker, LLM integration, single-agent baseline |
| learning | encoder, BC/aug/DAgger, LLM teacher |
| eval | metrics, runs, CI, report figures |

Assign names here when the team meets:

| Sub-team | People |
|---|---|
| bench | |
| agents | |
| learning | |
| eval | |
