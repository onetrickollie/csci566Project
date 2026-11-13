# Supervisor review of the latest progress

Reviewed 2026-11-13: production source at `025b2bb`, followed during review by `cf78ea1` (result manifests only). This is a code, data, model and API-behavior review; browser layout and real-provider behavior were not tested. H4 remains assigned to teammates. No live API calls were made. Existing result edits/deletions at review start were left untouched; the implementer subsequently committed regenerated results.

## Findings for the implementer, in priority order

### R1 — P1: impossible ground routes are presented as valid trips

`taskflow/data/world.py:93–98` estimates driving/taxi whenever both cities have coordinates, without checking road connectivity or travel time. `scripts/app.py:164–181` accepts the ordinary verifier result as trip validity. Reproduction: Los Angeles → Honolulu, March 10, 2 people, $10,000, no flight produces a **valid self-driving itinerary**, 4,843 km / 45h14m each way. New York → Seattle similarly yields 42h32m each way in a three-day itinerary that still includes all meals/attractions. Even ignoring the ocean, round-trip travel alone exceeds the 72-hour trip. An “estimated” label does not fix an impossible route.

**Fix:** restrict estimated ground options to supported road-connected routes, reject transport that cannot fit the itinerary, and distinguish benchmark constraint validity from real schedule feasibility in the app. Keep app-only route changes out of benchmark data. Add ocean-crossing and overlong-route tests.

### R2 — P2: asking is automatically counted as successful handling

`scripts/app.py:209–220` rolls back every ASK and increments `ok` with `asked or view['valid']`; the page additionally asserts that the change cannot be met. Reproduction uses an explicit always-ASK test double (not a claim that current trained weights always ask): on an already valid Chicago → Seattle $3,000 trip, ask to increase the budget to $4,000. All four cards report **1/1 changes handled**, keep $3,000, and assert impossibility despite the old plan satisfying the increase. This hides coordinator errors and differs from the benchmark's treatment of unnecessary ASK.

**Fix:** treat ASK as pending clarification rather than evidence of infeasibility or success. If an offline scoring badge is desired, use independent feasibility checking for scoring only; do not expose it to policies. Do not silently equate a model's refusal with a user withdrawing the update. Test an unnecessary ASK on a feasible revision.

### R3 — P2: multi-family recovery selection uses the wrong initial plan

`scripts/evaluate.py:54–59,74–80` reconstructs the cheap default itinerary rather than `ep.initial_plan`, while the episode runner correctly uses the approved expensive itinerary. Reproduction: all **127 feasible test_multi turns** break their initial approved plan, but `needs_repair_first_turn` selects only **33**. The post-injection recovery classification uses the same wrong start.

**Fix:** share the episode initialization semantics with both recovery helpers, including cache initialization, then compare injected plans to actual rollouts. The committed multi evaluation uses `--skip-recovery`, so its reported success/edit metrics are unaffected; a normal `evaluate.py --split test_multi` is affected.

### R4 — P2: non-finite budgets bypass the app's budget check

`scripts/app.py:147–152` accepts `float('NaN')` and `float('Infinity')`. Direct JSON API calls with either string create a session and report a valid itinerary (`budget $nan` / `budget $inf`), because comparisons to NaN do not produce a budget violation. The normal number input limits ordinary UI exposure but is not API validation.

**Fix:** require finite positive budget, validate the actual date and supported enum values, and return a clear client error. Add NaN/infinity API tests.

### R5 — P3: return-ground details display the outbound record

`scripts/app.py:87–106` finds the first ground record with the mode, ignoring direction. Kansas City → Pensacola self-driving costs $71 outbound and $72 return in the query, but the itinerary displays $71 and the outbound distance/duration for both legs. Verification uses the correct directional records, so this is a display discrepancy.

**Fix:** pass the slot/direction into `transport_label` and resolve `(mode, origin, destination)` exactly. Test asymmetric recorded ground routes.

### R6 — P3: status text is stale and overstates global necessity

`docs/STATUS.md` still says the new learned model fails multi-component cases, asks to rerun completed H1/H3/H5 work, and describes global rebuilds as necessary without the two-local-repair qualification. README's final caveats also say the post-parser feasibility audit remains outstanding and describe upstream verification as annotated-plans-only. The detailed response log is more accurate than these summaries.

**Fix:** align the top-level summaries with the verified results below. Say “global beyond the expert's two-local-repair search,” not “globally necessary in the full action space.” Describe the upstream adapter scope honestly; it is not the complete official CLI/database.

## Verified progress

- **72 tests pass.** Production code was not refactored or changed during this review.
- Dataset rebuild with seed 0 reproduces all six committed JSONL files byte for byte, including all three multi-family splits.
- Exact independent checks agree with all **2,957 v0** feasibility labels and all **710 multi** labels. All multi initial plans are valid; the scripted expert succeeds on every multi episode across all splits.
- v0 adapted upstream checks: **zero rejected passing plans** (train 1,393; validation 466; test 560). The escaped-newline entity issue is closed. Nine cost differences remain (4/2/3 across splits), consistent with the documented substring-resolution difference; no upstream acceptance failures.
- Full three-seed v0 evaluation exactly reproduces **all saved system results**, including recovery and error-by-step, not just rounded headline figures. Learned combined revision success is 99.7097%, versus 100% static/expert.
- Three-seed multi evaluation exactly reproduces all saved system results: learned 100% revision success, 1.7428 excess edits, 31.6425% global rebuilds, 2.3454 simulated LLM calls/turn.
- Fixed synthetic challenge evaluation was rerun separately; see `latest/challenges.json`.

- Independent three-seed retraining reproduces **all 18 model state dictionaries exactly**. Training logs also match except wall-clock duration. Rebuilt weights were written under `/tmp`, never over the production models.
- Both matched-call-budget evaluations (caps 1 and 2, three seeds) reproduce every saved system result exactly.
- Multi-family adapted upstream checks accept all **635 passing plans** (389/119/127). Two substring-related cost discrepancies remain (one train, one test); no label disagreements or failed expert turns.
- A fresh-cache fake-backend validation smoke completes with 55 fake backend calls, 106 cache hits, zero errors/fallbacks, and no deterministic oracle in the live registry. These are simulated calls, not provider requests or real billing.
- All three learned seeds pass **12/12** fixed synthetic challenges.

Machine-readable comparisons and result summaries are in `latest/reproduction.json`; multi upstream evidence is in `latest/upstream_multi.json`. Across both task families, all **3,667 feasibility labels** agree with exact search and all **3,054 passing expert plans** pass the adapted upstream checks.

## Validity and next work

The multi-family training addition is a real improvement: it is separated from the fixed synthetic cases and query splits are preserved. But it remains one-turn budget cuts from extreme expensive plans. Its difficulty levels are chosen using `minimal_fix`, the same bounded scripted expert that supplies labels. Thus it measures imitation of this expert's decision boundary, not independently established necessity of global replanning. Passing a repeatedly inspected fixed stress suite is a regression result, not an untouched final holdout.

The 430/142/138 multi splits have level counts 0/1/2/3 of 41/96/148/145, 23/28/46/45, and 11/30/54/43 respectively. This is an intentional weighting, not cross-split query leakage. Report level-conditioned performance and a stronger cost-aware static repair baseline before attributing the entire advantage to learned coordination: the present static policy only tries accommodation before global repair. Freeze the next evaluation set before further tuning; add non-budget multi-component updates and multi-turn sequences developed on train/validation.

The new action mask forbids immediately repeated replans. This is sensible for deterministic local planners, but repeated sampled/global or LLM calls are not guaranteed idempotent. Document the mask as a restriction on the learned policy and revisit it during H4; the current offline checks do not validate retry behavior with real LLM agents.

**Suggested production order:** R1 and R2 first; R3–R5 with small regression tests; synchronize docs; then strengthen the baseline and held-out scenarios. Teammates continue H4 independently.

## Reproduction

Run from the repository root. All evaluation output is isolated from canonical results.

```bash
.venv/bin/python -m pytest -q
.venv/bin/python docs/review/latest/check_progress.py
PYTHONPATH=/tmp/taskflow-audit/deps .venv/bin/python docs/review/audit_regenerated.py \
  --upstream /tmp/taskflow-official-travelplanner --out docs/review/latest/upstream.json
PYTHONPATH=/tmp/taskflow-audit/deps .venv/bin/python docs/review/audit_regenerated.py \
  --upstream /tmp/taskflow-official-travelplanner --splits train_multi val_multi test_multi \
  --out docs/review/latest/upstream_multi.json
.venv/bin/python scripts/build_dataset.py --seed 0 --out /tmp/taskflow-review-latest/data
.venv/bin/python scripts/evaluate.py --llm offline --seeds 0 1 2 --out /tmp/taskflow-review-latest/test
.venv/bin/python scripts/evaluate.py --llm offline --split test_multi --seeds 0 1 2 --skip-recovery --out /tmp/taskflow-review-latest/multi
.venv/bin/python scripts/evaluate.py --llm offline --call-cap 1 --seeds 0 1 2 --out /tmp/taskflow-review-latest/cap1
.venv/bin/python scripts/evaluate.py --llm offline --call-cap 2 --seeds 0 1 2 --out /tmp/taskflow-review-latest/cap2
.venv/bin/python scripts/evaluate.py --llm fake --split val --limit 2 --seeds 0 --skip-recovery --out /tmp/taskflow-review-latest/fake
.venv/bin/python scripts/evaluate_challenges.py --seeds 0 1 2 --out docs/review/latest/challenges.json
```

Upstream checkout/dependency setup is documented in `HANDOFF_RESULTS.md`. The existing audit CLI was extended to accept multi splits. App edge cases and all multi feasibility checks are reproducible using `latest/check_progress.py`; raw evidence is in `latest/checks.json`. The always-ASK stub is deliberately injected to test scoring behavior, not used in benchmark results.

To reproduce training without replacing production weights:

```bash
.venv/bin/python - <<'PYTHON'
import sys
from pathlib import Path
sys.path.insert(0, 'scripts')
import train
train.MODELS_DIR = Path('/tmp/taskflow-review-latest/models')
sys.argv = ['train', '--seeds', '0', '1', '2']
train.main()
PYTHON
```

For a fresh-cache fake smoke, import `evaluate` from `scripts`, set `taskflow.llm.client.CACHE_DIR` to `/tmp/taskflow-review-latest/fresh-fake-cache`, and invoke `evaluate.main()` with the fake-smoke arguments above and output `.../fake-fresh`. Then run `.venv/bin/python docs/review/latest/compare_reproduction.py` to produce the comparison summary. Its model comparison checks tensor equality, so serialization metadata does not mask training drift.
