"""LLM plumbing, exercised with the offline fake backend and a broken stub."""

import json
import random

import pytest

from taskflow.agents import llm_planners, tracker
from taskflow.agents.planners import compose_global, plan_accommodation, plan_meals
from taskflow.common import TASKS_DIR
from taskflow.coordinators.llm_coordinator import LLMCoordinator, state_summary
from taskflow.data.tasks import load
from taskflow.data.travelplanner import load_queries
from taskflow.env.episode import TurnEnv, run_episode
from taskflow.env.state import ACTIONS, Constraints
from taskflow.env.tools import Cache
from taskflow.env.verifier import verify
from taskflow.llm import client as client_mod
from taskflow.llm.client import LLMClient, extract_json, get_client


class Garbage:
    """A client whose replies are never valid."""

    def __init__(self):
        self.usage = client_mod.Usage()

    def complete_json(self, system, user, max_tokens=600):
        self.usage.requests += 1
        return {"name": "No Such Place", "action": "FLY_TO_MOON", "restaurants": ["x"],
                "attractions": [], "op": "add", "target_type": "budget", "new": -5}


@pytest.fixture(scope="module")
def Q():
    return {q.qid: q for q in load_queries()}


@pytest.fixture()
def fake(tmp_path, monkeypatch):
    monkeypatch.setattr(client_mod, "CACHE_DIR", tmp_path / "llm")
    return get_client("fake")


def test_offline_means_no_client(monkeypatch):
    monkeypatch.setenv("TASKFLOW_LLM_PROVIDER", "offline")
    assert get_client() is None


def test_real_provider_requires_model_and_key(monkeypatch):
    monkeypatch.delenv("TASKFLOW_LLM_MODEL", raising=False)
    with pytest.raises(client_mod.LLMError):
        get_client("openai")


def test_extract_json_tolerates_fences():
    assert extract_json('Sure!\n```json\n{"action": "VERIFY"}\n```') == {"action": "VERIFY"}


def test_cache_and_usage(fake):
    s, u = "ROLE: coordinator\n", 'INPUT:\n' + json.dumps(
        {"verifier": {"fresh": False, "passed": False, "violated_components": []},
         "actions_this_turn": [], "changed_components": [], "cache_fresh": {}})
    a = fake.complete(s, u)
    b = fake.complete(s, u)
    assert a == b
    assert fake.usage.calls == 1 and fake.usage.cache_hits == 1 and fake.usage.requests == 2


def test_llm_tracker_matches_rules(fake):
    c = Constraints(budget=2000, cuisines=["Chinese"])
    for msg in ["Let's change the budget to $1,500.", "Swap the Chinese food requirement for Mexican.",
                "The place needs to allow pets.", "Now quality matters more to me than anything else."]:
        d, src = tracker.parse_any(msg, c, fake)
        assert src == "llm"
        assert d.apply(c).to_dict() == tracker.parse(msg, c).apply(c).to_dict()


def test_llm_tracker_falls_back_on_invalid_reply():
    c = Constraints(budget=2000)
    d, src = tracker.parse_any("Let's change the budget to $1,500.", c, Garbage())
    assert src == "rules" and d.new == 1500.0


def test_planners_fall_back_on_invalid_reply(Q):
    q = next(iter(Q.values()))
    c = Constraints(budget=5000, people=1)
    cache = Cache()
    compose_global(q, c, cache)
    default = plan_accommodation(cache.get("accommodation"), c, 3000)
    assert llm_planners.accommodation(Garbage(), cache.get("accommodation"), c, 3000, default) == default
    dm = plan_meals(cache.get("dining"), c)
    assert llm_planners.meals(Garbage(), cache.get("dining"), c, dm) == dm


def test_llm_global_plan_is_valid(Q, fake):
    q = next(iter(Q.values()))
    c = Constraints(budget=5000, people=1)
    assert verify(q, c, compose_global(q, c, Cache(), llm=fake)).passed


def test_coordinator_returns_valid_actions_and_falls_back(Q, fake):
    q = next(iter(Q.values()))
    c = Constraints(budget=5000, people=1)
    cache = Cache()
    plan = compose_global(q, c, cache)
    env = TurnEnv(q, c, plan, cache, "Let's change the budget to $300.", random.Random(0))
    json.dumps(state_summary(env))  # must be serializable
    assert LLMCoordinator(fake).act(env) in ACTIONS
    bad = LLMCoordinator(Garbage())
    assert bad.act(env) in ACTIONS and bad.fallbacks == 1


def test_episode_with_fake_llm_records_measured_usage(Q, fake):
    if not (TASKS_DIR / "test.jsonl").exists():
        pytest.skip("dataset not built")
    for i, ep in enumerate(load(TASKS_DIR, "test")[:5]):
        r = run_episode(ep, Q[ep.qid], LLMCoordinator(fake), seed=i, llm=fake)
        assert all(t.measured_llm_calls is not None and t.measured_llm_calls >= 1 for t in r.turns)
        assert all(t.terminal != "TIMEOUT" for t in r.turns)


def test_fake_client_is_an_llmclient(fake):
    assert isinstance(fake, LLMClient) and fake.label == "fake:fake"
