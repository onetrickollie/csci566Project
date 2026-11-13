"""Multi-component family: split hygiene, validity, and separation from the stress suite."""

import json

import pytest

from taskflow.common import TASKS_DIR
from taskflow.coordinators.oracle import Oracle
from taskflow.data.tasks import load
from taskflow.data.travelplanner import load_queries
from taskflow.env.episode import run_episode
from taskflow.env.state import Constraints
from taskflow.env.verifier import verify

pytestmark = pytest.mark.skipif(not (TASKS_DIR / "train_multi.jsonl").exists(), reason="dataset not built")


@pytest.fixture(scope="module")
def Q():
    return {q.qid: q for q in load_queries()}


def test_multi_episodes_stay_in_their_query_split():
    split_of = json.loads((TASKS_DIR / "split_of_query.json").read_text())
    for s in ("train", "val", "test"):
        for e in load(TASKS_DIR, f"{s}_multi"):
            assert split_of[e.qid] == s
            assert not e.qid.startswith("budget-")  # synthetic stress cases are never stored here


def test_multi_initial_plans_valid_and_solved(Q):
    eps = load(TASKS_DIR, "val_multi")
    assert {e.episode_id.rsplit("-L", 1)[1] for e in eps} >= {"1", "2"}
    for i, e in enumerate(eps):
        q = Q[e.qid]
        assert verify(q, Constraints.from_dict(e.base), e.initial_plan).passed
        r = run_episode(e, q, Oracle(), seed=i)
        assert r.turns[0].success, e.episode_id
        if e.episode_id.endswith("-L0"):
            assert r.turns[0].terminal == "ASK_CLARIFICATION"


def test_retrained_model_solves_synthetic_stress_suite():
    import random

    from taskflow.common import MODELS_DIR, learned_policy
    from taskflow.data.challenges import budget_challenges
    from taskflow.env.episode import TurnEnv
    from taskflow.env.tools import Cache

    if not (MODELS_DIR / "bc_aug_dagger3_s0.pt").exists():
        pytest.skip("models not trained")
    pol = learned_policy("bc_aug_dagger3", 0)
    for case in budget_challenges(0):
        cache = Cache()
        for k in ("transport", "accommodation", "dining"):
            cache.search(k, case.query, case.before)
        env = TurnEnv(case.query, case.before, case.plan, cache, case.diff.nl, random.Random(0))
        while not env.done:
            env.step(pol.act(env))
        assert env.terminal == "STOP" and verify(case.query, env.c, env.plan).passed, case.name


def test_r3_recovery_selection_uses_initial_plan(Q):
    sys_path = __import__("sys").path
    from pathlib import Path

    sys_path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import evaluate

    eps = load(TASKS_DIR, "test_multi")
    selected = sum(evaluate.needs_repair_first_turn(e, Q) for e in eps)
    assert selected == sum(e.turns[0].feasible for e in eps)  # every feasible cut breaks the approved plan


def test_cost_aware_static_baseline_solves_multi(Q):
    from taskflow.coordinators.baselines import StaticRulesCostAware

    for i, e in enumerate(load(TASKS_DIR, "val_multi")):
        r = run_episode(e, Q[e.qid], StaticRulesCostAware(), seed=i)
        assert r.turns[0].success, (e.episode_id, r.turns[0].actions)
