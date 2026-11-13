"""A merged database for the interactive app: every city in TravelPlanner.

Each TravelPlanner query ships a slice of the database. Merging all 1,225
slices gives restaurants, hotels and attractions for every destination city,
flights for the (origin, destination, date) combinations that appear in the
data (March 2022), and driving/taxi records for the city pairs that appear.

For a pair with no recorded driving/taxi option, the app can estimate one
from the straight-line distance between the two cities' attraction
coordinates, scaled to road distance and priced with the same per-km rates
as the recorded records (both calibrated from the data). Estimated options
are marked ``estimated=True`` and labelled in the UI. Flights are never
invented.

The benchmark (data/tasks) does not use this module.
"""

from __future__ import annotations

import ast
import csv
import difflib
import math
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

from taskflow.data.travelplanner import (RAW_DIR, CityDB, Flight, Ground, Query, ensure_downloaded,
                                         parse_reference_information)

csv.field_size_limit(10**9)


def _haversine(a, b) -> float:
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


@dataclass
class World:
    restaurants: dict = field(default_factory=dict)      # city -> list[Restaurant]
    accommodations: dict = field(default_factory=dict)   # city -> list[Accommodation]
    attractions: dict = field(default_factory=dict)      # city -> list[Attraction]
    flights: dict = field(default_factory=dict)          # (org, dest, date) -> list[Flight]
    ground: dict = field(default_factory=dict)           # (mode, org, dest) -> Ground
    coords: dict = field(default_factory=dict)           # city -> (lat, lon)
    origins: set = field(default_factory=set)
    road_factor: float = 1.25
    rate: dict = field(default_factory=lambda: {"self-driving": 0.05, "taxi": 1.0})
    kmh: float = 100.0

    # ------------------------------------------------------------------
    @property
    def destinations(self) -> list[str]:
        """Cities with enough data to plan a full 3-day stay."""
        return sorted(c for c in self.restaurants
                      if len(self.restaurants[c]) >= 6 and self.accommodations.get(c)
                      and len(self.attractions.get(c, [])) >= 4)

    @property
    def start_cities(self) -> list[str]:
        return sorted(set(self.origins) | set(self.destinations))

    def resolve(self, name: str, choices: list[str]) -> tuple[str | None, list[str]]:
        """Case-insensitive exact match, else (None, close suggestions)."""
        by_low = {c.lower(): c for c in choices}
        key = name.strip().lower()
        if key in by_low:
            return by_low[key], []
        starts = [c for c in choices if c.lower().startswith(key)] if key else []
        if len(starts) == 1:
            return starts[0], []
        close = difflib.get_close_matches(name.strip(), choices, n=5, cutoff=0.6)
        return None, (starts[:5] or close)

    def flight_dates(self, org: str, dest: str) -> list[str]:
        """Start dates for which both the outbound and the return flight exist."""
        out = []
        for (o, d, dt) in self.flights:
            if o == org and d == dest:
                back = (date.fromisoformat(dt) + timedelta(days=2)).isoformat()
                if (dest, org, back) in self.flights:
                    out.append(dt)
        return sorted(set(out))

    def ground_option(self, mode: str, org: str, dest: str) -> Ground | None:
        g = self.ground.get((mode, org, dest)) or self.ground.get((mode, dest, org))
        if g is not None:
            return Ground(mode, org, dest, g.cost, g.duration, g.distance_km)
        if org in self.coords and dest in self.coords:
            km = _haversine(self.coords[org], self.coords[dest]) * self.road_factor
            hours = km / self.kmh
            return Ground(mode, org, dest, round(km * self.rate[mode]),
                          f"{int(hours)} hours {int(round((hours % 1) * 60))} mins", round(km),
                          estimated=True)
        return None

    def trip_query(self, org: str, dest: str, start: str, people: int, budget: float) -> Query:
        """A TravelPlanner-style query for a 3-day trip between any two known cities."""
        d0 = date.fromisoformat(start)
        dates = [(d0 + timedelta(days=i)).isoformat() for i in range(3)]
        db = CityDB(restaurants=list(self.restaurants[dest]),
                    accommodations=list(self.accommodations[dest]),
                    attractions=list(self.attractions[dest]))
        for o, d, dt in ((org, dest, dates[0]), (dest, org, dates[-1])):
            if (o, d, dt) in self.flights:
                db.flights[(o, d, dt)] = list(self.flights[(o, d, dt)])
            for mode in ("self-driving", "taxi"):
                g = self.ground_option(mode, o, d)
                if g is not None:
                    db.ground[(mode, o, d)] = g
        text = (f"Plan a 3-day trip from {org} to {dest}, {dates[0]} to {dates[-1]}, "
                f"for {people} traveler(s) with a budget of ${budget:,.0f}.")
        return Query(qid=f"custom:{org}->{dest}:{start}", source_split="custom", org=org, dest=dest,
                     dates=dates, people=people, budget=budget, local_constraint={}, text=text,
                     level="custom", db=db)


def build_world() -> World:
    ensure_downloaded()
    w = World()
    seen = {"r": set(), "a": set(), "t": set()}
    for f in ("train.csv", "validation.csv", "test.csv"):
        with open(RAW_DIR / f) as fh:
            for row in csv.DictReader(fh):
                w.origins.add(row["org"])
                db = parse_reference_information(ast.literal_eval(row["reference_information"]))
                for r in db.restaurants:
                    if (r.city, r.name) not in seen["r"]:
                        seen["r"].add((r.city, r.name))
                        w.restaurants.setdefault(r.city, []).append(r)
                for a in db.accommodations:
                    if (a.city, a.name) not in seen["a"]:
                        seen["a"].add((a.city, a.name))
                        w.accommodations.setdefault(a.city, []).append(a)
                for a in db.attractions:
                    if (a.city, a.name) not in seen["t"]:
                        seen["t"].add((a.city, a.name))
                        w.attractions.setdefault(a.city, []).append(a)
                for k, fl in db.flights.items():
                    have = {x.number for x in w.flights.get(k, [])}
                    w.flights.setdefault(k, []).extend(x for x in fl if x.number not in have)
                w.ground.update(db.ground)
    for city, attrs in w.attractions.items():
        pts = [(a.lat, a.lon) for a in attrs if a.lat is not None and a.lon is not None]
        if pts:
            w.coords[city] = (statistics.median(p[0] for p in pts), statistics.median(p[1] for p in pts))
    _calibrate(w)
    return w


def _calibrate(w: World) -> None:
    """Fit road factor, per-km rates and speed from recorded driving/taxi records."""
    factors, kmh, rates = [], [], {"self-driving": [], "taxi": []}
    for (mode, o, d), g in w.ground.items():
        if not g.distance_km:
            continue
        rates[mode].append(g.cost / g.distance_km)
        if o in w.coords and d in w.coords:
            straight = _haversine(w.coords[o], w.coords[d])
            if straight > 30:
                factors.append(g.distance_km / straight)
        parts = g.duration.split()
        try:
            hours = (float(parts[0]) + float(parts[2]) / 60) if "hour" in g.duration else float(parts[0]) / 60
            if hours > 0.5:
                kmh.append(g.distance_km / hours)
        except (ValueError, IndexError):
            pass
    if factors:
        w.road_factor = statistics.median(factors)
    for mode, xs in rates.items():
        if xs:
            w.rate[mode] = statistics.median(xs)
    if kmh:
        w.kmh = statistics.median(kmh)


__all__ = ["World", "build_world", "Flight"]
