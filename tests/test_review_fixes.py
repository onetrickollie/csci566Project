"""Regressions for review findings (docs/SUPERVISOR_REVIEW.md). Each test is the
reviewer's counterexample turned into an assertion. No network calls."""

import json
import random

import pytest

from taskflow.agents import tracker
from taskflow.agents.planners import compose_global, replan_local
from taskflow.common import TASKS_DIR
from taskflow.coordinators.baselines import StaticRules
from taskflow.coordinators.llm_coordinator import LLMCoordinator, state_summary
from taskflow.data.tasks import load
from taskflow.data.travelplanner import _split_table, load_queries
from taskflow.env.episode import TurnEnv, run_episode
from taskflow.env.state import ConstraintDiff, Constraints
from taskflow.env.tools import Cache
from taskflow.env.verifier import verify
from taskflow.learning.encode import encode
from taskflow.llm import client as cm
from taskflow.llm.client import LLMClient, LLMError, LLMFatalError


@pytest.fixture(scope="module")
def Q():
    return {q.qid: q for q in load_queries()}


@pytest.fixture()
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "CACHE_DIR", tmp_path / "llm")


# --- N1: cache identity includes the endpoint --------------------------------
def test_n1_cache_isolated_per_endpoint(tmp_cache):
    class Echo(LLMClient):
        def _call(self, s, u, m):
            return self.base_url, 10, 5

    a = Echo("openai", "same-model", base_url="https://server-a.invalid/v1")
    b = Echo("openai", "same-model", base_url="https://server-b.invalid/v1")
    assert a.complete("s", "u") == "https://server-a.invalid/v1"
    assert b.complete("s", "u") == "https://server-b.invalid/v1"
    assert b.usage.cache_hits == 0
    a2 = Echo("openai", "same-model", base_url="https://SERVER-A.invalid/v1/")
    a2.complete("s", "u")
    assert a2.usage.cache_hits == 1  # same endpoint after normalization replays


# --- N2: broken provider is fatal or visibly degraded -------------------------
def test_n2_auth_failure_aborts_instead_of_silent_fallback(Q, tmp_cache):
    class Unauthorized(LLMClient):
        def _call(self, *a):
            raise LLMFatalError("HTTP 401 unauthorized (synthetic)")

    bad = Unauthorized("openai", "x", use_cache=False)
    ep = load(TASKS_DIR, "test")[0]
    with pytest.raises(LLMFatalError):
        run_episode(ep, Q[ep.qid], LLMCoordinator(bad), llm=bad)


def test_n2_transient_failures_are_counted_as_fallbacks(Q, tmp_cache):
    class Flaky(LLMClient):
        def _call(self, *a):
            raise LLMError("timeout (synthetic)")

    flaky = Flaky("openai", "x", use_cache=False)
    ep = load(TASKS_DIR, "test")[0]
    run_episode(ep, Q[ep.qid], LLMCoordinator(flaky), llm=flaky)
    assert flaky.usage.errors > 0 and flaky.usage.calls == 0
    assert flaky.usage.degraded
    assert flaky.usage.fallbacks.get("tracker", 0) >= 1 and flaky.usage.fallbacks.get("coordinator", 0) >= 1


# --- N3: explicit "no change" is respected -------------------------------------
def test_n3_no_update_is_not_reinterpreted():
    class NoUpdate:
        def complete_json(self, *a, **k):
            return {"op": "none"}

    d, src = tracker.parse_any("Is Italian food available?", Constraints(1000, cuisines=["Chinese"]), NoUpdate())
    assert d is None and src == "llm-none"


def test_n3_env_keeps_constraints_on_no_update(Q):
    class NoUpdate:
        usage = cm.Usage()

        def complete_json(self, *a, **k):
            return {"op": "none"}

    q = next(iter(Q.values()))
    c = Constraints(5000, cuisines=["Chinese"])
    cache = Cache()
    env = TurnEnv(q, c, compose_global(q, c, cache), cache, "Is Italian food available?",
                  random.Random(0), llm=NoUpdate())
    assert env.diff is None and env.c.to_dict() == c.to_dict() and env.tracker_source == "llm-none"


# --- N4: off-template input never crashes; validator enforces the matrix -------
@pytest.mark.parametrize("msg", ["What room type do we have?", "Choose restaurants rated highly.",
                                 "hello", "", "We want rating", "room type please"])
def test_n4_rules_raise_only_valueerror(msg):
    try:
        tracker.parse(msg, Constraints(1000))
    except ValueError:
        pass


@pytest.mark.parametrize("bad", [
    ConstraintDiff("replace", "house_rule", "pets", "visitors"),
    ConstraintDiff("replace", "budget", None, float("nan")),
    ConstraintDiff("replace", "budget", None, float("inf")),
    ConstraintDiff("replace", "budget", None, "cheap"),
    ConstraintDiff("add", "min_rating", None, 9),
    ConstraintDiff("delete", "cuisine", "Italian", None),
    ConstraintDiff("delete", "transport", None, None),
    ConstraintDiff("add", "cuisine", None, "Chinese"),
    ConstraintDiff("reprioritize", "budget", None, 100),
    ConstraintDiff("teleport", "budget", None, 100),
])
def test_n4_validator_rejects(bad):
    c = Constraints(1000, house_rules=["pets"], cuisines=["Chinese"])
    with pytest.raises(ValueError):
        tracker.validate(bad, c)


def test_n4_env_survives_unparseable_message(Q):
    q = next(iter(Q.values()))
    c = Constraints(5000)
    cache = Cache()
    env = TurnEnv(q, c, compose_global(q, c, cache), cache, "What room type do we have?", random.Random(0))
    assert env.diff is None and env.tracker_source == "unparsed"


# --- N5: both policies see the same candidate evidence -------------------------
def test_n5_candidate_changes_reach_both_observations(Q):
    q = next(iter(Q.values()))
    c = Constraints(5000)
    cache = Cache()
    env = TurnEnv(q, c, compose_global(q, c, cache), cache, "Let's change the budget to $4,000.",
                  random.Random(0))
    s0, x0 = json.dumps(state_summary(env), sort_keys=True), encode(env).copy()
    env.cache.data["accommodation"] = []
    assert json.dumps(state_summary(env), sort_keys=True) != s0
    assert (encode(env) != x0).any()


# --- N6: meal agent gets the real budget and cannot overspend ------------------
def test_n6_meal_agent_respects_budget(Q):
    seen = {}

    class Expensive:
        usage = cm.Usage()

        def complete_json(self, s, u, max_tokens=300):
            inp = json.loads(u.split("INPUT:\n")[1])
            seen["budget_left"] = inp["budget_left"]
            names = sorted(inp["candidates"], key=lambda r: -r["cost_per_person"])[:6]
            return {"restaurants": [r["name"] for r in names]}

    q = next(iter(Q.values()))
    c = Constraints(5000)
    cache = Cache()
    p = compose_global(q, c, cache)
    c.budget = verify(q, c, p).total_cost + 1
    new = replan_local(q, c, p, "meals", cache, Expensive())
    assert seen["budget_left"] > 0
    assert verify(q, c, new).passed


# --- O1/O2: parser keeps numeric names; names identify one record --------------
def _pandas_like(rows, index=None):
    """Render rows like DataFrame.to_string(): right-aligned columns, optional left-aligned index."""
    from taskflow.data.travelplanner import REST_COLS

    cols = list(zip(*([REST_COLS] + rows)))
    widths = [max(len(str(v)) for v in col) for col in cols]
    iw = max(len(str(i)) for i in index) if index else 0

    def line(vals, idx=""):
        body = "  ".join(str(v).rjust(w) for v, w in zip(vals, widths))
        return (str(idx).ljust(iw) + " " + body) if index else body

    out = [line(REST_COLS, "")]
    out += [line(r, index[k] if index else "") for k, r in enumerate(rows)]
    return "\n".join(out)


ROWS = [["1918 Bistro & Grill", 40, "American, BBQ", 4.1, "Austin"],
        ["Cafe X", 10, "Tea", 3.0, "Austin"]]


def test_o1_numeric_names_survive_without_index():
    from taskflow.data.travelplanner import REST_COLS

    rows = _split_table(_pandas_like(ROWS), REST_COLS)
    assert [r[0] for r in rows] == ["1918 Bistro & Grill", "Cafe X"]


def test_o1_index_column_is_removed():
    from taskflow.data.travelplanner import REST_COLS

    rows = _split_table(_pandas_like(ROWS, index=[189, 1618]), REST_COLS)
    assert [r[0] for r in rows] == ["1918 Bistro & Grill", "Cafe X"]
    assert [r[1] for r in rows] == ["40", "10"]


def test_o1_o2_loaded_names(Q):
    names = [r.name for q in Q.values() for r in q.db.restaurants]
    assert "1918 Bistro & Grill" in names and "Bistro & Grill" not in names
    for q in Q.values():
        for attr in ("restaurants", "accommodations", "attractions"):
            ns = [x.name for x in getattr(q.db, attr)]
            assert len(ns) == len(set(ns)), (q.qid, attr)


# --- O3: incomplete plans are rejected -----------------------------------------
def test_o3_missing_meal_or_attraction_rejected(Q):
    q = next(iter(Q.values()))
    c = Constraints(5000)
    p = compose_global(q, c, Cache())
    assert verify(q, c, p).passed
    for slot in ("d2_lunch", "d1_attraction"):
        broken = dict(p, **{slot: "-"})
        rep = verify(q, c, broken)
        assert not rep.passed and "incomplete" in rep.kinds()


# --- O5: the system carries its own belief, not ground truth -------------------
def test_o5_wrong_parse_is_not_silently_corrected(Q, monkeypatch):
    ep = next(e for e in load(TASKS_DIR, "test") if len(e.turns) >= 2 and e.turns[0].feasible
              and e.turns[0].diff["target_type"] == "budget")
    real = tracker.parse_any
    seen = []

    def wrong_first(text, c, client=None):
        seen.append(c.budget)
        d, src = real(text, c, client)
        if len(seen) == 1:
            d.new = d.new + 1234.0
        return d, src

    monkeypatch.setattr(tracker, "parse_any", wrong_first)
    r = run_episode(ep, Q[ep.qid], StaticRules(), seed=0)
    truth_budget = ep.turns[0].constraints_after["budget"]
    assert not r.turns[0].tracker_ok
    # Turn 2 starts from the system's (wrong) belief, not from ground truth.
    assert seen[1] == truth_budget + 1234.0


# --- O8: retention counts every surviving item ---------------------------------
def test_o8_retention_keeps_same_type_items(Q):
    from taskflow.env import episode as epmod

    q = next(iter(Q.values()))
    before = Constraints(5000, cuisines=["Chinese", "Italian"])
    after = ConstraintDiff("replace", "cuisine", "Chinese", "Mexican").apply(before)
    kept = [it for it in before.items() if it in after.items()]
    assert ("cuisine", "Italian") in kept and ("cuisine", "Chinese") not in kept
    assert "truth_before.items() if it in truth_after.items()" in open(epmod.__file__).read()


# --- O9: static rules follow their script in order -----------------------------
def test_o9_injected_replan_before_search_does_not_skip_script(Q):
    q = next(iter(Q.values()))
    c = Constraints(5000)
    cache = Cache()
    env = TurnEnv(q, c, compose_global(q, c, cache), cache, "I'd like the accommodation to be a shared room.",
                  random.Random(0))
    env.step("REPLAN_LOCAL_ACCOMMODATION")  # forced mistake: re-plan before searching
    pol = StaticRules()
    assert pol.act(env) == "SEARCH_ACCOMMODATION"
    env.step("SEARCH_ACCOMMODATION")
    assert pol.act(env) == "REPLAN_LOCAL_ACCOMMODATION"


# --- O6: matched budget cap ----------------------------------------------------
def test_o6_call_cap_ends_turn(Q):
    ep = load(TASKS_DIR, "test")[0]
    from taskflow.coordinators.baselines import AlwaysGlobal

    r = run_episode(ep, Q[ep.qid], AlwaysGlobal(), seed=0, call_cap=1)
    assert all(t.llm_calls <= 1 for t in r.turns)
    assert any(t.terminal == "BUDGET_EXHAUSTED" for t in r.turns)
