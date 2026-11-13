"""Independent regression checks for H1/H2/H3/H5."""
import itertools
import random

import pytest

from taskflow.common import baseline_policies
from taskflow.coordinators.oracle import Oracle, minimal_fix
from taskflow.data.challenges import budget_challenges
from taskflow.env.episode import TurnEnv
from taskflow.env.state import ALL_SLOTS, SLOTS
from taskflow.env.tools import Cache, search_accommodation, search_transport
from taskflow.env.verifier import verify
from taskflow.eval.exact import minimum_repair, revision_efficiency
from taskflow.llm.client import LLMClient


def env_for(case, llm=None):
    cache = Cache()
    for k in ('transport', 'accommodation', 'dining'):
        cache.search(k, case.query, case.before)
    return TurnEnv(case.query, case.before, case.plan, cache, case.diff.nl, random.Random(0), llm,
                   sample_global=False)


def test_challenges_require_the_claimed_component_count():
    for case in budget_challenges(per_level=2):
        env = env_for(case)
        assert verify(case.query, case.before, case.plan).passed
        assert not env.report.passed
        fix = minimal_fix(env)
        assert (len(fix) if fix else 3) == case.min_components
        exact = minimum_repair(case.query, env.c, case.plan)
        assert exact is not None and verify(case.query, env.c, exact.plan).passed
        oracle = Oracle()
        if case.min_components == 3:
            # The expert searches up to three component repairs, so it repairs
            # locally instead of rebuilding.
            assert fix is not None and len(fix) == 3 and oracle.act(env) != 'REPLAN_GLOBAL'
        while not env.done:
            env.step(oracle.act(env))
        assert verify(case.query, env.c, env.plan).passed


def test_exact_solver_matches_brute_force_with_cuisine_and_duplicate_start():
    case = budget_challenges(per_level=1)[0]
    q = case.query
    q.db.restaurants = q.db.restaurants[:7]
    q.db.restaurants[0].cuisines = ['Chinese']
    start = dict(case.plan)
    for slot, r in zip(SLOTS['meals'], q.db.restaurants[:6]):
        start[slot] = r.name
    start['d2_lunch'] = start['d1_dinner']  # duplicate can't earn two retained slots
    c = case.diff.apply(case.before)
    c.cuisines = ['Chinese', 'Italian']
    actual = minimum_repair(q, c, start)
    tr = search_transport(q, c)
    best = None
    # Exhaustive assignments, independently judged by the actual verifier.
    for meals in itertools.permutations(q.db.restaurants, 6):
        p = dict(start)
        p.update(zip(SLOTS['meals'], [r.name for r in meals]))
        for a, b, hotel in itertools.product(tr['out'], tr['back'], search_accommodation(q, c)):
            p.update(transport_out=a.key, transport_back=b.key, accommodation=hotel.name)
            report = verify(q, c, p)
            if report.passed:
                key = (sum(start.get(s) != p.get(s) for s in ALL_SLOTS), report.total_cost)
                best = min(best, key) if best else key
    assert actual is not None and (actual.edits, actual.cost) == best


@pytest.mark.parametrize('impossible', ['budget', 'cuisine', 'attractions'])
def test_exact_infeasibility(impossible):
    case = budget_challenges(per_level=1)[0]
    c = case.before.copy()
    if impossible == 'budget':
        c.budget = 0
    elif impossible == 'cuisine':
        c.cuisines = ['French']
    else:
        case.query.db.attractions = case.query.db.attractions[:3]
    assert minimum_repair(case.query, c, case.plan) is None


def test_preservation_scores_costed_slots_and_does_not_reward_failure():
    case = budget_challenges(per_level=1)[0]
    c = case.diff.apply(case.before)
    optimum = minimum_repair(case.query, c, case.plan)
    optimal = revision_efficiency(case.query, c, case.plan, optimum.plan)
    assert optimal['excess_edits'] == 0 and optimal['edit_optimal_preservation'] == 1
    assert optimal['minimum_edits'] > 0
    more = dict(optimum.plan)
    more['d1_dinner'], more['d2_breakfast'] = more['d2_breakfast'], more['d1_dinner']
    inefficient = revision_efficiency(case.query, c, case.plan, more)
    assert inefficient['excess_edits'] > 0 and inefficient['edit_optimal_preservation'] < 1
    failed = revision_efficiency(case.query, c, case.plan, case.plan)
    assert all(v is None for v in failed.values())


def test_oracle_is_restricted_before_any_llm_repair():
    case = budget_challenges(per_level=1)[-1]
    client = LLMClient('fake', 'fake', use_cache=False)
    env = env_for(case, client)
    before = client.usage.requests
    with pytest.raises(ValueError, match='deterministic transitions only'):
        Oracle().act(env)
    assert client.usage.requests == before and not env.history
    assert 'oracle' not in baseline_policies(client)
    assert 'oracle' in baseline_policies()


def test_preservation_is_undefined_if_every_slot_must_change():
    case = budget_challenges(per_level=1)[0]
    start = {s: 'unavailable' for s in ALL_SLOTS}
    optimum = minimum_repair(case.query, case.before, start)
    score = revision_efficiency(case.query, case.before, start, optimum.plan)
    assert score == {'minimum_edits': 13, 'excess_edits': 0, 'edit_optimal_preservation': None}


def test_live_error_labels_are_disabled(monkeypatch):
    from scripts import evaluate
    monkeypatch.setattr(evaluate, 'LLM', object())
    assert evaluate.error_by_step(None, [], {}) == {'by_step': {}, 'by_turn': {}}
