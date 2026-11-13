"""Core data structures: constraints, constraint diffs, plans, actions.

A plan is a flat mapping slot -> value so that preservation can be measured
slot by slot. Slots are grouped into four components that the coordinator
can repair independently.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field

ROOM_TYPES = ["entire room", "private room", "shared room", "not shared room"]
HOUSE_RULES = ["smoking", "parties", "children under 10", "visitors", "pets"]
CUISINES = ["American", "Chinese", "French", "Indian", "Italian", "Mediterranean", "Mexican"]
TRANSPORT_RULES = ["no flight", "no self-driving"]
PRIORITIES = ["cost", "quality"]

GROUPS = ["transport", "accommodation", "meals", "attractions"]
SLOTS = {
    "transport": ["transport_out", "transport_back"],
    "accommodation": ["accommodation"],
    "meals": ["d1_dinner", "d2_breakfast", "d2_lunch", "d2_dinner", "d3_breakfast", "d3_lunch"],
    "attractions": ["d1_attraction", "d2_attraction_1", "d2_attraction_2", "d3_attraction"],
}
ALL_SLOTS = [s for g in GROUPS for s in SLOTS[g]]
SLOT_GROUP = {s: g for g in GROUPS for s in SLOTS[g]}

# Which constraint fields filter the candidates of each cache.
CACHE_OF_GROUP = {"transport": "transport", "accommodation": "accommodation",
                  "meals": "dining", "attractions": "dining"}
CACHES = ["transport", "accommodation", "dining"]


@dataclass
class Constraints:
    budget: float
    people: int = 1
    room_type: str | None = None
    house_rules: list[str] = field(default_factory=list)
    cuisines: list[str] = field(default_factory=list)
    transport: str | None = None
    min_rating: float | None = None
    priority: str | None = None

    def copy(self) -> "Constraints":
        return copy.deepcopy(self)

    def items(self) -> list[tuple[str, object]]:
        """Active constraint items, used for retention accounting."""
        out: list[tuple[str, object]] = [("budget", self.budget)]
        if self.room_type:
            out.append(("room_type", self.room_type))
        out += [("house_rule", h) for h in self.house_rules]
        out += [("cuisine", c) for c in self.cuisines]
        if self.transport:
            out.append(("transport", self.transport))
        if self.min_rating is not None:
            out.append(("min_rating", self.min_rating))
        if self.priority:
            out.append(("priority", self.priority))
        return out

    def cache_key(self, cache: str) -> tuple:
        if cache == "transport":
            return (self.transport,)
        if cache == "accommodation":
            return (self.room_type, tuple(sorted(self.house_rules)), self.priority == "quality")
        return (tuple(sorted(self.cuisines)), self.min_rating)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Constraints":
        return Constraints(**d)


DIFF_OPS = ["add", "delete", "replace", "reprioritize"]
DIFF_TYPES = ["budget", "room_type", "house_rule", "cuisine", "transport", "min_rating", "priority"]


@dataclass
class ConstraintDiff:
    op: str
    target_type: str
    old: object = None
    new: object = None
    nl: str = ""
    template_set: str = "A"

    def apply(self, c: Constraints) -> Constraints:
        c = c.copy()
        t, new, old = self.target_type, self.new, self.old
        if t == "budget":
            c.budget = float(new)
        elif t == "room_type":
            c.room_type = new if self.op != "delete" else None
        elif t == "house_rule":
            if self.op == "delete":
                c.house_rules = [h for h in c.house_rules if h != old]
            else:
                c.house_rules = sorted(set(c.house_rules) | {new})
        elif t == "cuisine":
            cs = [x for x in c.cuisines if x != old] if self.op in ("delete", "replace") else list(c.cuisines)
            if self.op in ("add", "replace") and new not in cs:
                cs.append(new)
            c.cuisines = cs
        elif t == "transport":
            c.transport = new if self.op != "delete" else None
        elif t == "min_rating":
            c.min_rating = float(new) if self.op != "delete" else None
        elif t == "priority":
            c.priority = new if self.op != "delete" else None
        return c

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ConstraintDiff":
        return ConstraintDiff(**d)


ACTIONS = [
    "KEEP_PLAN", "ASK_CLARIFICATION",
    "SEARCH_TRANSPORTATION", "SEARCH_ACCOMMODATION", "SEARCH_ACTIVITY_DINING",
    "REPLAN_LOCAL_TRANSPORT", "REPLAN_LOCAL_ACCOMMODATION", "REPLAN_LOCAL_MEALS",
    "REPLAN_LOCAL_ATTRACTIONS", "REPLAN_GLOBAL", "VERIFY", "STOP",
]
A = {a: i for i, a in enumerate(ACTIONS)}
TERMINAL = {"KEEP_PLAN", "ASK_CLARIFICATION", "STOP"}
LOCAL_ACTION = {"transport": "REPLAN_LOCAL_TRANSPORT", "accommodation": "REPLAN_LOCAL_ACCOMMODATION",
                "meals": "REPLAN_LOCAL_MEALS", "attractions": "REPLAN_LOCAL_ATTRACTIONS"}
ACTION_GROUP = {v: k for k, v in LOCAL_ACTION.items()}
SEARCH_ACTION = {"transport": "SEARCH_TRANSPORTATION", "accommodation": "SEARCH_ACCOMMODATION",
                 "dining": "SEARCH_ACTIVITY_DINING"}
ACTION_CACHE = {v: k for k, v in SEARCH_ACTION.items()}

# Simulated per-action cost of the LLM-backed agents (see README, "Cost model").
ACTION_COST = {
    "KEEP_PLAN": (0, 0, 0), "ASK_CLARIFICATION": (1, 0, 300), "STOP": (0, 0, 0),
    "VERIFY": (0, 0, 0),
    "SEARCH_TRANSPORTATION": (0, 1, 400), "SEARCH_ACCOMMODATION": (0, 1, 400),
    "SEARCH_ACTIVITY_DINING": (0, 1, 400),
    "REPLAN_LOCAL_TRANSPORT": (1, 0, 1500), "REPLAN_LOCAL_ACCOMMODATION": (1, 0, 1500),
    "REPLAN_LOCAL_MEALS": (1, 0, 1500), "REPLAN_LOCAL_ATTRACTIONS": (1, 0, 1500),
    "REPLAN_GLOBAL": (4, 3, 6000),
}  # (llm_calls, tool_calls, tokens)

Plan = dict  # slot -> value
