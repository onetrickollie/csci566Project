"""Evaluate every coordinator on the held-out test split.

Writes results/metrics.json, results/REPORT.md and figures in results/.

    python scripts/evaluate.py --seeds 0 1 2
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taskflow.agents.planners import compose_global  # noqa: E402
from taskflow.common import (LEARNED, RESULTS_DIR, TASKS_DIR, baseline_policies,  # noqa: E402
                             learned_policy, manifest, query_index)
from taskflow.coordinators.oracle import Oracle  # noqa: E402
from taskflow.data.tasks import load  # noqa: E402
from taskflow.env.episode import run_episode  # noqa: E402
from taskflow.env.state import ConstraintDiff, Constraints  # noqa: E402
from taskflow.env.tools import Cache  # noqa: E402
from taskflow.env.verifier import verify  # noqa: E402
from taskflow.eval.metrics import breakdown, by_chain_length, summarize  # noqa: E402

MISTAKES = ["REPLAN_LOCAL_ACCOMMODATION", "REPLAN_LOCAL_TRANSPORT", "REPLAN_LOCAL_MEALS",
            "REPLAN_GLOBAL"]


def mean_std(dicts: list[dict]) -> dict:
    out = {}
    for k in dicts[0]:
        vals = [d[k] for d in dicts if isinstance(d.get(k), (int, float)) and d[k] is not None]
        if vals:
            out[k] = {"mean": float(np.mean(vals)), "std": float(np.std(vals))}
    return out


def needs_repair_first_turn(ep, Q) -> bool:
    q = Q[ep.qid]
    base = Constraints.from_dict(ep.base)
    plan = compose_global(q, base, Cache())
    t = ep.turns[0]
    return t.feasible and not verify(q, ConstraintDiff.from_dict(t.diff).apply(base), plan).passed


def recovery(policy, eps, Q) -> dict:
    """Force one mistake at the first step of a turn that needs repair; can the policy recover?"""
    out = {}
    for mk in MISTAKES:
        succ, pres, calls = [], [], []
        for i, ep in enumerate(eps):
            r = run_episode(ep, Q[ep.qid], policy, seed=10_000 + i,
                            inject={"turn": 0, "step": 0, "action": mk})
            t = r.turns[0]
            succ.append(t.success)
            pres.append(t.preservation)
            calls.append(t.llm_calls)
        out[mk] = {"turn_success": float(np.mean(succ)),
                   "unaffected_preserved": float(np.mean([p for p in pres if p is not None])),
                   "llm_calls": float(np.mean(calls))}
    return out


def error_by_step(policy, eps, Q) -> dict:
    expert = Oracle()
    by_step, by_turn = defaultdict(list), defaultdict(list)
    for i, ep in enumerate(eps):
        r = run_episode(ep, Q[ep.qid], policy, seed=20_000 + i, expert=expert, record=True)
        for t in r.trajectory:
            err = t["action"] != t["expert_action"]
            by_step[t["step"]].append(err)
            by_turn[t["turn"]].append(err)
    return {"by_step": {k: float(np.mean(v)) for k, v in sorted(by_step.items())},
            "by_turn": {k: float(np.mean(v)) for k, v in sorted(by_turn.items())}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--split", default="test")
    a = ap.parse_args()
    RESULTS_DIR.mkdir(exist_ok=True)
    Q = query_index()
    eps = load(TASKS_DIR, a.split)
    rec_eps = [e for e in eps if needs_repair_first_turn(e, Q)]
    out = {"manifest": manifest(seeds=a.seeds, split=a.split), "systems": {},
           "recovery_episodes": len(rec_eps)}

    for name, pol in baseline_policies().items():
        res = [run_episode(e, Q[e.qid], pol, seed=i) for i, e in enumerate(eps)]
        out["systems"][name] = {
            "summary": {k: {"mean": v, "std": 0.0} for k, v in summarize(res).items()
                        if isinstance(v, (int, float))},
            "by_op": breakdown(res, "op"), "by_type": breakdown(res, "target_type"),
            "by_turn": breakdown(res, "turn_index"), "by_chain": by_chain_length(res),
            "recovery": recovery(pol, rec_eps, Q),
        }
        print(name, json.dumps(summarize(res)))

    for name in LEARNED:
        sums, recs, errs, first = [], [], [], None
        for s in a.seeds:
            pol = learned_policy(name, s)
            res = [run_episode(e, Q[e.qid], pol, seed=i) for i, e in enumerate(eps)]
            sums.append(summarize(res))
            recs.append(recovery(pol, rec_eps, Q))
            errs.append(error_by_step(pol, eps, Q))
            first = first or res
        rec = {mk: mean_std([r[mk] for r in recs]) for mk in MISTAKES}
        err = {"by_step": {k: float(np.mean([e["by_step"].get(k, np.nan) for e in errs]))
                           for k in errs[0]["by_step"]},
               "by_turn": {k: float(np.mean([e["by_turn"].get(k, np.nan) for e in errs]))
                           for k in errs[0]["by_turn"]}}
        out["systems"][name] = {
            "summary": mean_std(sums), "by_op": breakdown(first, "op"),
            "by_type": breakdown(first, "target_type"), "by_turn": breakdown(first, "turn_index"),
            "by_chain": by_chain_length(first), "recovery": rec, "error_vs_step": err,
        }
        print(name, json.dumps({k: round(v["mean"], 4) for k, v in mean_std(sums).items()}))

    (RESULTS_DIR / "metrics.json").write_text(json.dumps(out, indent=1, default=str))
    from taskflow.eval.report import write_report

    write_report(out, RESULTS_DIR)
    print(f"wrote {RESULTS_DIR / 'REPORT.md'}")


if __name__ == "__main__":
    main()
