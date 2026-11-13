"""Independent, synthetic multi-component budget revisions (not canonical data).

A valid, deliberately expensive user-approved itinerary precedes a budget
cut. The three levels require >=1, >=2, or >=3 component repairs. A global
rebuild is necessary only relative to the oracle's <=2-local-repair search:
three local actions can also solve the hardest cases. This distinction is
part of the benchmark contract, not an implicit change to action semantics.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from taskflow.data.travelplanner import Accommodation, Attraction, CityDB, Flight, Query, Restaurant
from taskflow.env.state import SLOTS, ConstraintDiff, Constraints, Plan


@dataclass
class Challenge:
    name: str
    query: Query
    before: Constraints
    diff: ConstraintDiff
    plan: Plan
    min_components: int


def budget_challenges(seed: int = 0, per_level: int = 4) -> list[Challenge]:
    rng = random.Random(seed)
    cases = []
    for level in (1, 2, 3):
        for i in range(per_level):
            scale = rng.randint(1, 9)
            db = CityDB()
            dates = ['2026-01-01', '2026-01-02', '2026-01-03']
            for leg, origin, dest, date in [('out', 'Origin', 'Destination', dates[0]),
                                            ('back', 'Destination', 'Origin', dates[-1])]:
                db.flights[(origin, dest, date)] = [
                    Flight(f'{leg}-cheap', 10*scale, '09:00', '10:00', date, origin, dest),
                    Flight(f'{leg}-approved', 100*scale, '09:00', '10:00', date, origin, dest)]
            db.accommodations = [Accommodation('cheap stay', 5*scale, 'Private room', '', 1, 2, 4, 'Destination'),
                                 Accommodation('approved stay', 50*scale, 'Private room', '', 1, 2, 5, 'Destination')]
            db.restaurants = [Restaurant(f'{kind} meal {j}', price*scale, ['Italian'], 4, 'Destination')
                              for kind, price in [('cheap', 1), ('approved', 20)] for j in range(6)]
            db.attractions = [Attraction(f'attraction {j}', 'Destination') for j in range(4)]
            name = f'budget-{level}-components-{i}'
            q = Query(name, 'synthetic', 'Origin', 'Destination', dates, 1, 500*scale, {}, '', 'challenge', db)
            before = Constraints(500*scale)
            target = {1: 300, 2: 150, 3: 50}[level]*scale
            diff = ConstraintDiff('replace', 'budget', before.budget, target,
                                  nl=f"Let's change the budget to ${target:,.0f}.")
            plan = {'transport_out': 'flight:out-approved', 'transport_back': 'flight:back-approved',
                    'accommodation': 'approved stay'}
            plan.update(zip(SLOTS['meals'], [f'approved meal {j}' for j in range(6)]))
            plan.update(zip(SLOTS['attractions'], [f'attraction {j}' for j in range(4)]))
            cases.append(Challenge(name, q, before, diff, plan, level))
    return cases
