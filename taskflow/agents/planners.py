"""Component planners (Transportation, Accommodation, Activity & Dining) and the
Plan Composer.

In this offline build each planner is a deterministic search over the cached
candidates; the coordinator interface is identical to the LLM-backed version
(see ``taskflow/llm``). Local planners keep every other component fixed and
work within the budget those components leave. Global regeneration refreshes
every cache and rebuilds from scratch; with ``rng`` it samples among
near-best options, modelling the instability of full regeneration.
"""

from __future__ import annotations

import random

from taskflow.agents import llm_planners
from taskflow.data.travelplanner import Query
from taskflow.env.state import SLOTS, Constraints, Plan
from taskflow.env.tools import Cache, TransportOption, acc_cost
from taskflow.env.verifier import PRIORITY_COST_RATIO, plan_cost, verify


def effective_budget(c: Constraints) -> float:
    return c.budget * (PRIORITY_COST_RATIO if c.priority == "cost" else 1.0)


def _conflict(a: TransportOption, b: TransportOption) -> bool:
    m = {a.mode, b.mode}
    return "self-driving" in m and len(m) > 1


def plan_transport(cands: dict, c: Constraints, budget_left: float, rng=None) -> dict:
    combos = [(o.cost(c.people) + b.cost(c.people), o, b)
              for o in cands["out"] for b in cands["back"] if not _conflict(o, b)]
    if not combos:
        return {"transport_out": "-", "transport_back": "-"}
    combos.sort(key=lambda x: (x[0], x[1].key, x[2].key))
    pick = combos[0]
    if rng is not None:
        near = [x for x in combos if x[0] <= max(budget_left, combos[0][0]) and x[0] <= combos[0][0] * 1.25]
        pick = rng.choice(near)
    return {"transport_out": pick[1].key, "transport_back": pick[2].key}


def plan_accommodation(cands: list, c: Constraints, budget_left: float, rng=None) -> dict:
    if not cands:
        return {"accommodation": "-"}
    priced = [(acc_cost(a, c.people), a) for a in cands]
    ok = [x for x in priced if x[0] <= budget_left]
    if not ok:
        return {"accommodation": min(priced, key=lambda x: (x[0], x[1].name))[1].name}
    if c.priority == "cost":
        ok.sort(key=lambda x: (x[0], -x[1].rating, x[1].name))
    else:
        ok.sort(key=lambda x: (-x[1].rating, x[0], x[1].name))
    pick = rng.choice(ok[:3]) if rng is not None else ok[0]
    return {"accommodation": pick[1].name}


def plan_meals(cands: dict, c: Constraints, rng=None) -> dict:
    rest = sorted(cands["restaurants"], key=lambda r: (r.cost, -r.rating, r.name))
    chosen: list = []
    names: set[str] = set()
    need = [cu for cu in c.cuisines]
    while need:
        best = None
        for r in rest:
            if r.name in names:
                continue
            cover = len(set(need) & set(r.cuisines))
            if cover and (best is None or cover / (r.cost + 1) > best[0]):
                best = (cover / (r.cost + 1), r)
        if best is None:
            break
        chosen.append(best[1])
        names.add(best[1].name)
        need = [cu for cu in need if cu not in best[1].cuisines]
    pool = [r for r in rest if r.name not in names]
    if rng is not None:
        pool = pool[:12]
        rng.shuffle(pool)
    for r in pool:
        if len(chosen) >= len(SLOTS["meals"]):
            break
        chosen.append(r)
        names.add(r.name)
    out = {s: "-" for s in SLOTS["meals"]}
    order = list(SLOTS["meals"])
    if rng is not None:
        rng.shuffle(order)
    for s, r in zip(order, chosen):
        out[s] = r.name
    return out


def plan_attractions(cands: dict, rng=None) -> dict:
    names = []
    for a in cands["attractions"]:
        if a.name not in names:
            names.append(a.name)
    if rng is not None:
        names = rng.sample(names, min(len(names), len(SLOTS["attractions"])))
    out = {s: "-" for s in SLOTS["attractions"]}
    for s, n in zip(SLOTS["attractions"], names):
        out[s] = n
    return out


def replan_local(q: Query, c: Constraints, plan: Plan, group: str, cache: Cache, llm=None) -> Plan:
    """Re-plan one component, keeping all others fixed, using cached candidates.

    With an LLM client the component agent chooses from a shortlist; the
    deterministic choice is the fallback for any invalid reply.
    """
    new = dict(plan)
    cost = plan_cost(q, c, plan)
    others = sum(v for k, v in cost.items() if k != group)
    left = effective_budget(c) - others
    if group == "transport":
        pick = plan_transport(cache.get("transport"), c, left)
        if llm is not None:
            pick = llm_planners.transport(llm, cache.get("transport"), c, left, pick)
    elif group == "accommodation":
        pick = plan_accommodation(cache.get("accommodation"), c, left)
        if llm is not None:
            pick = llm_planners.accommodation(llm, cache.get("accommodation"), c, left, pick)
    elif group == "meals":
        pick = plan_meals(cache.get("dining"), c)
        if llm is not None:
            pick = llm_planners.meals(llm, cache.get("dining"), c, pick, budget_left=left)
    else:
        pick = plan_attractions(cache.get("dining"))
        if llm is not None:
            pick = llm_planners.attractions(llm, cache.get("dining"), c, pick)
    new.update(pick)
    return new


def compose_global(q: Query, c: Constraints, cache: Cache, rng: random.Random | None = None,
                   llm=None) -> Plan:
    """Full regeneration. Refreshes every cache in place.

    Offline, ``rng`` samples among near-best options to model regeneration
    instability. With an LLM client every component agent is asked afresh.
    """
    for name in ("transport", "accommodation", "dining"):
        cache.search(name, q, c)
    det = _compose(q, c, cache, None)
    if llm is not None:
        p = _compose(q, c, cache, None, llm)
        return p if verify(q, c, p).passed else det
    if rng is None:
        return det
    for _ in range(3):
        p = _compose(q, c, cache, rng)
        if verify(q, c, p).passed:
            return p
    return det


def _compose(q, c, cache, rng, llm=None) -> Plan:
    plan: Plan = {}
    meals = plan_meals(cache.get("dining"), c, rng)
    attrs = plan_attractions(cache.get("dining"), rng)
    tr = plan_transport(cache.get("transport"), c, effective_budget(c), rng)
    if llm is not None:
        meals = llm_planners.meals(llm, cache.get("dining"), c, meals)
        attrs = llm_planners.attractions(llm, cache.get("dining"), c, attrs)
        tr = llm_planners.transport(llm, cache.get("transport"), c, effective_budget(c), tr)
    plan.update(meals)
    plan.update(attrs)
    plan.update(tr)
    plan["accommodation"] = "-"
    cost = plan_cost(q, c, plan)
    left = effective_budget(c) - cost["transport"] - cost["meals"]
    acc = plan_accommodation(cache.get("accommodation"), c, left, rng)
    if llm is not None:
        acc = llm_planners.accommodation(llm, cache.get("accommodation"), c, left, acc)
    plan.update(acc)
    return plan


def is_feasible(q: Query, c: Constraints) -> bool:
    return verify(q, c, compose_global(q, c, Cache())).passed


def min_cost(q: Query, c: Constraints) -> float:
    """Cost of the cheapest plan the planners can build (ignoring the budget)."""
    cc = c.copy()
    cc.budget, cc.priority = 1e9, "cost"
    cache = Cache()
    p = compose_global(q, cc, cache)
    cost = plan_cost(q, cc, p)
    accs = cache.get("accommodation")
    if accs:
        cost["accommodation"] = min(acc_cost(a, c.people) for a in accs)
    return sum(cost.values())
