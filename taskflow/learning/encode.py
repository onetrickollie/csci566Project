"""Observation encoder for the learned coordinator.

Uses only what a deployed coordinator can see: the parsed update, the last
verifier report (if fresh), cache freshness and contents, the current plan's
cost breakdown, and the actions taken so far this turn. No privileged
simulation.
"""

from __future__ import annotations

import numpy as np

from taskflow.agents.planners import effective_budget, plan_meals
from taskflow.env.state import (ACTIONS, CACHES, DIFF_OPS, DIFF_TYPES, GROUPS, SLOT_GROUP)
from taskflow.env.tools import _conflict_free_min, acc_cost
from taskflow.env.verifier import plan_cost

KINDS = ["budget", "room_type", "house_rule", "cuisine", "transport_rule", "min_rating",
         "priority_cost", "priority_quality", "invalid_entity", "transport_conflict",
         "min_nights", "duplicate_restaurant", "duplicate_attraction", "incomplete"]
MAX_STEPS = 10


def _onehot(i: int, n: int) -> list[float]:
    v = [0.0] * n
    if 0 <= i < n:
        v[i] = 1.0
    return v


def candidate_evidence(env) -> dict:
    """Observable facts from the cached search results and the current plan.

    Shared by the learned policy (``encode``) and the LLM coordinator
    (``state_summary``) so both see the same evidence. Caches may be stale;
    freshness is reported separately.
    """
    B = max(effective_budget(env.c), 1.0)
    cost = plan_cost(env.q, env.c, env.plan)
    tr = env.cache.get("transport")
    accs = env.cache.get("accommodation") or []
    dining = env.cache.get("dining")
    min_t = _conflict_free_min(tr, env.c.people) if tr else None
    min_a = min((acc_cost(a, env.c.people) for a in accs), default=None)
    meals = plan_meals(dining, env.c) if dining else {}
    idx = {r.name: r for r in (dining["restaurants"] if dining else [])}
    min_m = sum(idx[n].cost * env.c.people for n in meals.values() if n in idx)
    served = {cu for r in (dining["restaurants"] if dining else []) for cu in r.cuisines}
    lb = (min_t or 0) + (min_a or 0) + min_m
    return {
        "effective_budget": B,
        "plan_cost": cost,
        "plan_total": sum(cost.values()),
        "cheapest_transport": min_t,
        "cheapest_accommodation": min_a,
        "cheapest_meals": min_m,
        "cost_lower_bound": lb,
        "accommodation_candidates": len(accs),
        "transport_available": min_t is not None,
        "uncovered_cuisines": sorted(cu for cu in env.c.cuisines if cu not in served),
        "restaurant_candidates": len(dining["restaurants"]) if dining else 0,
    }


def encode(env) -> np.ndarray:
    f: list[float] = []
    d = env.diff
    f += _onehot(DIFF_OPS.index(d.op) if d else -1, len(DIFF_OPS))
    f += _onehot(DIFF_TYPES.index(d.target_type) if d else -1, len(DIFF_TYPES))
    f.append(1.0 if d is None else 0.0)
    f.append(1.0 if d and d.target_type == "budget" and float(d.new) < float(d.old or 0) else 0.0)

    rep = env.report
    f.append(1.0 if rep is not None else 0.0)
    f.append(1.0 if rep is not None and rep.passed else 0.0)
    kinds = rep.kinds() if rep is not None else set()
    f += [1.0 if k in kinds else 0.0 for k in KINDS]
    groups = {SLOT_GROUP[s] for s in rep.slots()} if rep is not None else set()
    f += [1.0 if g in groups else 0.0 for g in GROUPS]

    f += [1.0 if env.cache.fresh(c, env.c) else 0.0 for c in CACHES]
    f += [1.0 if g in env.changed else 0.0 for g in GROUPS]
    f.append(1.0 if env.global_done else 0.0)
    f += _onehot(min(len(env.history), MAX_STEPS - 1), MAX_STEPS)
    f += _onehot(ACTIONS.index(env.history[-1]) if env.history else len(ACTIONS), len(ACTIONS) + 1)
    f += [min(env.history.count(a), 3) / 3 for a in ACTIONS]
    f.append(min(env.failed_verifies, 3) / 3)

    # Cost picture and feasibility hints, relative to the effective budget.
    ev = candidate_evidence(env)
    B, cost, total = ev["effective_budget"], ev["plan_cost"], ev["plan_total"]
    min_t, min_a, min_m, lb = (ev["cheapest_transport"], ev["cheapest_accommodation"],
                               ev["cheapest_meals"], ev["cost_lower_bound"])
    f += [total / B, cost["transport"] / B, cost["accommodation"] / B, cost["meals"] / B]
    f += [(cost["transport"] - (min_t or 0)) / B, (cost["accommodation"] - (min_a or 0)) / B,
          (cost["meals"] - min_m) / B]
    f += [lb / B, 1.0 if lb > B else 0.0, 1.0 if total > B else 0.0]
    f += [1.0 if ev["accommodation_candidates"] == 0 else 0.0, 1.0 if min_t is None else 0.0,
          1.0 if ev["uncovered_cuisines"] else 0.0,
          1.0 if env.cache.get("dining") and ev["restaurant_candidates"] < 6 else 0.0]
    return np.asarray(f, dtype=np.float32)


def action_mask(env) -> np.ndarray:
    m = np.ones(len(ACTIONS), dtype=bool)
    if env.changed:
        m[ACTIONS.index("KEEP_PLAN")] = False
    return m
