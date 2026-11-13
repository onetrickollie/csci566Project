"""LLM-backed component agents.

Each agent gets a shortlist of cached candidates (deterministic best options
first), asks the model to choose, and validates the reply. Any invalid or
failed reply falls back to the deterministic choice, so the system always
returns a well-formed plan.
"""

from __future__ import annotations

from taskflow.env.state import SLOTS, Constraints
from taskflow.env.tools import acc_cost
from taskflow.llm.prompts import planner_prompt

SHORTLIST = 15


def _call(client, component, c, budget_left, cands, pick):
    system, user = planner_prompt(component, c.to_dict(), budget_left, cands, pick)
    return client.complete_json(system, user, max_tokens=300)


def accommodation(client, cands: list, c: Constraints, budget_left: float, default: dict) -> dict:
    if not cands:
        return default
    first = default.get("accommodation")
    ordered = sorted(cands, key=lambda a: (a.name != first, acc_cost(a, c.people), -a.rating))
    short = [{"name": a.name, "total_cost": round(acc_cost(a, c.people), 2), "room_type": a.room_type,
              "house_rules": a.house_rules or "none", "rating": a.rating, "max_occupancy": a.max_occupancy}
             for a in ordered[:SHORTLIST]]
    try:
        name = _call(client, "accommodation", c, budget_left, short, '{"name": "<candidate name>"}')["name"]
        pick = next(a for a in short if a["name"] == name)
        if pick["total_cost"] > budget_left and short[0]["total_cost"] <= budget_left:
            return default
        return {"accommodation": name}
    except Exception:
        return default


def transport(client, cands: dict, c: Constraints, budget_left: float, default: dict) -> dict:
    combos = []
    for o in cands["out"]:
        for b in cands["back"]:
            m = {o.mode, b.mode}
            if "self-driving" in m and len(m) > 1:
                continue
            combos.append({"out": o.key, "back": b.key, "total_cost": o.cost(c.people) + b.cost(c.people)})
    if not combos:
        return default
    combos.sort(key=lambda x: (not (x["out"] == default.get("transport_out")
                                    and x["back"] == default.get("transport_back")), x["total_cost"]))
    short = combos[:SHORTLIST]
    try:
        out = _call(client, "transport", c, budget_left, short, '{"out": "<key>", "back": "<key>"}')
        pick = next(x for x in short if x["out"] == out["out"] and x["back"] == out["back"])
        if pick["total_cost"] > budget_left and short[0]["total_cost"] <= budget_left:
            return default
        return {"transport_out": pick["out"], "transport_back": pick["back"]}
    except Exception:
        return default


def meals(client, cands: dict, c: Constraints, default: dict) -> dict:
    rest = cands["restaurants"]
    chosen = [default[s] for s in SLOTS["meals"] if default.get(s, "-") != "-"]
    by_name = {r.name: r for r in rest}
    others = sorted((r for r in rest if r.name not in chosen), key=lambda r: (r.cost, -r.rating))
    ordered = [by_name[n] for n in chosen if n in by_name] + others
    short = [{"name": r.name, "cost_per_person": r.cost, "cuisines": r.cuisines, "rating": r.rating}
             for r in ordered[:25]]
    try:
        names = _call(client, "meals", c, 0.0, short,
                      '{"restaurants": ["<6 distinct names: day1 dinner, day2 breakfast, day2 lunch, '
                      'day2 dinner, day3 breakfast, day3 lunch>"]}')["restaurants"]
        valid = {x["name"] for x in short}
        if len(names) != 6 or len(set(names)) != 6 or not set(names) <= valid:
            return default
        served = {cu for n in names for cu in by_name[n].cuisines}
        if any(cu not in served for cu in c.cuisines):
            return default
        if c.min_rating is not None and any(by_name[n].rating < c.min_rating for n in names):
            return default
        return dict(zip(SLOTS["meals"], names))
    except Exception:
        return default


def attractions(client, cands: dict, c: Constraints, default: dict) -> dict:
    first = [default[s] for s in SLOTS["attractions"] if default.get(s, "-") != "-"]
    names = first + [a.name for a in cands["attractions"] if a.name not in first]
    short = [{"name": n} for n in dict.fromkeys(names)][:20]
    try:
        picks = _call(client, "attractions", c, 0.0, short,
                      '{"attractions": ["<4 distinct names>"]}')["attractions"]
        valid = {x["name"] for x in short}
        if len(picks) != 4 or len(set(picks)) != 4 or not set(picks) <= valid:
            return default
        return dict(zip(SLOTS["attractions"], picks))
    except Exception:
        return default
