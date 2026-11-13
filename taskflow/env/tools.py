"""Search tools over a trip's database slice, plus pricing.

Tools filter candidates by the constraints that were active when they were
called. Results are kept in a per-component cache; a cache becomes stale
when a constraint that affects its filter changes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from taskflow.data.travelplanner import Accommodation, CityDB, Query, Restaurant
from taskflow.env.state import Constraints


@dataclass
class TransportOption:
    key: str  # "flight:F123" | "self-driving" | "taxi"
    mode: str
    unit_cost: float

    def cost(self, people: int) -> float:
        if self.mode == "flight":
            return self.unit_cost * people
        if self.mode == "self-driving":
            return self.unit_cost * math.ceil(people / 5)
        return self.unit_cost * math.ceil(people / 4)


def _conflict_free_min(cands: dict, people: int) -> float | None:
    """Cheapest valid out+back combination in a transport cache, or None."""
    best = None
    for o in cands["out"]:
        for b in cands["back"]:
            m = {o.mode, b.mode}
            if "self-driving" in m and len(m) > 1:
                continue
            v = o.cost(people) + b.cost(people)
            best = v if best is None or v < best else best
    return best


def room_ok(acc: Accommodation, room_type: str | None) -> bool:
    if room_type is None:
        return True
    rt = acc.room_type
    return {
        "entire room": rt == "Entire home/apt",
        "private room": rt == "Private room",
        "shared room": rt == "Shared room",
        "not shared room": rt != "Shared room",
    }[room_type]


def rules_ok(acc: Accommodation, rules: list[str]) -> bool:
    return all(f"No {r}" not in acc.house_rules for r in rules)


def acc_cost(acc: Accommodation, people: int, nights: int = 2) -> float:
    return acc.price * math.ceil(people / max(acc.max_occupancy, 1)) * nights


def transport_options(q: Query, c: Constraints, leg: str) -> list[TransportOption]:
    o, d = (q.org, q.dest) if leg == "out" else (q.dest, q.org)
    date = q.dates[0] if leg == "out" else q.dates[-1]
    opts: list[TransportOption] = []
    if c.transport != "no flight":
        for f in q.db.flights.get((o, d, date), []):
            opts.append(TransportOption(f"flight:{f.number}", "flight", f.price))
    for mode in ("self-driving", "taxi"):
        if mode == "self-driving" and c.transport == "no self-driving":
            continue
        g = q.db.ground.get((mode, o, d))
        if g:
            opts.append(TransportOption(mode, mode, g.cost))
    return opts


def search_transport(q: Query, c: Constraints) -> dict:
    return {"out": transport_options(q, c, "out"), "back": transport_options(q, c, "back")}


def search_accommodation(q: Query, c: Constraints) -> list[Accommodation]:
    return [a for a in q.db.accommodations
            if room_ok(a, c.room_type) and rules_ok(a, c.house_rules) and a.min_nights <= 2
            and (c.priority != "quality" or a.rating >= 4.0)]


def search_dining(q: Query, c: Constraints) -> dict:
    rest: list[Restaurant] = [r for r in q.db.restaurants
                              if c.min_rating is None or r.rating >= c.min_rating]
    return {"restaurants": rest, "attractions": list(q.db.attractions)}


SEARCH_FN = {"transport": search_transport, "accommodation": search_accommodation,
             "dining": search_dining}


class Cache:
    """Per-component cached search results tagged with the filter they used."""

    def __init__(self):
        self.data: dict[str, object] = {}
        self.key: dict[str, tuple] = {}

    def search(self, cache: str, q: Query, c: Constraints) -> None:
        self.data[cache] = SEARCH_FN[cache](q, c)
        self.key[cache] = c.cache_key(cache)

    def fresh(self, cache: str, c: Constraints) -> bool:
        return cache in self.data and self.key[cache] == c.cache_key(cache)

    def get(self, cache: str):
        return self.data.get(cache)

    def copy(self) -> "Cache":
        n = Cache()
        n.data, n.key = dict(self.data), dict(self.key)
        return n


def lookup_index(db: CityDB) -> dict:
    return {
        "restaurant": {r.name: r for r in db.restaurants},
        "accommodation": {a.name: a for a in db.accommodations},
        "attraction": {a.name: a for a in db.attractions},
    }
