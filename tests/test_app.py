"""Interactive app: merged city database and the JSON API (no server needed)."""

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


def test_world_coverage_and_resolution(app):
    w = app.WORLD
    assert len(w.destinations) > 200 and len(w.start_cities) > 240
    assert w.resolve("new york", w.destinations)[0] == "New York"
    name, suggestions = w.resolve("Seatle", w.destinations)
    assert name is None and "Seattle" in suggestions


def test_estimated_ground_is_labelled(app):
    q = app.WORLD.trip_query("Chicago", "Seattle", "2022-03-10", 2, 3000)
    assert q.db.ground and all(g.estimated for g in q.db.ground.values())
    assert not any(f.number.startswith("est") for fl in q.db.flights.values() for f in fl)


def test_trip_and_revisions(app):
    assert "suggest_dest" in app.api_trip({"org": "Chicago", "dest": "Seatle", "people": 2, "budget": 3000})
    low = app.api_trip({"org": "Chicago", "dest": "Seattle", "date": "2022-03-10", "people": 2, "budget": 300})
    assert "cheapest plan" in low["error"]
    r = app.api_trip({"org": "Chicago", "dest": "Seattle", "date": "2022-03-10", "people": 2, "budget": 3000})
    assert r["plan"]["valid"]
    for msg in ["Let's change the budget to $200.", "The place needs to allow pets.",
                "Now quality matters more to me than anything else."]:
        u = app.api_update({"session": r["session"], "message": msg})
        assert len(u["results"]) == 4
        for s in u["results"]:
            assert s["terminal"] != "TIMEOUT", (msg, s["label"], s["actions"])
            assert s["asked"] or s["plan"]["valid"], (msg, s["label"])
    assert "error" in app.api_update({"session": r["session"], "message": "hello there"})
