# Verification checklist and open questions

These are the parts we are least sure about, ordered by risk. Each item says what to check and where. When you settle one, record the finding (file:line, evidence, fix) in the "Log" section at the bottom.

## A. Reproduce

1. Run `make pipeline` (build → train → evaluate) and `make test`. The pipeline is deterministic, so `results/REPORT.md` should match the committed version exactly. Report any drift and its cause.

## B. Correctness (highest risk: every number depends on these)

2. **Table parser** (`taskflow/data/travelplanner.py`, `_split_table`). It slices pandas `to_string()` output by header column positions and strips the row index from restaurant names. Across all train, validation and test queries, check:
   - row counts equal the number of data lines;
   - no name has leftover characters from a neighboring column;
   - prices and ratings parse as numbers;
   - house rules are clean.

   Also count how often ground transport fails to parse, versus being genuinely unavailable.
3. **Verifier vs. the official TravelPlanner evaluator** (`taskflow/env/verifier.py`).
   - Compare the cost rules:
     - flight price × people;
     - self-driving × ceil(people/5);
     - taxi × ceil(people/4);
     - accommodation price × ceil(people/max_occupancy) × nights.
   - Compare the transport-conflict rule. We treat self-driving + flight and self-driving + taxi as conflicts.
   - Compare the room-type and house-rule mapping, and the minimum-nights check.
   - If possible, run the official evaluator on our exported plans. List the checks it has that we skip (timing, city per day, ...).
4. **Feasibility labels** (`tasks.make_episode`, `planners.is_feasible`). "Feasible" means the current plan already satisfies the update, or the greedy composer finds a plan. The greedy can miss plans that exist. On a sample of turns labeled infeasible, run an exhaustive or ILP search and report the false-infeasible rate.
5. **Oracle** (`coordinators/oracle.py`). `minimal_fix` only tries repairs of one or two components. Check:
   - every sequence it returns actually works when executed;
   - whether `REPLAN_GLOBAL` is truly never needed on feasible turns. The oracle never chooses it.

## C. Is the comparison fair?

6. **Leakage.** `learning/encode.py` must use no privileged information: no feasibility oracle and no ground truth from the episode file. Also check the action mask.
7. **Expert design.** The oracle refreshes its searches before asking for clarification, so its decision is visible to a non-privileged policy and can be imitated. Is that reasonable, and are the static rules designed with equal care?
8. **Generator bias.** Updates are chosen against the oracle's own plan trajectory, aiming for about 75% plan-breaking updates. Do other coordinators see a different mix on the same episodes? Does that favor oracle-like policies?
9. **Matched budget.** The proposal's rejection criterion is "under a comparable budget". Cap LLM calls per turn at 1 and at 2, then compare static rules with `bc_aug_dagger3`.
10. **Always-Global preservation** (33%) depends on the sampled regeneration in `compose_global(rng)`. Report preservation with `rng=None` too, and with a real LLM.

## D. Metric definitions (`env/episode.py`, `eval/metrics.py`)

11. **"Unaffected preserved"** counts the slots that start-of-turn violations don't mention. A budget violation mentions every slot that costs money, so on budget turns only the attractions are measured. Propose a fairer definition.
12. **Retention and new-constraint satisfaction.** Retention excludes constraints of the same type as the update, and new-constraint satisfaction depends on how `_diff_item` maps a diff to a constraint item. Hand-check:
    - a cuisine replacement;
    - a house-rule deletion;
    - a priority change;
    - a budget increase.
13. **ASK on a feasible turn.** The update stays applied and the plan isn't repaired, and `final_pass` requires the last turn to succeed. Confirm this matches the README.
14. **Recovery test.** Mistakes are injected only at turn 0, step 0. Check that the episode selection (`needs_repair_first_turn`) is right, and that the injected action doesn't unfairly help or hurt `StaticRules`, which matches its script against the action history.

## E. Held-out conditions and reporting

15. **Phrasing test.** The tracker and both template sets were written together, so 100% tracker accuracy on set B is weak evidence. Paraphrase test updates with an LLM (T10).
16. **Split hygiene.** Check that:
    - no query id crosses splits;
    - template set B and 4-turn chains appear only in test;
    - class weights, generator rates and oracle changes were chosen on train/val only.
17. **Recorded commit.** `results/metrics.json` records the commit that existed before the run, not the run's own commit.
18. **README numbers.** Cross-check every number quoted in README.md against `results/metrics.json`.

## F. LLM paths (not yet run against a real model)

19. Run `evaluate.py --llm <provider> --limit 30 --seeds 0 --skip-recovery`. Report:
    - the rate of fallbacks from the tracker, agents and coordinator;
    - tracker agreement with the ground-truth diffs (`tracker_accuracy`);
    - measured requests and tokens per turn.
20. Run the interactive demo and try off-template messages: multiple changes in one message, vague requests ("cheaper"), and messages that aren't updates. Record the failures.

## Log

**Supervisor review (2026-11-13, `ff4562a`):** see [SUPERVISOR_REVIEW.md](SUPERVISOR_REVIEW.md) for reproduced findings, severity, fixes, and acceptance criteria. Implementer: use that file's response log to record fixes; the listed correctness defects remain open even though the existing 25 tests pass. Prioritize scoring/data integrity and LLM failure handling before paid experiments.

| # | Date | Who | Finding | Fix / status |
|---|---|---|---|---|
| 1–18 | 2026-11-13 | reviewer | Previous full audit reproduced all metrics; confirmed parser/identity, completeness/feasibility, state-leakage, metric and comparison defects. | Open items O1–O12 in supervisor review; split hygiene and normal oracle sequences passed. |
| 19–20 | 2026-11-13 | reviewer | New LLM paths pass existing tests but adversarial stubs expose endpoint-cache collisions, silent fallback experiments, no-update mutations, parser crashes, unequal observations and meal-budget violations. | New items N1–N8 in supervisor review. No paid provider calls made. |
| N1–N7, O1–O12 | 2026-11-13 | implementer | Fixes per finding with regression tests (`tests/test_review_fixes.py`); data/models/results regenerated. | See the response table in SUPERVISOR_REVIEW.md; open: H1–H5. |
