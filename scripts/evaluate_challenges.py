"""Evaluate existing policies on synthetic revisions without retraining or changing v0."""
import argparse
import json
import random
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from taskflow.common import baseline_policies, learned_policy, manifest
from taskflow.data.challenges import budget_challenges
from taskflow.env.episode import TurnEnv
from taskflow.env.tools import Cache
from taskflow.env.verifier import verify
from taskflow.eval.exact import revision_efficiency


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--seeds', type=int, nargs='+', default=[0, 1, 2])
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    cases = budget_challenges(a.seed)
    policies = baseline_policies()
    for s in a.seeds:
        policies[f'bc_aug_dagger3_s{s}'] = learned_policy('bc_aug_dagger3', s)
    rows = []
    for name, policy in policies.items():
        for case in cases:
            cache = Cache()
            for k in ('transport', 'accommodation', 'dining'):
                cache.search(k, case.query, case.before)
            env = TurnEnv(case.query, case.before, case.plan, cache, case.diff.nl, random.Random(a.seed),
                          sample_global=getattr(policy, 'sample_global', True))
            while not env.done:
                env.step(policy.act(env))
            success = env.terminal in ('STOP', 'KEEP_PLAN') and verify(case.query, env.c, env.plan).passed
            rows.append(dict(system=name, case=case.name, min_components=case.min_components,
                             success=success, actions=env.history, terminal=env.terminal,
                             **revision_efficiency(case.query, env.c, case.plan, env.plan)))
    output = {'manifest': manifest(seed=a.seed, seeds=a.seeds, suite='synthetic-budget-v1'),
              'scope': 'Independent stress test; existing weights; no retraining. Global required only within <=2-local search.',
              'rows': rows}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(output, indent=2)+'\n')
    for name in policies:
        print(name, {level: sum(r['success'] for r in rows if r['system']==name and r['min_components']==level)
                     for level in (1, 2, 3)})


if __name__ == '__main__':
    main()
