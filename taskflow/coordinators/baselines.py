"""Non-learned coordinators.

StaticRules: a hand-written map from the kind of update to a repair script,
followed by verification. If the repair fails it refreshes stale searches and
asks for clarification when the cached candidates show the update cannot be
met (the same observable evidence the learned policy gets); otherwise it
tries one global rebuild, then asks.
AlwaysGlobal: regenerate the whole itinerary on every update.
AlwaysGlobalDeterministic: the same, without the sampled regeneration
instability (control for the preservation metric).
"""

from __future__ import annotations

from taskflow.env.state import SEARCH_ACTION


def infeasibility_evident(env) -> bool:
    """Observable evidence (from fresh caches) that the update cannot be met."""
    from taskflow.learning.encode import candidate_evidence

    ev = candidate_evidence(env)
    fresh = {c: env.cache.fresh(c, env.c) for c in SEARCH_ACTION}
    return ((fresh["accommodation"] and ev["accommodation_candidates"] == 0)
            or (fresh["transport"] and not ev["transport_available"])
            or (fresh["dining"] and (ev["uncovered_cuisines"] or ev["restaurant_candidates"] < 6))
            or (all(fresh.values()) and ev["cost_lower_bound"] > ev["effective_budget"]))


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
        # Follow the script in order: a scripted step counts as done only if it
        # happened after the previous scripted step (so an extra action taken
        # too early, e.g. a re-plan before the search, does not count).
        pos = 0
        for a in _script(env.diff):
            try:
                pos = h.index(a, pos) + 1
            except ValueError:
                return a
        if env.report is None:
            return "VERIFY"
        if env.report.passed:
            return "STOP" if env.changed else "KEEP_PLAN"
        for name, action in SEARCH_ACTION.items():
            if not env.cache.fresh(name, env.c):
                return action
        if infeasibility_evident(env):
            return "ASK_CLARIFICATION"
        if "REPLAN_GLOBAL" not in h:
            return "REPLAN_GLOBAL"
        return "ASK_CLARIFICATION"


class AlwaysGlobal:
    name = "always_global"
    sample_global = True

    def act(self, env) -> str:
        if "REPLAN_GLOBAL" not in env.history:
            return "REPLAN_GLOBAL"
        if env.report is None:
            return "VERIFY"
        return "STOP" if env.report.passed else "ASK_CLARIFICATION"


class AlwaysGlobalDeterministic(AlwaysGlobal):
    name = "always_global_det"
    sample_global = False


class StaticRulesCostAware(StaticRules):
    """A stronger hand-written baseline for budget pressure.

    When the plan is over budget (or over the cost-priority limit), it asks at
    once if the cached candidates show that even the cheapest choices cannot
    fit; otherwise it re-plans components in order of how much each could
    save (current cost minus its cheapest cached option), verifying after
    each, before trying one global rebuild. Other violations follow
    StaticRules. Uses only observable evidence (``candidate_evidence``).
    """

    name = "static_cost_aware"
    COMPONENT_ACTION = {"transport": "REPLAN_LOCAL_TRANSPORT", "accommodation": "REPLAN_LOCAL_ACCOMMODATION",
                        "meals": "REPLAN_LOCAL_MEALS"}
    COMPONENT_CACHE = {"transport": "transport", "accommodation": "accommodation", "meals": "dining"}

    def act(self, env) -> str:
        from taskflow.learning.encode import candidate_evidence

        h = env.history
        rep = env.report
        if rep is None:
            return "VERIFY"
        if rep.passed:
            return "STOP" if env.changed else "KEEP_PLAN"
        if not ({"budget", "priority_cost"} & rep.kinds()) or len(rep.kinds() - {"budget", "priority_cost"}):
            return super().act(env)
        if infeasibility_evident(env):
            return "ASK_CLARIFICATION"
        ev = candidate_evidence(env)
        cheapest = {"transport": ev["cheapest_transport"], "accommodation": ev["cheapest_accommodation"],
                    "meals": ev["cheapest_meals"]}
        slack = {k: ev["plan_cost"][k] - (cheapest[k] or 0) for k in cheapest}
        for comp in sorted(slack, key=lambda k: -slack[k]):
            if slack[comp] <= 0 or self.COMPONENT_ACTION[comp] in h:
                continue
            cache = self.COMPONENT_CACHE[comp]
            if not env.cache.fresh(cache, env.c):
                return SEARCH_ACTION[cache]
            return self.COMPONENT_ACTION[comp]
        for name, action in SEARCH_ACTION.items():
            if not env.cache.fresh(name, env.c):
                return action
        if "REPLAN_GLOBAL" not in h:
            return "REPLAN_GLOBAL"
        return "ASK_CLARIFICATION"
