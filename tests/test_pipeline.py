import random

import numpy as np
import pytest

from taskflow.agents import tracker
from taskflow.agents.planners import compose_global
from taskflow.common import TASKS_DIR
from taskflow.coordinators.baselines import AlwaysGlobal, StaticRules
from taskflow.coordinators.oracle import Oracle
from taskflow.data.tasks import TEMPLATES, build_dataset, candidate_diffs, load, render, split_queries
from taskflow.data.travelplanner import load_queries
from taskflow.env.episode import TurnEnv, run_episode
from taskflow.env.state import ConstraintDiff, Constraints
from taskflow.env.tools import Cache
from taskflow.env.verifier import verify
from taskflow.learning.encode import action_mask, encode


@pytest.fixture(scope="module")
def Q():
    return {q.qid: q for q in load_queries()}


@pytest.fixture(scope="module")
def small(Q):
    qs = sorted(Q.values(), key=lambda q: q.qid)[:30]
    return build_dataset(qs, seed=1, episodes_per_query=2)


def test_splits_are_disjoint_by_query():
    split = split_queries([f"q{i}" for i in range(100)], seed=0)
    assert set(split.values()) == {"train", "val", "test"}
    assert len(split) == 100


def test_saved_dataset_has_no_query_leakage():
    if not (TASKS_DIR / "train.jsonl").exists():
        pytest.skip("dataset not built")
    seen = {s: {e.qid for e in load(TASKS_DIR, s)} for s in ("train", "val", "test")}
    assert not (seen["train"] & seen["val"]) and not (seen["train"] & seen["test"])
    assert not (seen["val"] & seen["test"])


def test_held_out_conditions_only_in_test(small):
    for s in ("train", "val"):
        for e in small["episodes"][s]:
            assert len(e.turns) <= 3
            assert all(t.diff["template_set"] == "A" for t in e.turns)
    assert all(t.diff["template_set"] == "B" for e in small["episodes"]["test"] for t in e.turns)


@pytest.mark.parametrize("tset", ["A", "B"])
def test_tracker_recovers_every_diff(Q, tset):
    rng = random.Random(0)
    q = next(iter(Q.values()))
    c = Constraints(budget=2000, people=2, room_type="private room", house_rules=["pets"],
                    cuisines=["Chinese"], transport="no flight", min_rating=3.5, priority="cost")
    for base in (c, Constraints(budget=1500)):
        for d in candidate_diffs(base, q, rng):
            for _ in range(3):
                nl = render(d, rng, tset)
                parsed = tracker.parse(nl, base)
                assert parsed.apply(base).to_dict() == d.apply(base).to_dict(), nl


def test_every_template_key_exists_in_both_sets():
    assert set(TEMPLATES["A"]) == set(TEMPLATES["B"])


def test_oracle_solves_every_turn(small, Q):
    eps = small["episodes"]["train"] + small["episodes"]["test"]
    for i, e in enumerate(eps):
        r = run_episode(e, Q[e.qid], Oracle(), seed=i)
        assert all(t.success for t in r.turns), (e.episode_id, [t.actions for t in r.turns])


@pytest.mark.parametrize("pol", [StaticRules(), AlwaysGlobal()])
def test_baselines_terminate(small, Q, pol):
    for i, e in enumerate(small["episodes"]["val"]):
        r = run_episode(e, Q[e.qid], pol, seed=i)
        assert all(t.terminal != "TIMEOUT" for t in r.turns)


def test_episode_is_deterministic(small, Q):
    e = small["episodes"]["train"][0]
    a = run_episode(e, Q[e.qid], AlwaysGlobal(), seed=5).to_dict()
    b = run_episode(e, Q[e.qid], AlwaysGlobal(), seed=5).to_dict()
    assert a == b


def test_initial_plans_are_valid(small, Q):
    for e in small["episodes"]["train"]:
        q, c = Q[e.qid], Constraints.from_dict(e.base)
        assert verify(q, c, compose_global(q, c, Cache())).passed


def test_encoder_shape_and_mask(small, Q):
    e = small["episodes"]["train"][0]
    q, c = Q[e.qid], Constraints.from_dict(e.base)
    cache = Cache()
    plan = compose_global(q, c, cache)
    env = TurnEnv(q, c, plan, cache, ConstraintDiff.from_dict(e.turns[0].diff).nl, random.Random(0))
    x = encode(env)
    assert x.dtype == np.float32 and x.ndim == 1 and np.isfinite(x).all()
    env.step("REPLAN_LOCAL_MEALS")
    assert not action_mask(env)[0]  # KEEP_PLAN is masked once something changed
    assert encode(env).shape == x.shape
