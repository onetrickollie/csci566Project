"""Exact feasibility and minimum slot edits for the v0 single-city schema.

Scoring only: never used by a deployed policy or its observation encoder.
Dynamic programming considers six distinct meals, cuisine coverage, and the
number of old meal assignments retained; transport pairs and hotels are
exhaustive. All 13 slots are required. The objective is lexicographic:
fewest changed slots, then lowest cost. No greedy planner is consulted.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product

from taskflow.data.travelplanner import Query
from taskflow.env.state import ALL_SLOTS, SLOTS, Constraints, Plan
from taskflow.env.tools import acc_cost, search_accommodation, search_dining, search_transport
from taskflow.env.verifier import PRIORITY_COST_RATIO, verify


@dataclass
class ExactRepair:
    edits: int
    cost: float
    plan: Plan


def minimum_repair(q: Query, c: Constraints, start: Plan) -> ExactRepair | None:
    """Return an exact witness, or None when no complete valid plan exists.

    The meal DP retains the cheapest subset for each (size, cuisine mask,
    retained-count). A chosen old restaurant preserves at most one slot,
    including when the starting plan has duplicates. Free assignments fill
    the remaining slots, so these counts are attainable, not just bounds.
    """
    tr = search_transport(q, c)
    transports = {}
    for a, b in product(tr['out'], tr['back']):
        if 'self-driving' in {a.mode, b.mode} and a.mode != b.mode:
            continue
        edits = int(start.get('transport_out') != a.key) + int(start.get('transport_back') != b.key)
        value = (a.cost(c.people) + b.cost(c.people), a.key, b.key)
        if edits not in transports or value < transports[edits]:
            transports[edits] = value
    hotels = {}
    for a in search_accommodation(q, c):
        edits = int(start.get('accommodation') != a.name)
        value = (acc_cost(a, c.people), a.name)
        if edits not in hotels or value < hotels[edits]:
            hotels[edits] = value
    dining = search_dining(q, c)
    restaurants = {r.name: r for r in reversed(dining['restaurants'])}
    old_names = {start.get(s) for s in SLOTS['meals']}
    dp = {(0, 0, 0): (0.0, ())}
    for name, r in sorted(restaurants.items()):
        mask = sum(1 << i for i, cu in enumerate(c.cuisines) if cu in r.cuisines)
        retain = int(name in old_names)
        for (n, covered, kept), (cost, chosen) in list(dp.items()):
            if n == 6:
                continue
            key = (n + 1, covered | mask, kept + retain)
            value = (cost + r.cost * c.people, chosen + (name,))
            if key not in dp or value < dp[key]:
                dp[key] = value
    full = (1 << len(c.cuisines)) - 1
    meals = {6 - kept: value for (n, mask, kept), value in dp.items() if n == 6 and mask == full}
    attractions = sorted({a.name for a in dining['attractions']})
    if not transports or not hotels or not meals or len(attractions) < 4:
        return None
    attrs, used = {}, set()
    for slot in SLOTS['attractions']:
        name = start.get(slot)
        if name in attractions and name not in used:
            attrs[slot] = name
            used.add(name)
    for slot in SLOTS['attractions']:
        if slot not in attrs:
            name = next(a for a in attractions if a not in used)
            attrs[slot] = name
            used.add(name)
    attr_edits = sum(attrs[s] != start.get(s) for s in attrs)
    budget = c.budget * (PRIORITY_COST_RATIO if c.priority == 'cost' else 1.0)
    best = None
    for (te, t), (ae, a), (me, m) in product(transports.items(), hotels.items(), meals.items()):
        cost = t[0] + a[0] + m[0]
        if cost > budget:
            continue
        key = (te + ae + me + attr_edits, cost, t[1:], a[1], m[1])
        if best is not None and key >= best[0]:
            continue
        plan = dict(attrs, transport_out=t[1], transport_back=t[2], accommodation=a[1])
        remaining = set(m[1])
        for slot in SLOTS['meals']:
            name = start.get(slot)
            if name in remaining:
                plan[slot] = name
                remaining.remove(name)
        for slot in SLOTS['meals']:
            if slot not in plan:
                name = min(remaining)
                plan[slot] = name
                remaining.remove(name)
        best = (key, plan)
    if best is None:
        return None
    edits = sum(best[1][s] != start.get(s) for s in ALL_SLOTS)
    assert edits == best[0][0] and verify(q, c, best[1]).passed
    return ExactRepair(edits, best[0][1], best[1])


def revision_efficiency(q: Query, c: Constraints, before: Plan, after: Plan) -> dict:
    """Score successful plans only; failed/no-op plans cannot earn stability credit.

    edit_optimal_preservation = 1 - (actual_edits - minimum_edits)/(13-minimum_edits).
    If all slots must change, excess edits is defined but preservation is not.
    """
    if not verify(q, c, after).passed:
        return {'minimum_edits': None, 'excess_edits': None, 'edit_optimal_preservation': None}
    optimum = minimum_repair(q, c, before)
    assert optimum is not None
    actual = sum(before.get(s) != after.get(s) for s in ALL_SLOTS)
    excess = actual - optimum.edits
    assert excess >= 0
    denominator = len(ALL_SLOTS) - optimum.edits
    return {'minimum_edits': optimum.edits, 'excess_edits': excess,
            'edit_optimal_preservation': 1 - excess / denominator if denominator else None}
