"""Offline stand-in for an LLM, used by tests and ``--llm fake``.

It answers each prompt role with simple deterministic logic, so the whole
LLM code path (prompting, JSON parsing, validation, caching, usage
accounting) can be exercised without a key. It is not meant to be smart.
"""

from __future__ import annotations

import json

from taskflow.llm.prompts import split


def respond(system: str, user: str) -> str:
    role, inp = split(system, user)
    if role == "tracker":
        from taskflow.agents.tracker import parse
        from taskflow.env.state import Constraints

        try:
            d = parse(inp["message"], Constraints.from_dict(inp["current_constraints"]))
        except ValueError:
            return json.dumps({"op": "none", "target_type": "budget", "old": None, "new": None})
        return json.dumps({"op": d.op, "target_type": d.target_type, "old": d.old, "new": d.new})
    if role.startswith("planner_"):
        comp = role[len("planner_"):]
        cands = inp["candidates"]
        if comp == "accommodation":
            return json.dumps({"name": cands[0]["name"] if cands else None})
        if comp == "transport":
            return json.dumps({"out": cands[0]["out"], "back": cands[0]["back"]} if cands else {})
        if comp == "meals":
            return json.dumps({"restaurants": [c["name"] for c in cands[:6]]})
        if comp == "attractions":
            return json.dumps({"attractions": [c["name"] for c in cands[:4]]})
    if role == "coordinator":
        return json.dumps({"action": _coordinate(inp), "reason": "fake backend rule"})
    return json.dumps({})


def _coordinate(s: dict) -> str:
    v, hist = s["verifier"], s["actions_this_turn"]
    if not v["fresh"]:
        return "VERIFY"
    if v["passed"]:
        return "STOP" if s["changed_components"] else "KEEP_PLAN"
    if "REPLAN_GLOBAL" in hist:
        return "ASK_CLARIFICATION"
    if hist.count("VERIFY") >= 2:
        return "REPLAN_GLOBAL"
    comps = [c for c in v["violated_components"] if c != "attractions"] or v["violated_components"]
    comp = "accommodation" if "accommodation" in comps else comps[0]
    cache = {"transport": "transport", "accommodation": "accommodation"}.get(comp, "dining")
    if not s["cache_fresh"][cache]:
        return {"transport": "SEARCH_TRANSPORTATION", "accommodation": "SEARCH_ACCOMMODATION",
                "dining": "SEARCH_ACTIVITY_DINING"}[cache]
    return f"REPLAN_LOCAL_{comp.upper()}"
