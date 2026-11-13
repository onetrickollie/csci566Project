"""H1: independent exact feasibility + pinned upstream comparisons on regenerated data."""
from __future__ import annotations
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from taskflow.common import ROOT, TASKS_DIR, fingerprint, manifest, query_index
from taskflow.coordinators.oracle import Oracle
from taskflow.data.tasks import load
from taskflow.env.episode import run_episode
from taskflow.env.state import ConstraintDiff, Constraints
from taskflow.env.verifier import verify
from taskflow.eval.exact import minimum_repair
from upstream_adapter import UpstreamAdapter, UPSTREAM_SHA


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--upstream', type=Path, required=True)
    ap.add_argument('--splits', nargs='+', choices=['train', 'val', 'test'], default=['train', 'val', 'test'])
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    queries = query_index()
    adapter = UpstreamAdapter(a.upstream, queries)
    counts, witnesses, disagreements = {}, [], []
    for split in a.splits:
        tally = Counter()
        class Inspect:
            def __init__(self):
                self.policy = Oracle()
            def act(self, env):
                action = self.policy.act(env)
                if action in ('KEEP_PLAN', 'STOP'):
                    local = verify(env.q, env.c, env.plan)
                    if not local.passed:
                        raise AssertionError('Expert terminated with invalid plan')
                    official = adapter.evaluate(env.q, env.c, env.plan)
                    tally['checked_passing_plans'] += 1
                    tally['upstream_rejections'] += bool(official['failures'])
                    tally['cost_disagreements'] += not math.isclose(local.total_cost, official['cost'])
                    tally.update(official['failures'].keys())
                    if official['failures'] or not math.isclose(local.total_cost, official['cost']):
                        disagreements.append(dict(split=split, qid=env.q.qid, constraints=env.c.to_dict(),
                                                  local_cost=local.total_cost, **official))
                return action
        for i, ep in enumerate(load(TASKS_DIR, split)):
            before = Constraints.from_dict(ep.base)
            for ti, turn in enumerate(ep.turns):
                after = ConstraintDiff.from_dict(turn.diff).apply(before)
                # Empty reference means the solver minimizes cost across all valid choices.
                answer = minimum_repair(queries[ep.qid], after, {})
                tally['turns'] += 1
                tally['labeled_infeasible'] += not turn.feasible
                if bool(answer) != turn.feasible:
                    label = 'false_infeasible' if answer else 'false_feasible'
                    tally[label] += 1
                    witnesses.append(dict(split=split, episode=ep.episode_id, turn=ti, issue=label,
                                          constraints=after.to_dict(), witness=vars(answer) if answer else None))
                before = Constraints.from_dict(turn.constraints_after)
            result = run_episode(ep, queries[ep.qid], Inspect(), seed=a.seed+i)
            tally['failed_oracle_turns'] += sum(not t.success for t in result.turns)
        for key in ('false_infeasible', 'false_feasible', 'upstream_rejections', 'cost_disagreements'):
            tally.setdefault(key, 0)
        counts[split] = dict(tally)
        print(split, counts[split], flush=True)
    result = dict(manifest=manifest(seed=a.seed, splits=a.splits, upstream_sha=UPSTREAM_SHA,
                                   audit_code=fingerprint([Path(__file__), Path(__file__).with_name('upstream_adapter.py')]),
                                   raw_data=fingerprint([ROOT / 'data/raw' / f'{s}.csv'
                                                         for s in ('train', 'validation', 'test')])),
                  scope='All 13 slots required. Upstream function adapter uses query slices, not full database/CLI; no leaderboard claim.',
                  counts=counts, label_disagreements=witnesses, upstream_disagreements=disagreements)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
