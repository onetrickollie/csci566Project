"""Prompt builders for every LLM-backed component.

Each prompt is a (system, user) pair. The user message ends with
``INPUT:`` followed by one JSON object, and the system message starts with
``ROLE: <name>``. Keeping the input machine-readable makes replies easy to
validate and lets the fake backend answer every prompt offline.

Edit prompts here; nothing else needs to change.
"""

from __future__ import annotations

import json

from taskflow.env.state import (ACTIONS, CUISINES, DIFF_OPS, DIFF_TYPES, HOUSE_RULES, PRIORITIES,
                                ROOM_TYPES, TRANSPORT_RULES)


def _user(instructions: str, payload: dict) -> str:
    return f"{instructions.strip()}\n\nINPUT:\n{json.dumps(payload, ensure_ascii=False)}"


def tracker_prompt(utterance: str, constraints: dict) -> tuple[str, str]:
    system = f"""ROLE: tracker
You convert one travel-planning user message into a structured constraint update.
Reply with ONE JSON object and nothing else:
{{"op": one of {DIFF_OPS} or "none", "target_type": one of {DIFF_TYPES},
  "old": previous value or null, "new": new value or null}}
Allowed values:
- budget: a number in USD (total for the trip)
- room_type: {ROOM_TYPES}
- house_rule: {HOUSE_RULES}  (the place must ALLOW this)
- cuisine: {CUISINES}
- transport: {TRANSPORT_RULES}
- min_rating: a number between 0 and 5 (restaurant rating floor)
- priority: {PRIORITIES}
Rules: "delete" sets new to null and old to the value being removed. "replace" is for budget,
room_type and cuisine swaps. "reprioritize" is only for priority. Use op "none" if the message
does not change any constraint."""
    return system, _user("Current constraints and the user's message:",
                         {"current_constraints": constraints, "message": utterance})


def planner_prompt(component: str, constraints: dict, budget_left: float, candidates: list[dict],
                   pick: str) -> tuple[str, str]:
    system = f"""ROLE: planner_{component}
You are the {component} agent of a travel planner. Choose from the candidates only.
Hard requirements: respect every constraint and keep the cost within budget_left when possible.
Candidates are listed in a suggested order (cheapest valid options first); you may choose
differently if it better serves the user's priority.
Reply with ONE JSON object and nothing else: {pick}"""
    return system, _user("Choose for this trip:", {"constraints": constraints,
                                                   "budget_left": round(budget_left, 2),
                                                   "candidates": candidates})


ACTION_HELP = {
    "KEEP_PLAN": "end the turn without changes (only if nothing was changed this turn and the plan is valid)",
    "ASK_CLARIFICATION": "tell the user the update cannot be satisfied with the other constraints",
    "SEARCH_TRANSPORTATION": "refresh transport options under current constraints",
    "SEARCH_ACCOMMODATION": "refresh accommodation options under current constraints",
    "SEARCH_ACTIVITY_DINING": "refresh restaurants and attractions under current constraints",
    "REPLAN_LOCAL_TRANSPORT": "re-plan only transport, keep everything else",
    "REPLAN_LOCAL_ACCOMMODATION": "re-plan only the accommodation, keep everything else",
    "REPLAN_LOCAL_MEALS": "re-plan only the meals, keep everything else",
    "REPLAN_LOCAL_ATTRACTIONS": "re-plan only attractions, keep everything else",
    "REPLAN_GLOBAL": "rebuild the whole itinerary (expensive, changes many parts)",
    "VERIFY": "re-run the constraint checker on the current plan",
    "STOP": "end the turn after changes, once the checker says the plan is valid",
}


def coordinator_prompt(state: dict) -> tuple[str, str]:
    actions = "\n".join(f"- {a}: {ACTION_HELP[a]}" for a in ACTIONS)
    system = f"""ROLE: coordinator
You coordinate travel-planning agents while the user revises their constraints.
Goal: end each turn with a valid plan while changing as little of the plan as possible and
using as few re-planning calls as possible. Replanning with stale search results may reuse
options that violate new constraints, so search first when the relevant cache is stale.
After any re-plan the checker result is stale until you VERIFY.
Actions:
{actions}
Reply with ONE JSON object and nothing else: {{"action": "<one action name>", "reason": "<short>"}}"""
    return system, _user("Current state:", state)


def split(system: str, user: str) -> tuple[str, dict]:
    """Inverse used by the fake backend: (role, input payload)."""
    role = system.split("\n", 1)[0].replace("ROLE:", "").strip()
    payload = json.loads(user.split("INPUT:\n", 1)[1])
    return role, payload
