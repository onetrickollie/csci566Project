# H1–H5 handoff results

Reviewer implementation and audit, 2026-11-13. Input baseline: `1aaeecd`.
H4 is explicitly deferred to teammates at the user's request. No live API calls were made.
Canonical data, trained weights, and `results/metrics.json` remain unchanged.

Verification: **66 tests passed**, including nine handoff regressions; full three-seed offline evaluation and a two-episode fake validation run completed. Stored source fingerprints match the final implementation. Results honestly record a dirty working tree at execution time; they are not labelled as a clean-commit run.

## H1 — reproducible audits delivered; exact labels pass, some upstream differences remain

The audit tooling is now in this repository:

- `docs/review/upstream_adapter.py`: pinned upstream function adapter and plan exporter.
- `docs/review/audit_regenerated.py`: runs exact feasibility on every turn and upstream checks on passing expert plans.
- `taskflow/eval/exact.py`: independent dynamic-programming solver; no greedy planner calls.
- `docs/review/handoff/h1_audit.json`: complete counts, source/data fingerprints, and disagreements.

| Split | Turns checked | Labeled infeasible | Exact label disagreements | Passing plans checked upstream | Upstream rejections | Cost differences |
|---|---:|---:|---:|---:|---:|---:|
| Train | 1,710 | 317 | 0 | 1,393 | 3 | 7 |
| Validation | 558 | 92 | 0 | 466 | 4 | 6 |
| Test | 689 | 129 | 0 | 560 | 0 | 3 |

All **2,957** labels agree with exact search under the current **13 mandatory slots** definition. All 538 infeasible labels are confirmed under that definition. No oracle turn failed locally. The prior budget/cuisine upstream rejections are gone; full parity is not established:

- Test's three cost differences are all `validation-0008` (source query ID), where upstream substring matching selects **Pizza Hut Delivery (76)** for **Pizza Hut (61)**. Both evaluators still pass the plans. Exact-name matching is reasonable locally; document this upstream mismatch rather than silently aliasing two different restaurants.
- Seven train/validation plans fail upstream entity lookup because the table representation retains literal `\\n` in hotel names, whereas structured upstream records contain a newline. Examples: source queries `test-0005` and `validation-0069`. This remains an export/parser normalization issue for the implementer; O1/O2 are not complete upstream-compatibility guarantees.

**Adapter limitations:** executes the unmodified function definitions from upstream commit `e52c87f4ac348a3410c46dc3553c519db5ec5e23`, using official structured query slices in place of the full global database. Ground costs are parsed independently from the structured reference strings. The city map contains supplied query cities; only three-day single-city trips are supported. This is not the upstream CLI or leaderboard. Additional project constraints (rating and priority) are verified locally, not by upstream. Exact search proves feasibility within the parsed local database, not physical travel realism.

Reproduce from the repository root (review dependencies are optional and separate from production requirements):

```bash
git clone https://github.com/OSU-NLP-Group/TravelPlanner.git /tmp/taskflow-upstream
git -C /tmp/taskflow-upstream checkout e52c87f4ac348a3410c46dc3553c519db5ec5e23
.venv/bin/pip install -r docs/review/requirements.txt
.venv/bin/python docs/review/audit_regenerated.py \
  --upstream /tmp/taskflow-upstream --seed 0 \
  --out /tmp/taskflow-h1.json
```

The adapter refuses a different revision or modified upstream evaluator/data files. It does not vendor upstream source or datasets.

## H2 — independent multi-component stress suite added

`taskflow/data/challenges.py` constructs **12 synthetic, valid initial itineraries** independently of the expert's trajectory: four cases each requiring at least one, two, or three component repairs after a single budget cut. They use expensive user-approved initial choices and independently chosen cheaper alternatives. Their seed is fixed; they are separate from v0 and must not be presented as new TravelPlanner test queries.

A global rebuild is **not uniquely necessary in the full action space**: three local repairs can also solve the hardest cases. The relevant property is that **no sequence of one or two local component repairs succeeds**, so the current scripted expert correctly takes its global fallback. Making global rebuilding mathematically mandatory would require changing action semantics or budgets; we did neither.

Existing pretrained policy results, successes out of four cases per level:

| Policy | One component | Two components | Three components |
|---|---:|---:|---:|
| Always-Global, deterministic global, static rules, scripted expert | 4 | 4 | 4 |
| BC+augmentation+DAgger3, seed 0 | 4 | 0 | 0 |
| BC+augmentation+DAgger3, seed 1 | 0 | 0 | 0 |
| BC+augmentation+DAgger3, seed 2 | 4 | 0 | 0 |

The existing models **have not learned this broader coordination behavior**. These are out-of-distribution diagnostic results, not new training results or a fair estimate of natural-query prevalence. Keep this suite fixed for regression testing. If the team trains on multi-component scenarios next, generate a separate development/training family and hold these cases out.

```bash
.venv/bin/python scripts/evaluate_challenges.py --seed 0 --seeds 0 1 2 \
  --out /tmp/taskflow-h2.json
```

Per-case actions, termination, exact edits, and outcome: `docs/review/handoff/h2_challenges.json`.

## H3 — deterministic expert only; enforced in code

Decision: **the scripted expert is restricted to deterministic component transitions**. It is not an LLM-mode policy or an optimality upper bound, even offline (its local search is bounded and planners are greedy).

- `Oracle.act` rejects an environment with LLM-backed agents before executing a repair.
- Live/fake LLM policy registries omit this expert; demos reject an explicit incompatible selection with a clear message.
- Evaluation skips deterministic-expert disagreement labels in LLM mode and reports deterministic-only unnecessary-global scoring as unavailable there.
- Reports use "Deterministic scripted expert" rather than "upper bound".
- `LLMCoordinator` remains a **fallible teacher**. Existing `train.py --teacher llm` labels trajectories collected with deterministic agents; it does not imply training on live-agent transitions. That environment difference must be preserved in interpretation and manifests.

A fake-LLM validation run (2 episodes / 6 turns) verifies the allowed paths still execute after the restriction. It is wiring validation only, not a replacement for H4.

## H4 — teammate-owned, not blocking today's offline work

The user explicitly deferred the live-provider test. Environment inspection found no configured provider/model/API key/local endpoint. Credentials were not displayed or requested in chat.

After a teammate configures `.env` locally, begin with one validation episode, review the report and fallback log, then expand:

```bash
.venv/bin/python scripts/evaluate.py --require-llm --split val --limit 1 \
  --seeds 0 --skip-recovery --out results/runs/live-val-smoke-1
```

This command evaluates multiple systems, so one episode is still multiple requests. Review raw responses under `cache/llm/`, `llm_usage_total`, per-system usage/fallbacks, and any DEGRADED banner. Do not tune prompts on the test split. Fake counts are not dollar-cost measurements.

## H5 — exact minimum necessary edits implemented

The old "unaffected" set is not uniquely defined for a global budget constraint: several different equally small repairs may work. We therefore measure a **number of necessary edits**, rather than declaring every costed slot affected.

Let `N=13`, `m` be the exact minimum number of slot substitutions needed to produce any complete valid plan under the revised constraints, and `a` be the actual number of changed slots:

- `minimum_edits = m`
- `excess_edits = a - m`
- `edit_optimal_preservation = 1 - (a - m)/(N - m)`

If all 13 slots must change, preservation is undefined, while excess edits remains defined. Failed turns do not receive stability credit: these values are null. Reports include successful scored-turn counts and must be read alongside revision success, preventing a policy that keeps an invalid plan from looking maximally stable. Priorities, cuisines, group travel costs, accommodation capacity, unique meals/attractions, and all mandatory slots are included. The objective is minimum edits first, cost second.

The solver exhausts transport pairs and hotels and uses exact DP over meal count, cuisine coverage, and retained meal assignments. Attraction retention is solved independently because attractions have no cost or preference constraints in v0. This is **exact only for the current schema**; future timing/multi-city/attraction-preference constraints require extending it.

Scoring runs **after** policy execution and is not provided to policies or training encoders. Training collection leaves this optional computation off. Full evaluation enables it. Existing legacy preservation and edit-rate fields are retained and labelled for historical comparison.

Full test evaluation (three training seeds; successful feasible turns only):

| System | Mean excess edits | Edit-optimal preservation |
|---|---:|---:|
| Always-Global, sampled | 8.223 | 30.00% |
| Always-Global, deterministic | 1.525 | 86.89% |
| Static rules | 1.205 | 89.04% |
| BC+augmentation+DAgger3 | 1.159 | 89.65% |
| Deterministic scripted expert | 1.159 | 89.65% |

On the 28 feasible budget turns, learned seed 0 and scripted expert score **98.70%**, versus **100%** under the old metric, because avoidable costed-slot changes now count. Policies can have different starting itineraries, so each optimum is relative to its own actual pre-update plan; these are not matched-state causal estimates.

Results: `results/runs/handoff-offline/REPORT.md` and `metrics.json`; per-update-type exact metrics are in `by_type`. Every pre-existing summary metric equals the canonical result exactly. No models were retrained and no canonical result file was overwritten.

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/evaluate.py --llm offline --seeds 0 1 2 --skip-recovery \
  --out results/runs/handoff-offline
```

`tests/test_handoff.py` independently brute-forces restaurant assignments to check the exact solver, covers cuisine/duplicate-name retention and impossible cases, proves the component-repair thresholds, tests failed-plan/all-slots-change scoring, and checks the expert restriction. Recovery was not rerun for this handoff; the new scoring does not affect transition behavior.
