"""Privileged scripted expert, restricted to deterministic transitions.

LLM agents can choose different valid repairs than the simulated planners.
Consequently this expert is neither executed nor used for disagreement
labels in LLM mode. Use LLMCoordinator as a fallible teacher there.

It sees the full verifier report and may simulate candidate repairs on a
copy of the environment, so it can label *any* state, including states the
learned policy reaches after its own mistakes. That is what makes DAgger
relabeling free.

Decision rule:
  stale report            -> VERIFY
  plan valid              -> KEEP_PLAN (nothing changed) / STOP
  update infeasible       -> refresh stale searches, then ASK_CLARIFICATION
  smallest local repair (up to three components) -> SEARCH_* if stale, else REPLAN_LOCAL_*
  no local repair works   -> REPLAN_GLOBAL
"""

from __future__ import annotations

from itertools import permutations

from taskflow.agents.planners import is_feasible, replan_local
from taskflow.env.state import CACHE_OF_GROUP, GROUPS, LOCAL_ACTION, SEARCH_ACTION, SLOTS
from taskflow.env.verifier import verify


def minimal_fix(env) -> list[str] | None:
    """Shortest sequence of component repairs (with fresh caches) that yields a valid plan."""
    cache = env.cache.copy()
    for name in ("transport", "accommodation", "dining"):
        if not cache.fresh(name, env.c):
            cache.search(name, env.q, env.c)
    for size in (1, 2, 3):
        best = None
        for seq in permutations(GROUPS, size):
            p = env.plan
            for g in seq:
                p = replan_local(env.q, env.c, p, g, cache)
            if verify(env.q, env.c, p).passed:
                changed = sum(p[s] != env.plan.get(s) for s in p)
                key = (changed, sum(len(SLOTS[g]) for g in seq), seq)
                if best is None or key < best[0]:
                    best = (key, list(seq))
        if best:
            return best[1]
    return None


class Oracle:
    name = "oracle"

    def __init__(self):
        self._feasible: dict = {}

    def feasible(self, env) -> bool:
        key = (env.q.qid, str(env.c.to_dict()))
        if key not in self._feasible:
            self._feasible[key] = is_feasible(env.q, env.c)
        return self._feasible[key]

    def act(self, env) -> str:
        if getattr(env, "llm", None) is not None:
            raise ValueError("Oracle supports deterministic transitions only; use LLMCoordinator for live agents")
        if env.report is None:
            return "VERIFY"
        if env.report.passed:
            return "STOP" if env.changed else "KEEP_PLAN"
        if not self.feasible(env):
            # Refresh searches first so the evidence for infeasibility (empty
            # candidate lists, cost lower bound above budget) is observable.
            for name in ("accommodation", "transport", "dining"):
                if not env.cache.fresh(name, env.c):
                    return SEARCH_ACTION[name]
            return "ASK_CLARIFICATION"
        fix = minimal_fix(env)
        if fix is None:
            return "REPLAN_GLOBAL"
        g = fix[0]
        cache = CACHE_OF_GROUP[g]
        if not env.cache.fresh(cache, env.c):
            return SEARCH_ACTION[cache]
        return LOCAL_ACTION[g]
