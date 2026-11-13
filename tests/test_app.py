"""Interactive app: merged city database, route realism, and the JSON API (no server)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


@pytest.fixture(scope="module")
def app():
    import app as app_mod
    from taskflow.data.world import build_world

    app_mod.WORLD = build_world()
    app_mod.LLM = None
    return app_mod


def trip(app, **kw):
    body = {"org": "Chicago", "dest": "Detroit", "date": "2022-03-10", "people": 2, "budget": 3000}
    body.update(kw)
    return app.api_trip(body)


def test_world_coverage_and_resolution(app):
    w = app.WORLD
    assert len(w.destinations) > 200 and len(w.start_cities) > 240
    assert w.resolve("new york", w.destinations)[0] == "New York"
    name, suggestions = w.resolve("Seatle", w.destinations)
    assert name is None and "Seattle" in suggestions


# R1: impossible or overlong ground routes are refused
@pytest.mark.parametrize("org,dest", [("Los Angeles", "Honolulu"), ("New York", "Seattle"), ("Chicago", "Seattle")])
def test_r1_unrealistic_routes_refused(app, org, dest):
    r = trip(app, org=org, dest=dest, budget=10000)
    assert "error" in r and "No realistic way" in r["error"]
    assert r.get("suggest_routes")


def test_r1_ocean_crossing_never_estimated(app):
    q = app.WORLD.trip_query("Los Angeles", "Honolulu", "2022-03-10", 2, 10000)
    assert not q.db.ground


def test_r1_estimated_short_route_is_labelled(app):
    q = app.WORLD.trip_query("Chicago", "Detroit", "2022-03-10", 2, 3000)
    assert q.db.ground and all(g.estimated for g in q.db.ground.values())


# R2: an ask is not automatically counted as handled
def test_r2_unnecessary_ask_is_not_counted_as_handled(app):
    class AlwaysAsk:
        name = "always_ask"

        def act(self, env):
            return "ASK_CLARIFICATION"

    r = trip(app)
    sess = app.SESSIONS[r["session"]]
    for st in sess["state"].values():
        st["policy"] = AlwaysAsk()
    u = app.api_update({"session": r["session"], "message": "Let's change the budget to $4,000."})
    for s in u["results"]:
        assert s["asked"] and s["achievable"] and not s["handled"]
        assert s["totals"]["ok"] == 0


def test_r2_necessary_ask_counts_and_keeps_plan(app):
    r = trip(app)
    u = app.api_update({"session": r["session"], "message": "Let's change the budget to $50."})
    for s in u["results"]:
        assert s["terminal"] != "TIMEOUT", (s["label"], s["actions"])
        if s["asked"]:
            assert s["achievable"] is False and s["handled"] and s["changed"] == 0


# R4: input validation at the API boundary
@pytest.mark.parametrize("budget", ["NaN", "Infinity", "-Infinity", "-5", "0", "abc"])
def test_r4_bad_budgets_rejected(app, budget):
    assert "error" in trip(app, budget=budget)


@pytest.mark.parametrize("kw", [{"date": "2022-13-40"}, {"date": "2022-04-15"}, {"people": 0},
                                {"room_type": "castle"}, {"house_rules": ["dragons"]}, {"cuisines": ["Martian"]},
                                {"transport": "teleport"}])
def test_r4_bad_fields_rejected(app, kw):
    assert "error" in trip(app, **kw)


# R5: each transport leg shows its own direction's record
def test_r5_return_leg_uses_its_own_record(app):
    q = app.WORLD.trip_query("Abilene", "Amarillo", "2022-03-10", 1, 3000)
    out = app.transport_label(q, "self-driving", "transport_out")
    back = app.transport_label(q, "self-driving", "transport_back")
    assert "Abilene → Amarillo" in out and "$22" in out
    assert "Amarillo → Abilene" in back and "$23" in back


def test_revisions_end_cleanly(app):
    r = trip(app)
    assert r["plan"]["valid"]
    for msg in ["Let's change the budget to $200.", "The place needs to allow pets.",
                "Now quality matters more to me than anything else."]:
        u = app.api_update({"session": r["session"], "message": msg})
        assert len(u["results"]) == 4
        for s in u["results"]:
            assert s["terminal"] != "TIMEOUT", (msg, s["label"], s["actions"])
            assert s["asked"] or s["plan"]["valid"], (msg, s["label"])
    assert "error" in app.api_update({"session": r["session"], "message": "hello there"})
