"""Evolving-constraint task construction.

1. Base constraints: taken from the query for train/validation rows; sampled
   for test rows (TravelPlanner hides their constraints).
2. Splits by original query id, before any variant is generated.
3. Each episode is a chain of structured updates (add / delete / replace /
   reprioritize) with a natural-language rendering. Infeasible updates are
   kept at a controlled rate; the correct response is ASK_CLARIFICATION and
   the user then withdraws the update.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

from taskflow.agents.planners import is_feasible, min_cost
from taskflow.data.travelplanner import Query
from taskflow.env.state import (CUISINES, HOUSE_RULES, PRIORITIES, ROOM_TYPES, TRANSPORT_RULES,
                                ConstraintDiff, Constraints)

TEMPLATES = {
    # Template set A is used for train/validation; set B only for test.
    "A": {
        "budget": ["Actually, can we keep the total budget at ${new:,.0f}?",
                   "Let's change the budget to ${new:,.0f}."],
        "add_room_type": ["I'd like the accommodation to be a {new}."],
        "replace_room_type": ["Instead of a {old}, please make it a {new}."],
        "delete_room_type": ["The room type doesn't matter anymore."],
        "add_house_rule": ["The place needs to allow {new}."],
        "delete_house_rule": ["We no longer need the place to allow {old}."],
        "add_cuisine": ["Could we also try some {new} food?"],
        "replace_cuisine": ["Swap the {old} food requirement for {new}."],
        "delete_cuisine": ["Forget about the {old} food."],
        "add_transport": ["Please, {new} on this trip."],
        "delete_transport": ["Any transportation mode is fine now."],
        "add_min_rating": ["Only restaurants rated at least {new} please."],
        "delete_min_rating": ["Restaurant ratings don't matter anymore."],
        "priority": ["Now {new} matters more to me than anything else."],
        "delete_priority": ["No particular priority anymore, just stay valid."],
    },
    "B": {
        "budget": ["My spending limit for the whole trip is now ${new:,.0f}."],
        "add_room_type": ["Book us a {new} for the stay."],
        "replace_room_type": ["Change the lodging from {old} to {new}."],
        "delete_room_type": ["Any kind of room works for us now."],
        "add_house_rule": ["We'll need a host that permits {new}."],
        "delete_house_rule": ["Allowing {old} is not required any longer."],
        "add_cuisine": ["Add a {new} meal somewhere in the trip."],
        "replace_cuisine": ["Rather than {old}, we want {new} cuisine."],
        "delete_cuisine": ["Drop the {old} cuisine request."],
        "add_transport": ["One more thing: {new}."],
        "delete_transport": ["We're open to every transportation option again."],
        "add_min_rating": ["Skip restaurants with a rating under {new}."],
        "delete_min_rating": ["Restaurant rating is no longer a concern."],
        "priority": ["From here on, optimize for {new}."],
        "delete_priority": ["Forget the earlier priority."],
    },
}


def render(d: ConstraintDiff, rng: random.Random, tset: str) -> str:
    key = d.target_type if d.target_type == "budget" else (
        "priority" if d.op == "reprioritize" else f"{d.op}_{d.target_type}")
    tmpl = rng.choice(TEMPLATES[tset][key])
    return tmpl.format(new=d.new if d.new is not None else "", old=d.old if d.old is not None else "")


@dataclass
class Turn:
    diff: dict
    feasible: bool
    constraints_after: dict  # ground-truth constraints once the turn is resolved


@dataclass
class Episode:
    episode_id: str
    qid: str
    split: str
    base: dict
    turns: list[Turn] = field(default_factory=list)
    initial_plan: dict | None = None  # set for "approved itinerary" episodes; else built by the planners

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(s: str) -> "Episode":
        d = json.loads(s)
        d["turns"] = [Turn(**t) for t in d["turns"]]
        return Episode(**d)


def base_constraints(q: Query, rng: random.Random) -> Constraints | None:
    if q.budget is not None:
        lc = q.local_constraint
        c = Constraints(budget=q.budget, people=q.people or 1, room_type=lc.get("room type"),
                        house_rules=[lc["house rule"]] if lc.get("house rule") else [],
                        cuisines=list(lc.get("cuisine") or []), transport=lc.get("transportation"))
    else:
        c = Constraints(budget=0, people=rng.choice([1, 1, 2, 2, 3, 4]))
        if rng.random() < 0.25:
            c.room_type = rng.choice(ROOM_TYPES)
        if rng.random() < 0.25:
            c.house_rules = [rng.choice(HOUSE_RULES)]
        if rng.random() < 0.15:
            c.transport = rng.choice(TRANSPORT_RULES)
        if rng.random() < 0.15:
            c.cuisines = rng.sample(CUISINES, 2)
        lo = min_cost(q, c)
        c.budget = round(lo * rng.uniform(1.2, 1.7) / 100) * 100
    return c if is_feasible(q, c) else None


def split_queries(qids: list[str], seed: int, frac=(0.6, 0.2, 0.2)) -> dict[str, str]:
    ids = sorted(qids)
    random.Random(seed).shuffle(ids)
    n = len(ids)
    a, b = int(frac[0] * n), int((frac[0] + frac[1]) * n)
    return {q: ("train" if i < a else "val" if i < b else "test") for i, q in enumerate(ids)}


def candidate_diffs(c: Constraints, q: Query, rng: random.Random,
                    plan_cost_now: float | None = None) -> list[ConstraintDiff]:
    served = sorted({cu for r in q.db.restaurants for cu in r.cuisines} & set(CUISINES))
    out: list[ConstraintDiff] = []
    ref = plan_cost_now or c.budget
    for f in (0.75, 0.85, 0.95):  # cuts relative to what the current plan costs
        out.append(ConstraintDiff("replace", "budget", c.budget, round(ref * f / 50) * 50))
    out.append(ConstraintDiff("replace", "budget", c.budget, round(c.budget * 1.25 / 50) * 50))
    if c.room_type is None:
        out.append(ConstraintDiff("add", "room_type", None, rng.choice(ROOM_TYPES)))
    else:
        out.append(ConstraintDiff("replace", "room_type", c.room_type,
                                  rng.choice([r for r in ROOM_TYPES if r != c.room_type])))
        out.append(ConstraintDiff("delete", "room_type", c.room_type, None))
    free_rules = [h for h in HOUSE_RULES if h not in c.house_rules]
    if free_rules:
        out.append(ConstraintDiff("add", "house_rule", None, rng.choice(free_rules)))
    for h in c.house_rules:
        out.append(ConstraintDiff("delete", "house_rule", h, None))
    free_cu = [cu for cu in served if cu not in c.cuisines]
    if free_cu:
        out.append(ConstraintDiff("add", "cuisine", None, rng.choice(free_cu)))
    if c.cuisines:
        old = rng.choice(c.cuisines)
        if free_cu:
            out.append(ConstraintDiff("replace", "cuisine", old, rng.choice(free_cu)))
        out.append(ConstraintDiff("delete", "cuisine", old, None))
    if c.transport is None:
        out.append(ConstraintDiff("add", "transport", None, rng.choice(TRANSPORT_RULES)))
    else:
        out.append(ConstraintDiff("delete", "transport", c.transport, None))
    if c.min_rating is None:
        out.append(ConstraintDiff("add", "min_rating", None, rng.choice([3.5, 4.0])))
    else:
        out.append(ConstraintDiff("delete", "min_rating", c.min_rating, None))
    others = [p for p in PRIORITIES if p != c.priority]
    out.append(ConstraintDiff("reprioritize", "priority", c.priority, rng.choice(others)))
    if c.priority:
        out.append(ConstraintDiff("delete", "priority", c.priority, None))
    return out


def _type_balanced(cands: list[ConstraintDiff], rng: random.Random) -> list[ConstraintDiff]:
    """Order candidates so each constraint type is equally likely to come first."""
    by_type: dict[str, list[ConstraintDiff]] = {}
    for d in cands:
        by_type.setdefault(d.target_type, []).append(d)
    for v in by_type.values():
        rng.shuffle(v)
    types = list(by_type)
    rng.shuffle(types)
    out = []
    while any(by_type.values()):
        for t in types:
            if by_type[t]:
                out.append(by_type[t].pop())
    return out


def make_episode(q: Query, base: Constraints, split: str, idx: int, rng: random.Random,
                 chain_len: int, tset: str, infeasible_rate: float = 0.12,
                 invalidating_rate: float = 0.75) -> Episode:
    """Sample a chain of updates against the plan a reference coordinator would hold.

    The reference (the privileged oracle) is only used to know which updates
    invalidate the current plan, so the mix of easy and hard turns is controlled.
    """
    from taskflow.agents.planners import compose_global
    from taskflow.coordinators.oracle import Oracle
    from taskflow.env.episode import TurnEnv
    from taskflow.env.tools import Cache
    from taskflow.env.verifier import verify

    ep = Episode(episode_id=f"{q.qid}-e{idx}", qid=q.qid, split=split, base=base.to_dict())
    c = base
    cache = Cache()
    plan = compose_global(q, c, cache)
    oracle = Oracle()
    for _ in range(chain_len):
        cost_now = verify(q, c, plan).total_cost
        cands = _type_balanced(candidate_diffs(c, q, rng, cost_now), rng)
        u = rng.random()
        want = ("infeasible" if u < infeasible_rate else
                "invalidating" if u < infeasible_rate + (1 - infeasible_rate) * invalidating_rate
                else "keeps")
        chosen, feas, kind_of = None, None, {}
        for d in cands:
            new_c = d.apply(c)
            keeps = verify(q, new_c, plan).passed
            # Feasible if the current plan already satisfies the update or the
            # planners can build one; the greedy planner alone is incomplete.
            f = keeps or is_feasible(q, new_c)
            kind = "infeasible" if not f else ("keeps" if keeps else "invalidating")
            kind_of[id(d)] = (kind, f)
            if kind == want:
                chosen, feas = d, f
                break
        if chosen is None:
            chosen = cands[0]
            feas = kind_of[id(chosen)][1]
        chosen.template_set = tset
        chosen.nl = render(chosen, rng, tset)
        after = chosen.apply(c) if feas else c
        if feas:
            env = TurnEnv(q, c, plan, cache, chosen.nl, random.Random(rng.random()))
            while not env.done:
                env.step(oracle.act(env))
            plan = env.plan
        ep.turns.append(Turn(diff=chosen.to_dict(), feasible=feas, constraints_after=after.to_dict()))
        c = after
    return ep


def build_dataset(queries: list[Query], seed: int, episodes_per_query: int = 4,
                  multi_per_query: int = 2) -> dict:
    rng = random.Random(seed)
    split_of = split_queries([q.qid for q in queries], seed)
    episodes: dict[str, list[Episode]] = {"train": [], "val": [], "test": []}
    bases: dict[str, dict] = {}
    for q in sorted(queries, key=lambda x: x.qid):
        base = base_constraints(q, rng)
        if base is None:
            continue
        bases[q.qid] = base.to_dict()
        s = split_of[q.qid]
        for i in range(episodes_per_query):
            # Held-out conditions: longer chains and template set B on test only.
            L = rng.randint(1, 4) if s == "test" else rng.randint(1, 3)
            tset = "B" if s == "test" else "A"
            episodes[s].append(make_episode(q, base, s, i, rng, L, tset))
    # Multi-component family: separate files and a separate RNG, so the v0
    # episodes above are unchanged by its presence.
    mrng = random.Random(seed + 7919)
    for s in ("train", "val", "test"):
        episodes[f"{s}_multi"] = []
    for q in sorted(queries, key=lambda x: x.qid):
        if q.qid not in bases:
            continue
        s = split_of[q.qid]
        for i in range(multi_per_query):
            ep = make_multi_episode(q, Constraints.from_dict(bases[q.qid]), s, i, mrng,
                                    "B" if s == "test" else "A")
            if ep is not None:
                episodes[f"{s}_multi"].append(ep)
    return {"episodes": episodes, "bases": bases, "split_of": split_of}


def _luxury_plan(q: Query, c: Constraints, cache) -> dict | None:
    """The most expensive valid choice per component (an itinerary the user approved)."""
    from taskflow.agents.planners import plan_attractions

    tr = cache.get("transport")
    combos = [(o.cost(c.people) + b.cost(c.people), o, b) for o in tr["out"] for b in tr["back"]
              if not ({o.mode, b.mode} >= {"self-driving"} and len({o.mode, b.mode}) > 1)]
    accs = cache.get("accommodation")
    rest = cache.get("dining")["restaurants"]
    if not combos or not accs or len(rest) < 6:
        return None
    _, o, b = max(combos, key=lambda x: (x[0], x[1].key, x[2].key))
    from taskflow.env.tools import acc_cost

    acc = max(accs, key=lambda a: (acc_cost(a, c.people), a.name))
    pricey = sorted(rest, key=lambda r: (-r.cost, r.name))
    chosen = []
    for cu in c.cuisines:  # cover required cuisines with the priciest option serving them
        r = next((r for r in pricey if cu in r.cuisines and r not in chosen), None)
        if r is None:
            return None
        if r not in chosen:
            chosen.append(r)
    for r in pricey:
        if len(chosen) >= 6:
            break
        if r not in chosen:
            chosen.append(r)
    plan = {"transport_out": o.key, "transport_back": b.key, "accommodation": acc.name}
    plan.update(zip(SLOTS_MEALS, [r.name for r in chosen[:6]]))
    plan.update(plan_attractions(cache.get("dining")))
    return plan


SLOTS_MEALS = ["d1_dinner", "d2_breakfast", "d2_lunch", "d2_dinner", "d3_breakfast", "d3_lunch"]


def make_multi_episode(q: Query, base: Constraints, split: str, idx: int, rng: random.Random,
                       tset: str) -> Episode | None:
    """One-turn episode: an expensive approved itinerary, then a budget cut that
    is impossible (level 0: ask) or needs 1, 2, or 3+ component repairs (3+ = beyond the oracle's two-repair
    search, so it falls back to a global rebuild). Built from real TravelPlanner
    trips of the given split only; the fixed synthetic stress cases in
    taskflow/data/challenges.py are never used for training.
    """
    from taskflow.coordinators.oracle import minimal_fix
    from taskflow.env.episode import TurnEnv
    from taskflow.env.tools import Cache
    from taskflow.env.verifier import verify

    c = base.copy()
    c.priority, c.min_rating = None, None
    cache = Cache()
    for name in ("transport", "accommodation", "dining"):
        cache.search(name, q, c)
    plan = _luxury_plan(q, c, cache)
    if plan is None:
        return None
    total = verify(q, Constraints(budget=1e9, people=c.people, room_type=c.room_type,
                                  house_rules=c.house_rules, cuisines=c.cuisines,
                                  transport=c.transport), plan).total_cost
    c.budget = float(round(total * 1.05 / 50 + 0.5) * 50)
    if not verify(q, c, plan).passed:
        return None
    by_level: dict[int, list[float]] = {0: [], 1: [], 2: [], 3: []}
    floor = min_cost(q, c)
    # Fractions of the approved plan's cost, plus cuts just above the cheapest
    # possible trip: feasible cases where the approved plan is far over budget,
    # so "far over budget" alone never means "impossible".
    targets = [total * x / 100 for x in range(90, 20, -5)] + [floor * f for f in (1.05, 1.15, 1.3, 1.5)]
    for t in sorted(set(round(t / 50) * 50 for t in targets), reverse=True):
        target = float(t)
        if target <= 0:
            continue
        new_c = c.copy()
        new_c.budget = target
        if verify(q, new_c, plan).passed or not is_feasible(q, new_c):
            continue
        env = TurnEnv(q, c, plan, cache.copy(), f"Let's change the budget to ${target:,.0f}.",
                      random.Random(0))
        fix = minimal_fix(env)
        by_level[len(fix) if fix else 3].append(target)
    # Level 0: a cut far below the cheapest possible trip (20-85% of it), where the
    # right response is to ask. Covers budgets well outside the v0 range.
    deep = float(round(floor * rng.uniform(0.2, 0.85) / 50) * 50)
    if deep > 0:
        new_c = c.copy()
        new_c.budget = deep
        if not is_feasible(q, new_c):
            by_level[0] = [deep]
    levels = [lv for lv in (0, 1, 2, 3) if by_level.get(lv)]
    if not levels:
        return None
    # Favour the harder feasible levels; impossible cuts stay a minority.
    weights = [{0: 1, 1: 2, 2: 3, 3: 4}[lv] for lv in levels]
    level = rng.choices(levels, weights=weights)[0]
    target = rng.choice(by_level[level])
    d = ConstraintDiff("replace", "budget", c.budget, target, template_set=tset)
    d.nl = render(d, rng, tset)
    feasible = level != 0
    after = d.apply(c) if feasible else c
    return Episode(episode_id=f"{q.qid}-m{idx}-L{level}", qid=q.qid, split=f"{split}_multi",
                   base=c.to_dict(), initial_plan=plan,
                   turns=[Turn(diff=d.to_dict(), feasible=feasible, constraints_after=after.to_dict())])


def save(ds: dict, out_dir: Path, manifest: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for s, eps in ds["episodes"].items():
        with open(out_dir / f"{s}.jsonl", "w") as f:
            for e in eps:
                f.write(e.to_json() + "\n")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


def load(out_dir: Path, split: str) -> list[Episode]:
    with open(out_dir / f"{split}.jsonl") as f:
        return [Episode.from_json(ln) for ln in f if ln.strip()]
