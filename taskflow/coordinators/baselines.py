"""Non-learned coordinators.

StaticRules: a hand-written map from the kind of update to a repair script,
followed by verification, one global fallback, then clarification.
AlwaysGlobal: regenerate the whole itinerary on every update.
"""

from __future__ import annotations


def _script(diff) -> list[str]:
    if diff is None:
        return ["REPLAN_GLOBAL"]
    t, op = diff.target_type, diff.op
    if op == "delete":
        return []
    if t == "budget":
        return ["REPLAN_LOCAL_ACCOMMODATION"]
    if t in ("room_type", "house_rule"):
        return ["SEARCH_ACCOMMODATION", "REPLAN_LOCAL_ACCOMMODATION"]
    if t in ("cuisine", "min_rating"):
        return ["SEARCH_ACTIVITY_DINING", "REPLAN_LOCAL_MEALS"]
    if t == "transport":
        return ["SEARCH_TRANSPORTATION", "REPLAN_LOCAL_TRANSPORT"]
    if t == "priority":
        return ["SEARCH_ACCOMMODATION", "REPLAN_LOCAL_ACCOMMODATION"]
    return ["REPLAN_GLOBAL"]


class StaticRules:
    name = "static_rules"

    def act(self, env) -> str:
        h = env.history
        if not h and env.report is not None and env.report.passed:
            return "KEEP_PLAN"
        # Next scripted action that has not been executed yet (robust to
        # extra actions in the history).
        remaining = list(h)
        for a in _script(env.diff):
            if a in remaining:
                remaining.remove(a)
            else:
                return a
        if env.report is None:
            return "VERIFY"
        if env.report.passed:
            return "STOP" if env.changed else "KEEP_PLAN"
        if "REPLAN_GLOBAL" not in h:
            return "REPLAN_GLOBAL"
        return "ASK_CLARIFICATION"


class AlwaysGlobal:
    name = "always_global"

    def act(self, env) -> str:
        if "REPLAN_GLOBAL" not in env.history:
            return "REPLAN_GLOBAL"
        if env.report is None:
            return "VERIFY"
        return "STOP" if env.report.passed else "ASK_CLARIFICATION"
