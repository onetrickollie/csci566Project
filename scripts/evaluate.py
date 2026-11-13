"""Evaluate every coordinator on a split.

    python scripts/evaluate.py --canonical --seeds 0 1 2      # the committed results/ (offline, test)
    python scripts/evaluate.py --llm openai --split val --limit 30 --seeds 0 --skip-recovery
    python scripts/evaluate.py --call-cap 1 --seeds 0 1 2     # matched LLM-call budget per turn

Output goes to results/runs/<run_id>/ (metrics.json, REPORT.md, figures).
Only --canonical writes results/ itself, and it is refused for anything but
the full offline test evaluation. run_id encodes split, backend, model
suffix, cap and a config hash, so different runs never overwrite each other.

With --llm, the tracker and component agents call the model, an LLM
coordinator is added, and measured usage plus per-component fallbacks are
reported per system. A run whose client had errors or fallbacks is marked
DEGRADED in the report. Fatal client errors (bad key/model/endpoint) abort.
Use the validation split for prompt development; keep test frozen.
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
from taskflow.env.episode import TurnEnv  # noqa: E402
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


def initial_state(ep, q):
    """Same start as run_episode: planner-built plan (fills every cache), or the
    episode's approved initial plan when it has one."""
    base = Constraints.from_dict(ep.base)
    cache = Cache()
    plan = compose_global(q, base, cache)
    if ep.initial_plan:
        plan = dict(ep.initial_plan)
    return base, cache, plan


def needs_repair_first_turn(ep, Q) -> bool:
    q = Q[ep.qid]
    base, _, plan = initial_state(ep, q)
    t = ep.turns[0]
    return t.feasible and not verify(q, ConstraintDiff.from_dict(t.diff).apply(base), plan).passed


LLM = None
CALL_CAP = None


def mistake_needs_recovery(ep, Q, mistake: str) -> bool:
    """Does the forced action leave the first turn's plan invalid? (deterministic check)

    If the injected action alone already repairs the plan (e.g. REPLAN_GLOBAL),
    the case says nothing about recovery and is reported separately.
    """
    import random

    q = Q[ep.qid]
    base, cache, plan = initial_state(ep, q)
    env = TurnEnv(q, base, plan, cache, ConstraintDiff.from_dict(ep.turns[0].diff).nl, random.Random(0))
    env.step(mistake)
    return not verify(q, env.c, env.plan).passed


def recovery(policy, eps, Q, needs: dict) -> dict:
    """Force one mistake at the first step of a turn that needs repair; can the policy recover?

    Reported over all selected episodes and over the subset where the mistake
    actually left the plan broken (``needs_recovery``).
    """
    out = {}
    if not eps:
        return out
    for mk in MISTAKES:
        rows = []
        for i, ep in enumerate(eps):
            r = run_episode(ep, Q[ep.qid], policy, seed=10_000 + i,
                            inject={"turn": 0, "step": 0, "action": mk}, llm=LLM, call_cap=CALL_CAP)
            t = r.turns[0]
            rows.append((needs[(ep.episode_id, mk)], t.success, t.preservation, t.llm_calls))
        hard = [x for x in rows if x[0]]
        out[mk] = {"turn_success": float(np.mean([x[1] for x in rows])),
                   "unaffected_preserved": float(np.mean([x[2] for x in rows if x[2] is not None])),
                   "llm_calls": float(np.mean([x[3] for x in rows])),
                   "needs_recovery_n": len(hard),
                   "needs_recovery_success": float(np.mean([x[1] for x in hard])) if hard else None}
    return out


def error_by_step(policy, eps, Q) -> dict:
    if LLM is not None:
        # Deterministic counterfactual labels are not expert labels for live transitions.
        return {"by_step": {}, "by_turn": {}}
    expert = Oracle()
    by_step, by_turn = defaultdict(list), defaultdict(list)
    for i, ep in enumerate(eps):
        r = run_episode(ep, Q[ep.qid], policy, seed=20_000 + i, expert=expert, record=True, llm=LLM,
                        call_cap=CALL_CAP)
        for t in r.trajectory:
            err = t["action"] != t["expert_action"]
            by_step[t["step"]].append(err)
            by_turn[t["turn"]].append(err)
    return {"by_step": {k: float(np.mean(v)) for k, v in sorted(by_step.items())},
            "by_turn": {k: float(np.mean(v)) for k, v in sorted(by_turn.items())}}


def _usage_delta(u0: dict | None) -> dict | None:
    if LLM is None:
        return None
    u = LLM.usage.as_dict()
    out = {k: u[k] - u0.get(k, 0) for k in ("requests", "calls", "cache_hits", "errors", "tokens",
                                             "billed_input_tokens", "billed_output_tokens")}
    out["fallbacks"] = {k: v - u0["fallbacks"].get(k, 0) for k, v in u["fallbacks"].items()
                        if v - u0["fallbacks"].get(k, 0)}
    out["fallback_rate"] = sum(out["fallbacks"].values()) / out["requests"] if out["requests"] else 0.0
    out["degraded"] = out["errors"] > 0 or bool(out["fallbacks"])
    return out


def _snapshot() -> dict | None:
    if LLM is None:
        return None
    u = LLM.usage.as_dict()
    u["fallbacks"] = dict(u["fallbacks"])
    return u


def main():
    global LLM, CALL_CAP
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--split", default="test",
                    choices=["train", "val", "test", "train_multi", "val_multi", "test_multi"])
    ap.add_argument("--llm", default=None, help="offline | fake | openai | anthropic")
    ap.add_argument("--require-llm", action="store_true", help="refuse to run offline")
    ap.add_argument("--limit", type=int, default=None, help="evaluate only the first N episodes")
    ap.add_argument("--skip-recovery", action="store_true")
    ap.add_argument("--model-suffix", default="", help='e.g. "_llmteacher" for LLM-teacher models')
    ap.add_argument("--call-cap", type=int, default=None, help="max cost-model LLM calls per turn")
    ap.add_argument("--canonical", action="store_true", help="write results/ (full offline test run only)")
    ap.add_argument("--out", type=Path, default=None, help="explicit output directory")
    a = ap.parse_args()
    from taskflow.llm.client import get_client

    LLM = get_client(a.llm)
    CALL_CAP = a.call_cap
    if a.require_llm and LLM is None:
        sys.exit("--require-llm: no LLM backend configured (set TASKFLOW_LLM_PROVIDER or pass --llm)")
    from taskflow.common import MODELS_DIR, fingerprint

    model_files = [MODELS_DIR / f"{n}{a.model_suffix}_s{sd}.pt" for n in LEARNED for sd in a.seeds]
    config = dict(seeds=a.seeds, split=a.split, limit=a.limit, skip_recovery=a.skip_recovery,
                  model_suffix=a.model_suffix, call_cap=a.call_cap,
                  llm=LLM.identity() if LLM else "offline", models=fingerprint(model_files))
    man = manifest(**config)
    if a.canonical:
        if LLM is not None or a.split != "test" or a.limit or a.model_suffix or a.call_cap or a.skip_recovery:
            sys.exit("--canonical is only for the full offline test evaluation")
        out_dir = RESULTS_DIR
    elif a.out:
        out_dir = a.out
    else:
        backend = "offline" if LLM is None else f"{LLM.provider}-{LLM.model}".replace("/", "_")
        parts = [a.split, backend] + ([f"cap{a.call_cap}"] if a.call_cap is not None else []) \
            + ([a.model_suffix.strip("_")] if a.model_suffix else []) + [man["config_hash"]]
        out_dir = RESULTS_DIR / "runs" / "-".join(parts)
    out_dir.mkdir(parents=True, exist_ok=True)
    Q = query_index()
    eps = load(TASKS_DIR, a.split)[: a.limit]
    rec_eps = [] if a.skip_recovery else [e for e in eps if needs_repair_first_turn(e, Q)]
    needs = {(e.episode_id, mk): mistake_needs_recovery(e, Q, mk) for e in rec_eps for mk in MISTAKES}
    out = {"manifest": man, "systems": {}, "recovery_episodes": len(rec_eps)}

    for name, pol in baseline_policies(LLM).items():
        u0 = _snapshot()
        res = [run_episode(e, Q[e.qid], pol, seed=i, llm=LLM, call_cap=CALL_CAP, score_edits=True)
               for i, e in enumerate(eps)]
        usage = _usage_delta(u0)
        out["systems"][name] = {
            "summary": {k: {"mean": v, "std": 0.0} for k, v in summarize(res).items()
                        if isinstance(v, (int, float))},
            "by_op": breakdown(res, "op"), "by_type": breakdown(res, "target_type"),
            "by_turn": breakdown(res, "turn_index"), "by_chain": by_chain_length(res),
            "by_level": breakdown(res, "level"),
            "recovery": recovery(pol, rec_eps, Q, needs), "llm_usage": usage,
        }
        print(name, json.dumps(summarize(res)))

    for name in LEARNED:
        sums, recs, errs, first, usages = [], [], [], None, []
        for s in a.seeds:
            pol = learned_policy(name + a.model_suffix, s)
            u0 = _snapshot()
            res = [run_episode(e, Q[e.qid], pol, seed=i, llm=LLM, call_cap=CALL_CAP, score_edits=True)
                   for i, e in enumerate(eps)]
            usages.append(_usage_delta(u0))
            sums.append(summarize(res))
            recs.append(recovery(pol, rec_eps, Q, needs))
            errs.append(error_by_step(pol, eps, Q))
            first = first or res
        rec = {}
        if recs and recs[0]:
            for mk in MISTAKES:
                rec[mk] = mean_std([{k: v for k, v in r[mk].items() if v is not None} for r in recs])
        err = {"by_step": {k: float(np.mean([e["by_step"].get(k, np.nan) for e in errs]))
                           for k in errs[0]["by_step"]},
               "by_turn": {k: float(np.mean([e["by_turn"].get(k, np.nan) for e in errs]))
                           for k in errs[0]["by_turn"]}}
        out["systems"][name] = {
            "summary": mean_std(sums), "by_op": breakdown(first, "op"),
            "by_type": breakdown(first, "target_type"), "by_turn": breakdown(first, "turn_index"),
            "by_chain": by_chain_length(first), "by_level": breakdown(first, "level"),
            "recovery": rec, "error_vs_step": err,
            "llm_usage": usages[0],
        }
        print(name, json.dumps({k: round(v["mean"], 4) for k, v in mean_std(sums).items()}))

    if LLM is not None:
        out["llm_usage_total"] = LLM.usage.as_dict()
        out["degraded"] = LLM.usage.degraded
    (out_dir / "metrics.json").write_text(json.dumps(out, indent=1, default=str))
    from taskflow.eval.report import write_report

    write_report(out, out_dir)
    print(f"wrote {out_dir / 'REPORT.md'}")


if __name__ == "__main__":
    main()
