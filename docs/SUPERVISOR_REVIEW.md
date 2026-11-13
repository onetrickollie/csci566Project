# Supervisor review and implementation handoff

**Latest handoff update:** The reviewer completed H1, H2, H3, and H5 against regenerated baseline `1aaeecd`; H4 is deferred to teammates by explicit user instruction. See [HANDOFF_RESULTS.md](review/HANDOFF_RESULTS.md) for evidence, reproducible commands, limitations, and remaining upstream name-resolution issues. Historical findings and responses below are retained as an audit trail.

Reviewed on 2026-11-13. Baseline: `ff4562a`, including `cd49e18` and `5ce2491`. This is a review of implemented behavior, not a claim that a live provider has been validated. No paid API calls were made. Production code, model weights, datasets, and result files were not changed by this review.

## Implementer: next implementation batches

Please fix the correctness and evaluation blockers below before running paid experiments or extending scope. Keep changes small, preserve historical results, and record each addressed review ID with its regression test and verification command in this file. Do not mark an item fixed merely because a fallback makes a demo finish.

1. **Data and scoring:** O1–O5 below: names/identity, mandatory slots, consistent feasibility, and operational state independent of ground truth. Regenerate data, retrain, and evaluate together after the definitions are fixed.
2. **LLM boundary:** N1–N4: endpoint-isolated cache, explicit failures/fallback reporting, no-update semantics, and safe tracker validation. Use adversarial stub tests without paid calls.
3. **Comparison integrity:** N5–N8 and O6–O10: shared observable information, budget handling, deterministic controls, matched-budget static rules, and durable run metadata.
4. **Live smoke test only after these gates:** start on validation episodes, log raw outputs and fallbacks, and report attempted/successful/cached calls separately. Keep the final test set frozen during prompt development.

## Verification performed

- Existing suite: `.venv/bin/python -m pytest -q` → **25 passed**.
- Isolated copy for experiments: `/tmp/taskflow-review-ff4562a` (does not include the user's `.env`).
- Full offline evaluation, seeds 0/1/2: **all system metrics exactly match the committed values**, recovery selection remains 184. Manifest now identifies `ff4562a`; no rebuild/retraining was necessary for this follow-up because dataset generation and learning code are unchanged.
- Fake evaluation on **40 test episodes / 105 turns**, seed 0, with recovery skipped: completed with zero client errors. Static rules and LLM coordinator: 100% final pass / revision success; learned BC+augmentation+DAgger3: 97.5% final pass / 99.05% revision success. These are wiring checks, not evidence of real-model capability. Fake aggregate usage includes auxiliary error-by-step rollouts, so it is not solely primary benchmark traffic.
- Commands in the isolated copy: `scripts/evaluate.py --llm offline --seeds 0 1 2`, then `scripts/evaluate.py --llm fake --limit 40 --seeds 0 --skip-recovery`, both using the project's `.venv/bin/python`. Machine-readable summary: `docs/review/verification_summary.json`.
- Targeted adversarial diagnostics: `docs/review/llm_regressions.py`; observed output: `docs/review/llm_regressions.json`. This is a diagnostic script, not a test suite that blesses the current broken behavior. It uses synthetic clients and temporary cache storage only.
- Prior full build/train/evaluate audit at `c8872ce` reproduced every metric exactly and passed 14 tests. The current additions do not change the core parser identity, verifier, task-generation, or metric defects listed below.

## New findings in the LLM additions

### N1 — P1: cache collisions across API endpoints

**Location:** `taskflow/llm/client.py:91–101`.

The cache key omits `base_url`. Two OpenAI-compatible endpoints with the same model name and prompt share an entry. In the diagnostic, server B returns server A's response and records zero successful network calls and one cache hit. Changing backend can therefore silently reuse another backend's result.

**Fix / acceptance:** include normalized effective endpoint and request/API configuration in the cache identity; do not include credentials. Same-endpoint replay must hit, different-endpoint requests must miss. Include endpoint identity in manifests too.

### N2 — P1: a completely broken provider can produce a successful "LLM" evaluation

**Locations:** `taskflow/agents/tracker.py:125–132`, `taskflow/agents/llm_planners.py` exception handlers, `taskflow/coordinators/llm_coordinator.py:56–66`, `scripts/evaluate.py:142–146`.

A synthetic client returning HTTP-401 errors for every request completed the first test episode with `final_pass=True`, all tracker checks true, **10 requests, 10 errors, zero successful calls, and zero tokens**. All work was done through deterministic fallbacks. The coordinator records a fallback counter but evaluation does not expose it per system; tracker/agent fallbacks have no equivalent aggregate. Total client errors alone do not establish how much any system used the model.

**Fix / acceptance:** fail immediately for authentication/configuration failures in experiment mode. Report failures, fallback reasons, and fallback rates per component/system; mark degraded results clearly. Distinguish attempted requests, successful responses, cache hits, logical token usage, and actual spending. An all-failing client must not produce an unqualified successful LLM experiment.

### N3 — P1: an explicit no-update response is converted into a constraint mutation

**Location:** `taskflow/agents/tracker.py:118–132`.

`op=none` becomes a generic exception and is sent to the rule parser. With current cuisines `[Chinese]`, the question **"Is Italian food available?"**, and an LLM response `{"op":"none"}`, `parse_any` produces an **add Italian** update from rules.

**Fix / acceptance:** represent no-change separately from malformed replies, service errors, and ambiguous updates. An explicit no-change result must not trigger reinterpretation as a mutation. Test questions, acknowledgments, and unsupported compound updates.

### N4 — P2: schema validation and fallback do not safely handle off-template input

**Locations:** `taskflow/agents/tracker.py:36–52,79–110`; `taskflow/env/episode.py:31–37`.

- `What room type do we have?` raises `IndexError` in rules.
- `Choose restaurants rated highly.` raises `AttributeError` in rules.
- These exceptions escape the environment, which catches only `ValueError`. They also occur when the LLM is unavailable and fallback is used.
- `validate(replace house_rule pets → visitors)` accepts the combination, but `ConstraintDiff.apply` retains pets and adds visitors. The prompt prohibits this replacement, but the validator does not enforce that contract.

**Fix / acceptance:** validate an explicit operation/type matrix and old-value semantics; return a typed no-change/clarification outcome for incomplete input. Guard regex matches before indexing. Test malformed JSON, missing values, nonfinite budgets, and unsupported operations, not only the fake backend's template replies.

### N5 — P1: LLM and learned coordinators do not receive equivalent observations

**Locations:** `taskflow/coordinators/llm_coordinator.py:23–45`; `taskflow/learning/encode.py:59–76`.

The MLP observes candidate-derived minimum prices, empty candidate lists, cuisine availability, and restaurant-count hints. The LLM summary contains freshness flags but none of these candidate facts. Replacing the accommodation candidate list with an empty list, while preserving its freshness key, leaves the LLM summary identical but changes three MLP features. The module's "same information" claim is false. This especially affects cheap infeasibility detection.

**Fix / acceptance:** build a common observable-state representation and expose the same candidate evidence to both policies. Test that meaningful candidate changes affect both observations. Do not add oracle feasibility labels as a shortcut.

### N6 — P2: the meal agent receives a zero budget and accepts an unaffordable replacement

**Locations:** `taskflow/agents/planners.py:119–132`; `taskflow/agents/llm_planners.py:60–82`.

Local replanning calculates the remaining budget but does not pass it to the meal wrapper. The prompt receives `budget_left=0.0`; validation checks names, cuisine, and rating but not cost. A stub selecting valid expensive shortlist entries changed a valid **1388-cost plan with budget 1389** into a **1746-cost invalid plan**.

**Fix / acceptance:** pass the remaining group budget and enforce it when an affordable valid fallback exists. Include a test where both cheap valid and expensive valid-name responses are available. Keep error reporting explicit when no affordable choice exists.

### N7 — P2: run identity and output paths can overwrite unrelated experiments

**Locations:** `scripts/evaluate.py:103–112,142–146`; `scripts/train.py:42–48,64–69`.

All models/endpoints/temperatures for a provider write to `results/llm-<provider>/`. Evaluation manifests omit model suffix, skip-recovery, temperature, endpoint, prompt/source fingerprint, and input model/data fingerprints. An offline `--model-suffix _llmteacher` evaluation writes to the canonical offline result path. With no provider configured, `make evaluate-llm` can perform a limited offline evaluation and overwrite the full offline results. Teacher training manifests do not record teacher model identity.

**Fix / acceptance:** use explicit run IDs/output paths and complete config manifests. Keep canonical results opt-in. Require a non-offline backend for the named LLM target. Verify suffix/temperature/endpoint changes produce distinguishable artifacts.

### N8 — P2: the existing privileged oracle is not an execution-valid upper bound in LLM mode

**Locations:** `taskflow/coordinators/oracle.py:25–43,53–78`; `taskflow/env/episode.py:63–71`; `taskflow/agents/planners.py:108–134`.

The oracle tests deterministic repairs, but the environment executes LLM-backed repairs. A valid LLM choice can differ from the simulated choice; the meal counterexample in N6 demonstrates this possibility. The prior guarantee that oracle-returned sequences execute successfully applies only to the deterministic environment. `--teacher llm` also labels trajectories in a deterministic environment because `collect` does not pass an LLM client to `run_episode`; document this train/evaluation environment difference explicitly.

**Fix / acceptance:** define the oracle's scope, or validate it against the same action transition implementation. Do not label it an LLM-mode upper bound without evidence. Use a divergent but schema-valid stub to test repeated repairs and termination.

## Previous findings: still open unless noted

These measurements come from the completed `c8872ce` audit. Relevant implementation is unchanged except line shifts and optional LLM plumbing. Do not describe these as merely unanswered checklist questions.

| ID | Severity | Location / evidence | Required correction |
|---|---|---|---|
| O1 | P1 | `data/travelplanner.py:148`: numeric-name stripping corrupts 566 occurrences across 453 source queries; e.g. `1918 Bistro & Grill` → `Bistro & Grill`. Row counts, numeric fields, house rules passed; unexpected ground parse failures: zero. | Use structured upstream records or parse index columns explicitly. |
| O2 | P1 | `env/tools.py:123–127`: name-only lookup selects last duplicate. 78 duplicate restaurant-name groups across 63 loaded queries. `test-0041`: local cost 592 vs upstream 668, budget 600, due to duplicate Cafe Coffee Day records. | Stable identities and consistent resolution/export policy. |
| O3 | P1 | `env/verifier.py:98–112`: missing mandatory meals/attractions accepted. Adapted upstream function checks rejected 48/624 passing oracle test turns: 41 completeness, 4 budget, 3 cuisine. | Enforce completeness and test negative plans. Official comparison used query-record adapters, not full upstream CLI. |
| O4 | P1 | `data/tasks.py:213–227`, `agents/planners.py:is_feasible`: exact search found 0/127 false-infeasible test labels requiring six meals; 39/127 with mandatory day-2 meals and optional travel meals; all 39 passed adapted upstream checks. Current verifier's more permissive rules admit 54/127. | Align completeness definitions and use exact feasibility for this small scope. |
| O5 | P1 | `env/episode.py:193`: next-turn state is assigned `truth_after`. A wrong parsed budget 3899 is silently reset to ground truth 3000 next turn. | Separate operational state from scoring truth. Now more consequential with a real tracker. |
| O6 | P2 | `coordinators/baselines.py:49–51`: static policy requires four-call global rebuild before ASK. Capped at 1/2 calls it has 0 clarification recall; revision success 75.63% versus learned 97.16%/99.33%. | Budget-aware static policy with comparable observable evidence. |
| O7 | P2 | `agents/planners.py:compose_global`, `env/episode.py` preservation: deterministic Always-Global preserved 92.26% versus sampled 32.96%, same 99.87% revision success. Budget violations exclude all cost-bearing slots. | Report deterministic control and total edit rate; define minimum necessary changes independently. |
| O8 | P2 | `env/episode.py` retention: type-wide exclusion drops unchanged Italian when Chinese is replaced, and unchanged visitors when pets is deleted. | Score intersection of surviving constraint items, without type exclusion. |
| O9 | P2 | `scripts/evaluate.py:recovery`, static history matching: selection correctly contains 184 episodes, but global injection already solves all 184, meals 41, accommodation 17. Eleven accommodation cases skip required repair after refreshed search. | Separate harmful/redundant/beneficial injections; preserve action ordering/cache dependencies. |
| O10 | P2 | `data/tasks.py` oracle-conditioned generation: all 1,532 normal oracle repairs succeeded (1,491 one-component, 41 two-component); none required global. Three corrupted components do trigger global. | Add independent multi-component scenarios; avoid claiming broad local/global learning from this distribution. |
| O11 | P2/P3 | README still says 292 episodes / 741 turns and 75% feasible updates break plans. Actual held-out set: 296 / 751; oracle broken feasible starts: 377/624 = 60.4%. Set-B phrasing is handwritten into tracker. | Generate counts from metrics; distinguish template compatibility from language robustness. STATUS now acknowledges the phrasing limitation, but not all claims are corrected. |
| O12 | P3 | `common.py:git_sha` already reads current HEAD. New committed metrics say `c8872ce`, despite incorporating then-uncommitted LLM plumbing. | Record dirty state and content fingerprints; do not infer source identity from HEAD alone. |

Split hygiene previously passed: train 211 queries / 844 episodes, validation 67 / 268, test 74 / 296; no cross-split query IDs; A/length ≤3 only in train/validation and B/length 4 held out. No available development log proves historical hyperparameter/prompt decisions avoided test results. Current STATUS's recommendation to iterate prompts on test episodes should instead use validation episodes.

## Response log

Append reviewed commit, IDs addressed, tests run, changed-result explanation, and remaining limitations here. The reviewer will verify fixes against the evidence above before closing findings.

| Commit | IDs | Verification | Status |
|---|---|---|---|
| `ff4562a` | Initial follow-up review | 25 existing tests pass; full offline metrics reproduce; 40-episode fake evaluation completes; adversarial stubs reproduce N1–N6 | Changes requested |
| (this commit) | N1–N7, O1–O3, O5–O9, O11, O12 fixed or mitigated; O4, O10, N8 partly; see the table below | `make test` → 57 passed (32 new in `tests/test_review_fixes.py`); `docs/review/llm_regressions_after_fixes.py` → `llm_regressions_after_fixes.json`; dataset rebuilt, 3 seeds retrained, `make evaluate`, `make evaluate-capped`, fake-LLM validation run | Ready for re-review |

### Implementer response (per finding)

Data, models and results were regenerated together after the definition changes. Test split is now 69 queries / 276 episodes / 689 turns (completeness and parser fixes change feasibility labels). Old numbers in earlier commits are superseded.

| ID | Status | What changed | Regression test / evidence |
|---|---|---|---|
| N1 | fixed | Cache key includes the normalized endpoint; cache records and run manifests carry `endpoint`. | `test_n1_cache_isolated_per_endpoint`; diagnostic `endpoint_cache_collision` now returns server B. |
| N2 | fixed | `LLMFatalError` for HTTP 400/401/403/404 and configuration errors, never swallowed by fallbacks. Recoverable failures are counted per component and reason (`usage.fallbacks`, `fallback_reasons`); billed vs logical tokens split; per-system usage table and a DEGRADED banner in LLM-mode reports. | `test_n2_auth_failure_aborts_instead_of_silent_fallback`, `test_n2_transient_failures_are_counted_as_fallbacks`; diagnostic `auth_failure: aborted`, `all_api_calls_fail.usage.degraded: true`. |
| N3 | fixed | `op: none` returns `(None, "llm-none")`; rules are not consulted. The environment keeps constraints unchanged. | `test_n3_no_update_is_not_reinterpreted`, `test_n3_env_keeps_constraints_on_no_update`. |
| N4 | fixed | Rule parser guards both crash sites and raises only `ValueError`; environment records `unparsed`. Validator enforces an op/type matrix (`ALLOWED_OPS`), current-state old values, finite numbers, and no-op detection. | `test_n4_*` (16 parametrized cases incl. house-rule replace, NaN/inf budget). |
| N5 | fixed | `candidate_evidence(env)` is the single source for both the MLP features and the LLM summary (`candidate_evidence` key). | `test_n5_candidate_changes_reach_both_observations`. |
| N6 | fixed | Local meal re-plan passes the remaining budget; the validator rejects an over-budget pick when the default is affordable. | `test_n6_meal_agent_respects_budget`; diagnostic `meals_budget.new_valid: true`. |
| N7 | fixed | Output goes to `results/runs/<split>-<backend>[-capN][-suffix]-<hash>/`; only `--canonical` (full offline test run) writes `results/`. `--require-llm` used by `make evaluate-llm`, which now targets the validation split. Manifests record suffix, cap, skip-recovery, LLM identity (provider, model, endpoint, temperature), and fingerprints of source, prompts, tasks and model weights. Training manifests record teacher identity and collection environment. | Manual: `make evaluate-capped`, `--llm fake --split val`; see manifests under `results/runs/`. |
| N8 | partly | Documented: the oracle simulates deterministic planners; in LLM-mode reports it is labelled "not an upper bound here". `train.py --teacher llm` documents that collection uses deterministic planners. Not done: validating oracle sequences against LLM-backed transitions. | Handoff H3. |
| O1 | fixed | Index column detected from layout (all 7,449 tables classified: 90 indexed, all multi-row) and removed by width; names starting with digits preserved (102 such names). | `test_o1_*`. |
| O2 | fixed | A name identifies one record: first occurrence kept (upstream resolution), later duplicates dropped (`CityDB.dropped_duplicates`). | `test_o1_o2_loaded_names`. |
| O3 | fixed (definition) | Verifier requires all 13 slots (`incomplete` violation); documented as stricter than upstream. Annotated-plan test runs with `require_complete=False`. | `test_o3_missing_meal_or_attraction_rejected`. |
| O4 | partly | Feasibility labels now use the same all-slots completeness definition the review's exact search found consistent (0/127 false-infeasible). Not re-run after the parser fixes. | Handoff H1. |
| O5 | fixed | The system's own belief carries between turns; truth is only for scoring. ASK on an infeasible update reverts the belief; otherwise the tracked constraints persist. | `test_o5_wrong_parse_is_not_silently_corrected`. |
| O6 | fixed | Static rules refresh stale searches and ask on observable evidence (shared `candidate_evidence`) before trying one global rebuild. `--call-cap N` for matched-budget runs (`BUDGET_EXHAUSTED` terminal). At cap 1: static 72.4% vs learned 96.9–98.1% revision success; cap 2: 98.1% vs 98.5–100%. | `test_o6_call_cap_ends_turn`; `results/runs/test-offline-cap{1,2}-*`. |
| O7 | fixed | `always_global_det` control (31.3% vs 93.1% preserved) and an `edit_rate` metric (all slots). README states the dependency. Preservation definition for budget turns is unchanged (documented). | `results/REPORT.md`. |
| O8 | fixed | Retention scores the intersection of items before and after the update, no type exclusion. | `test_o8_retention_keeps_same_type_items`. |
| O9 | fixed | Recovery reports all cases and the subset where the forced action left the plan broken (`needs_recovery_n`, `needs_recovery_success`); global injections show n=0. Static rules match their script as an ordered subsequence. | `test_o9_injected_replan_before_search_does_not_skip_script`; REPORT recovery table. |
| O10 | open | Claims moderated in README ("results show when to repair locally and when to ask, not a learned local-vs-global trade-off"). Generator unchanged. | Handoff H2. |
| O11 | fixed | README counts and rates regenerated from `results/metrics.json` (276/689; 63% plan-breaking; 19% infeasible). Template-set B described as template compatibility, not paraphrase robustness. STATUS/LLM_SETUP now say to develop prompts on validation. | README, STATUS. |
| O12 | fixed | Manifests add `git_dirty` and content fingerprints. | `results/metrics.json` manifest. |

### Handoff: items for the reviewer

| ID | Task | Why not done here |
|---|---|---|
| H1 (O3/O4) | Re-run the adapted upstream checks and the exact feasibility search on the regenerated `data/tasks/v0` (fingerprint in `results/metrics.json`). Confirm the earlier 4 budget / 3 cuisine upstream rejections are gone after O1/O2. | Needs the reviewer's upstream adapters, which are not in the repo. Please commit them under `docs/review/` or `tests/` if possible. |
| H2 (O10) | Design and add independent multi-component scenarios (e.g. a single update that invalidates two components, or chained cuts that exhaust local slack) so a global rebuild is sometimes necessary; then report whether the learned coordinator learns when to go global. | A generator design decision for the team; changes the benchmark distribution. |
| H3 (N8) | Validate oracle sequences against LLM-backed transitions with a divergent but schema-valid stub (repeated repairs, termination), or keep the oracle restricted to deterministic mode. | Needs a design choice on what the oracle means in LLM mode. |
| H4 | First live-provider smoke test on validation episodes (`make evaluate-llm`), logging fallbacks and raw outputs. | No API key in this environment. |
| H5 | Preservation definition for budget turns (all costed slots are "affected"): propose and implement a minimum-necessary-change definition. | Definition choice; `edit_rate` added meanwhile. |

### Reviewer response to H1–H5 (2026-11-13)

| ID | Status | Delivered / remaining work |
|---|---|---|
| H1 | Audit complete; upstream differences documented | Repository adapters and exact solver; all 2,957 labels agree; all 560 passing test plans pass adapted upstream checks. Three test cost differences and seven train/validation entity rejections remain (substring matching and escaped newlines). No claim of full database parity. |
| H2 | Stress suite complete; current model limitation confirmed | 12 independent synthetic budget revisions requiring 1/2/3 component repairs; existing learned models fail all 2/3-component cases, while baselines/expert solve them. Global is required only relative to the expert's bounded two-local-repair search, not the complete action space. No benchmark retraining or test contamination. |
| H3 | Decision implemented | Scripted expert is deterministic-only, excluded from live registries and live expert-disagreement labels; incompatible direct use raises. LLM teacher is a fallible demonstrator. |
| H4 | Deferred by user | Teammates configure credentials and run the documented validation smoke command. No API calls made. |
| H5 | Implemented and evaluated | Exact minimum slot substitutions, excess edits, and edit-optimal preservation; failed plans get no stability credit. Full three-seed evaluation preserves all earlier summary values and writes a separate run. |

Implementer next steps: normalize/export escaped-name identities and document upstream substring resolution; develop a separate multi-component training distribution without training on the committed stress cases; have a teammate run H4 on validation data. Do not overwrite canonical metrics until any behavioral/data changes are regenerated and verified together.

### Implementer response to the H1–H5 results

| Item | Status | What changed | Evidence |
|---|---|---|---|
| H1 escaped names | fixed | The parser restores literal `\n` in entity names to a real newline (24 records), matching upstream structured records; demos print it as " / ". v0 task counts and labels unchanged. | `make test`; `data/tasks/v0/manifest.json` stats identical to before. Re-running `docs/review/audit_regenerated.py` against upstream should now show 0 entity rejections; not re-run here because it needs the upstream checkout. |
| H1 substring matching | documented | Exact name matching kept on purpose; the "Pizza Hut" vs "Pizza Hut Delivery" difference is documented in `LICENSES.md`. | `LICENSES.md`. |
| H2 training distribution | done | New family `make_multi_episode` (`taskflow/data/tasks.py`): real trips from each split, an approved expensive itinerary, then a budget cut needing 1, 2, or 3+ component repairs (3+ = beyond the expert's two-repair search). Separate files `train_multi` / `val_multi` / `test_multi` and a separate RNG, so v0 is unchanged. Training uses `train` + `train_multi` (`--no-multi` to disable). The fixed synthetic stress suite is never trained on. | `tests/test_multi.py` (split hygiene, no synthetic ids, expert solves every episode). Stress suite: BC+aug+DAgger(3) now 12/12 for each seed (was 4/0/0, 0/0/0, 4/0/0). `test_multi`: 100% success, 1.91 excess edits vs 5.88 for static rules and 1.75 for the expert; global-rebuild rate 23% vs expert 20%. |
| Canonical results | regenerated | Models retrained (3 seeds) with the new family; `results/`, capped runs, `results/runs/test-multi`, `results/runs/challenges`, fake validation smoke regenerated. | `make pipeline`. |
| H4 | open (teammates) | Unchanged. | — |

Open for the next review:
- The multi-component family only contains budget cuts.
- The stress suite uses one fixed synthetic layout, so passing it isn't evidence of general multi-component skill.
- H1's upstream audit has not been re-run after the name fix.
- `results/runs/handoff-offline` and `results/runs/handoff-fake-val` are the reviewer's runs at `1aaeecd`, made with the models from before retraining. They are kept as an audit trail; current numbers are in `results/` and the other `results/runs/*` folders (all recorded at a clean commit).

### Implementer update: interactive app and robustness fixes

| Item | What changed | Evidence |
|---|---|---|
| Interactive app | `scripts/app.py` (`make app`): any of 257 start cities and 220 destinations from a merged database (`taskflow/data/world.py`). Flights only where TravelPlanner has them; driving/taxi for other routes estimated from city coordinates with per-km rates fitted to the data (road factor 1.18, $0.05/km, $1/km, 107 km/h), labelled "estimated" in the UI. | `tests/test_app.py` |
| Out-of-range budgets | The app exposed a learned-policy failure: a $200 budget for a $1,650 trip made it repeat REPLAN_GLOBAL until timeout. Fixes: (1) cost-ratio features clipped at 10; (2) action mask forbids repeating the previous re-plan/search back to back (the expert never does: 0/2,140 turns); (3) the multi family adds impossible cuts at 20–85% of the cheapest trip (correct response: ask) and feasible cuts at 1.05–1.5× the cheapest trip, so "far over budget" and "impossible" are separated only by the cost lower bound. | `test_app.py::test_trip_and_revisions`; stress suite 12/12 for all seeds; canonical metrics regenerated |
| Visual replay | `scripts/demo_html.py` (`make demo-html`, `make demo-html-multi`). | — |

For the next review: the distance-based estimates for routes without driving/taxi records are app-only (not used in any benchmark number). Check that the multi family's new level mix (0: 41, 1: 96, 2: 148, 3: 145 in train) does not bias the comparison.

