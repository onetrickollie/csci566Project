"""The verifier must accept the human-annotated TravelPlanner reference plans."""

import re

import pytest

from taskflow.data.travelplanner import load_queries
from taskflow.env.state import SLOTS, Constraints
from taskflow.env.verifier import verify


def annotated_to_plan(ann: list[dict]) -> dict:
    def strip_city(v: str) -> str:
        return "-" if not v or v == "-" else v.rsplit(",", 1)[0].strip()

    def transport(v: str) -> str:
        m = re.search(r"Flight Number: (F\d+)", v)
        if m:
            return f"flight:{m.group(1)}"
        return "self-driving" if v.lower().startswith("self-driving") else "taxi"

    days = [d for d in ann if d]
    plan = {"transport_out": transport(days[0]["transportation"]),
            "transport_back": transport(days[2]["transportation"]),
            "accommodation": strip_city(days[0]["accommodation"])}
    meals = [days[0]["dinner"], days[1]["breakfast"], days[1]["lunch"], days[1]["dinner"],
             days[2]["breakfast"], days[2]["lunch"]]
    for s, v in zip(SLOTS["meals"], meals):
        plan[s] = strip_city(v)
    attrs = [strip_city(a) for d in days for a in d["attraction"].split(";") if a.strip() and a != "-"]
    for s in SLOTS["attractions"]:
        plan[s] = attrs.pop(0) if attrs else "-"
    return plan


def from_local(q) -> Constraints:
    lc = q.local_constraint
    return Constraints(budget=q.budget, people=q.people, room_type=lc.get("room type"),
                       house_rules=[lc["house rule"]] if lc.get("house rule") else [],
                       cuisines=list(lc.get("cuisine") or []), transport=lc.get("transportation"))


@pytest.fixture(scope="module")
def annotated():
    return [q for q in load_queries() if q.annotated_plan]


def test_reference_plans_pass(annotated):
    assert len(annotated) == 15
    failures = []
    for q in annotated:
        rep = verify(q, from_local(q), annotated_to_plan(q.annotated_plan))
        # Reference plans sometimes skip a meal they can't fit; that only lowers cost.
        if not rep.passed:
            failures.append((q.qid, [(v.kind, v.detail) for v in rep.violations]))
    assert not failures, failures


def test_budget_violation_detected(annotated):
    q = annotated[0]
    c = from_local(q)
    c.budget = 10
    rep = verify(q, c, annotated_to_plan(q.annotated_plan))
    assert "budget" in rep.kinds()
