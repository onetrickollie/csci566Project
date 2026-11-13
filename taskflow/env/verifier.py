"""Deterministic plan checker.

Mirrors the TravelPlanner commonsense and hard-constraint checks for 3-day
single-city trips, plus the constraint types added by this project
(restaurant rating floor and cost/quality priority). Each violation lists
the plan slots that cause it, which is what the coordinator and the
preservation metric use.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from taskflow.data.travelplanner import Query
from taskflow.env.state import SLOTS, Constraints, Plan
from taskflow.env.tools import acc_cost, lookup_index, room_ok, rules_ok, transport_options

__all__ = ["Report", "Violation", "verify", "plan_cost", "constraint_item_satisfied"]

COSTED = SLOTS["transport"] + SLOTS["accommodation"] + SLOTS["meals"]
PRIORITY_COST_RATIO = 0.85
PRIORITY_QUALITY_RATING = 4.0


@dataclass
class Violation:
    kind: str
    detail: str
    slots: list[str]


@dataclass
class Report:
    passed: bool
    total_cost: float
    violations: list[Violation] = field(default_factory=list)
    component_cost: dict = field(default_factory=dict)

    def kinds(self) -> set[str]:
        return {v.kind for v in self.violations}

    def slots(self) -> set[str]:
        return {s for v in self.violations for s in v.slots}

    def to_dict(self) -> dict:
        return asdict(self)


def _transport_lookup(q: Query, c_any: Constraints, leg: str) -> dict:
    # Availability is checked without the user's transport rule; the rule is a
    # separate hard constraint.
    relaxed = c_any.copy()
    relaxed.transport = None
    return {o.key: o for o in transport_options(q, relaxed, leg)}


def plan_cost(q: Query, c: Constraints, plan: Plan, idx: dict | None = None) -> dict:
    idx = idx or lookup_index(q.db)
    out = {"transport": 0.0, "accommodation": 0.0, "meals": 0.0}
    for leg, slot in (("out", "transport_out"), ("back", "transport_back")):
        o = _transport_lookup(q, c, leg).get(plan.get(slot, "-"))
        if o:
            out["transport"] += o.cost(c.people)
    a = idx["accommodation"].get(plan.get("accommodation", "-"))
    if a:
        out["accommodation"] = acc_cost(a, c.people)
    for s in SLOTS["meals"]:
        r = idx["restaurant"].get(plan.get(s, "-"))
        if r:
            out["meals"] += r.cost * c.people
    return out


def verify(q: Query, c: Constraints, plan: Plan) -> Report:
    idx = lookup_index(q.db)
    V: list[Violation] = []

    # --- commonsense -----------------------------------------------------
    legs = {}
    for leg, slot in (("out", "transport_out"), ("back", "transport_back")):
        val = plan.get(slot, "-")
        opt = _transport_lookup(q, c, leg).get(val)
        if opt is None:
            V.append(Violation("invalid_entity", f"{slot}={val!r} unavailable", [slot]))
        else:
            legs[slot] = opt.mode
    modes = set(legs.values())
    if "self-driving" in modes and ({"flight", "taxi"} & modes):
        V.append(Violation("transport_conflict", f"modes {sorted(modes)}", list(legs)))

    acc = idx["accommodation"].get(plan.get("accommodation", "-"))
    if acc is None:
        V.append(Violation("invalid_entity", "accommodation unknown", ["accommodation"]))
    elif acc.min_nights > 2:
        V.append(Violation("min_nights", f"requires {acc.min_nights:g} nights", ["accommodation"]))

    seen: dict[str, str] = {}
    for s in SLOTS["meals"]:
        name = plan.get(s, "-")
        if name == "-":
            continue
        if name not in idx["restaurant"]:
            V.append(Violation("invalid_entity", f"{s}={name!r} unknown", [s]))
        elif name in seen:
            V.append(Violation("duplicate_restaurant", name, [seen[name], s]))
        else:
            seen[name] = s
    seen_a: dict[str, str] = {}
    for s in SLOTS["attractions"]:
        name = plan.get(s, "-")
        if name == "-":
            continue
        if name not in idx["attraction"]:
            V.append(Violation("invalid_entity", f"{s}={name!r} unknown", [s]))
        elif name in seen_a:
            V.append(Violation("duplicate_attraction", name, [seen_a[name], s]))
        else:
            seen_a[name] = s

    # --- hard constraints ------------------------------------------------
    cost = plan_cost(q, c, plan, idx)
    total = sum(cost.values())
    if total > c.budget:
        V.append(Violation("budget", f"total={total:.0f} > {c.budget:.0f}", list(COSTED)))
    if acc is not None:
        if not room_ok(acc, c.room_type):
            V.append(Violation("room_type", f"{acc.room_type} vs {c.room_type}", ["accommodation"]))
        for rule in c.house_rules:
            if not rules_ok(acc, [rule]):
                V.append(Violation("house_rule", rule, ["accommodation"]))
    meal_rest = {s: idx["restaurant"][plan[s]] for s in SLOTS["meals"]
                 if plan.get(s, "-") in idx["restaurant"]}
    served = {cu for r in meal_rest.values() for cu in r.cuisines}
    for cu in c.cuisines:
        if cu not in served:
            V.append(Violation("cuisine", f"no {cu} restaurant", list(SLOTS["meals"])))
    if c.transport == "no flight" and "flight" in modes:
        V.append(Violation("transport_rule", "flight used", [s for s, m in legs.items() if m == "flight"]))
    if c.transport == "no self-driving" and "self-driving" in modes:
        V.append(Violation("transport_rule", "self-driving used",
                           [s for s, m in legs.items() if m == "self-driving"]))
    if c.min_rating is not None:
        low = [s for s, r in meal_rest.items() if r.rating < c.min_rating]
        if low:
            V.append(Violation("min_rating", f"{len(low)} meals below {c.min_rating}", low))
    if c.priority == "cost" and total > PRIORITY_COST_RATIO * c.budget:
        V.append(Violation("priority_cost", f"total={total:.0f} > {PRIORITY_COST_RATIO:.0%} of budget",
                           list(COSTED)))
    if c.priority == "quality" and acc is not None and acc.rating < PRIORITY_QUALITY_RATING:
        V.append(Violation("priority_quality", f"accommodation rating {acc.rating}", ["accommodation"]))

    return Report(passed=not V, total_cost=total, violations=V, component_cost=cost)


def constraint_item_satisfied(item: tuple[str, object], report: Report) -> bool:
    """Is one active constraint item satisfied by the plan behind ``report``?"""
    kind, val = item
    for v in report.violations:
        if kind == "budget" and v.kind == "budget":
            return False
        if kind == "room_type" and v.kind == "room_type":
            return False
        if kind == "house_rule" and v.kind == "house_rule" and v.detail == val:
            return False
        if kind == "cuisine" and v.kind == "cuisine" and v.detail == f"no {val} restaurant":
            return False
        if kind == "transport" and v.kind == "transport_rule":
            return False
        if kind == "min_rating" and v.kind == "min_rating":
            return False
        if kind == "priority" and v.kind == f"priority_{val}":
            return False
    return True
