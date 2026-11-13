"""Reproduce review checks without modifying production data, models or results."""
import json, random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import app
import evaluate
from taskflow.common import query_index, TASKS_DIR, manifest
from taskflow.data.tasks import load
from taskflow.data.world import build_world
from taskflow.env.state import Constraints, ConstraintDiff
from taskflow.env.verifier import verify
from taskflow.eval.exact import minimum_repair
from taskflow.env.episode import run_episode
from taskflow.coordinators.oracle import Oracle

out = {'manifest': manifest()}
Q = query_index()
multis = {}
for split in ('train_multi', 'val_multi', 'test_multi'):
    es = load(TASKS_DIR, split)
    counts = {'episodes': len(es), 'false_labels': [], 'invalid_initial': [], 'oracle_failures': [], 'levels': {}}
    for i, e in enumerate(es):
        c = Constraints.from_dict(e.base)
        if not verify(Q[e.qid], c, e.initial_plan).passed:
            counts['invalid_initial'].append(e.episode_id)
        t = e.turns[0]
        c = ConstraintDiff.from_dict(t.diff).apply(c)
        exact = minimum_repair(Q[e.qid], c, {})
        if bool(exact) != t.feasible:
            counts['false_labels'].append(e.episode_id)
        if not run_episode(e, Q[e.qid], Oracle(), seed=i).turns[0].success:
            counts['oracle_failures'].append(e.episode_id)
        level = e.episode_id.rsplit('-L', 1)[1]
        counts['levels'][level] = counts['levels'].get(level, 0) + 1
    multis[split] = counts
out['multi'] = multis
es = load(TASKS_DIR, 'test_multi')
out['recovery_selection'] = {'actual_broken_feasible': sum(e.turns[0].feasible and not verify(Q[e.qid], ConstraintDiff.from_dict(e.turns[0].diff).apply(Constraints.from_dict(e.base)), e.initial_plan).passed for e in es), 'selected': sum(evaluate.needs_repair_first_turn(e, Q) for e in es)}
app.WORLD = build_world()
app.LLM = None
out['world'] = {'starts': len(app.WORLD.start_cities), 'destinations': len(app.WORLD.destinations)}
for org, dest in [('Los Angeles', 'Honolulu'), ('New York', 'Seattle')]:
    if org in app.WORLD.start_cities and dest in app.WORLD.destinations:
        result = app.api_trip(dict(org=org, dest=dest, date='2022-03-10', people=2, budget=10000, transport='no flight'))
        out[f'route:{org}->{dest}'] = result
class Ask:
    def act(self, env):
        return 'ASK_CLARIFICATION'
result = app.api_trip(dict(org='Chicago', dest='Seattle', date='2022-03-10', people=2, budget=3000))
sid = result['session']
for st in app.SESSIONS[sid]['state'].values():
    st['policy'] = Ask()
# A budget increase preserves validity; asking is demonstrably unnecessary.
out['feasible_ask'] = app.api_update({'session': sid, 'message': "Let's change the budget to $4,000."})
for budget in ['NaN', 'Infinity', '-1']:
    try:
        r = app.api_trip(dict(org='Chicago', dest='Seattle', date='2022-03-10', people=2, budget=budget))
        out[f'budget:{budget}'] = {'accepted': 'session' in r, 'request': r.get('request'), 'error': r.get('error')}
    except Exception as exc:
        out[f'budget:{budget}'] = {'exception': str(exc)}
# Outbound and return ground records may have distinct costs/distances.
for (mode, org, dest), g in app.WORLD.ground.items():
    back = app.WORLD.ground.get((mode, dest, org))
    if back and (g.cost, g.duration, g.distance_km) != (back.cost, back.duration, back.distance_km) and dest in app.WORLD.destinations:
        q = app.WORLD.trip_query(org, dest, '2022-03-10', 2, 10000)
        out['direction_display'] = {'org': org, 'dest': dest, 'mode': mode, 'out_cost': q.db.ground[(mode, org, dest)].cost, 'back_cost': q.db.ground[(mode, dest, org)].cost, 'rows': app.plan_rows(q, {'transport_out': mode, 'transport_back': mode})}
        break
Path(__file__).with_name('checks.json').write_text(json.dumps(out, indent=2, allow_nan=False) + '\n')
print(json.dumps({k:v for k,v in out.items() if k in ['multi','world','recovery_selection']}, indent=2))
