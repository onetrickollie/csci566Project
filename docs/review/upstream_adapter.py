"""Pinned TravelPlanner evaluator adapter; no vendored upstream code/data.

Loads unmodified function bodies from an explicitly supplied checkout. Only
3-day, single-city exports are supported. Query-slice tables stand in for
the full database; ground prices are independently parsed from upstream
reference JSON. City membership is limited to the supplied query cities.
This is NOT an official leaderboard or full-database evaluation.
"""
from __future__ import annotations

import ast
import json
import math
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

UPSTREAM_SHA = 'e52c87f4ac348a3410c46dc3553c519db5ec5e23'


def _functions(path: Path, namespace: dict) -> None:
    tree = ast.parse(path.read_text())
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    exec(compile(tree, str(path), 'exec'), namespace)


class UpstreamAdapter:
    def __init__(self, checkout: Path, queries: dict):
        import numpy as np
        import pandas as pd
        self.pd = pd
        sha = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
        if sha != UPSTREAM_SHA:
            raise ValueError(f'Expected upstream {UPSTREAM_SHA}, found {sha}')
        changed = subprocess.check_output(['git', '-C', str(checkout), 'diff', 'HEAD', '--',
                                          'evaluation', 'utils/func.py', 'database'], text=True)
        if changed:
            raise ValueError('Upstream evaluator/data checkout must be unmodified')
        base = {'re': re, 'math': math, 'json': json, 'np': np}
        _functions(checkout / 'utils/func.py', base)
        self.hard, self.common = dict(base), dict(base)
        _functions(checkout / 'evaluation/hard_constraint.py', self.hard)
        _functions(checkout / 'evaluation/commonsense_constraint.py', self.common)
        self.common['city_state_map'] = {city: '' for q in queries.values() for city in (q.org, q.dest)}
        self.raw = {s: [json.loads(line) for line in (checkout / f'database/{s}_ref_info.jsonl').read_text().splitlines()]
                    for s in ('train', 'validation', 'test')}
        self.bound = None

    def bind(self, q):
        if self.bound == q.qid:
            return
        refs = self.raw[q.source_split][int(q.qid.rsplit('-', 1)[1])]
        for obj, prefix in [('flight', 'Flight from'), ('restaurants', 'Restaurants in'),
                            ('accommodation', 'Accommodations in'), ('attractions', 'Attractions in')]:
            rows = [r for k, value in refs.items() if k.startswith(prefix) and isinstance(value, list) for r in value]
            table = self.pd.DataFrame(rows).drop_duplicates().reset_index(drop=True)
            if obj == 'flight' and table.empty:
                table = self.pd.DataFrame(columns=['Flight Number', 'Price', 'OriginCityName', 'DestCityName'])
            for namespace in (self.hard, self.common):
                namespace[obj] = SimpleNamespace(data=table)
        def ground(origin, destination, mode):
            text = refs.get(f'{mode.capitalize()} from {origin} to {destination}', '')
            match = re.search(r'cost: ([\d,.]+)', text) if isinstance(text, str) else None
            return {'cost': float(match[1].replace(',', '')) if match else None}
        for namespace in (self.hard, self.common):
            namespace['googleDistanceMatrix'] = SimpleNamespace(run_for_evaluation=ground)
        self.bound = q.qid

    def evaluate(self, q, c, plan):
        self.bind(q)
        exported = export_plan(q, plan)
        question = dict(days=3, org=q.org, dest=q.dest, visiting_city_number=1,
                        people_number=c.people, budget=c.budget, local_constraint={
                            'cuisine': c.cuisines, 'house rule': c.house_rules[0] if c.house_rules else None,
                            'room type': c.room_type, 'transportation': c.transport})
        checks = {**self.hard['evaluation'](question, exported), **self.common['evaluation'](question, exported)}
        for rule in c.house_rules:
            question['local_constraint']['house rule'] = rule
            result = self.hard['is_valid_room_rule'](question, exported)
            if result[0] is False:
                checks['valid_room_rule'] = result
        return {'cost': float(self.hard['get_total_cost'](question, exported)),
                'failures': {k: list(v) for k, v in checks.items() if v[0] is False}}


def export_plan(q, plan):
    def entity(slot):
        return f'{plan[slot]}, {q.dest}' if plan.get(slot, '-') != '-' else '-'
    def transport(slot, origin, dest):
        value = plan[slot]
        mode = f'Flight Number: {value[7:]}' if value.startswith('flight:') else value.capitalize()
        return f'{mode}, from {origin} to {dest}'
    return [
        dict(days=1, current_city=f'from {q.org} to {q.dest}',
             transportation=transport('transport_out', q.org, q.dest), breakfast='-', lunch='-',
             dinner=entity('d1_dinner'), attraction=entity('d1_attraction')+';', accommodation=entity('accommodation')),
        dict(days=2, current_city=q.dest, transportation='-', breakfast=entity('d2_breakfast'),
             lunch=entity('d2_lunch'), dinner=entity('d2_dinner'),
             attraction=entity('d2_attraction_1')+';'+entity('d2_attraction_2')+';', accommodation=entity('accommodation')),
        dict(days=3, current_city=f'from {q.dest} to {q.org}',
             transportation=transport('transport_back', q.dest, q.org), breakfast=entity('d3_breakfast'),
             lunch=entity('d3_lunch'), dinner='-', attraction=entity('d3_attraction')+';', accommodation='-')]
