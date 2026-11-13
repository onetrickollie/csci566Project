"""LLM coordinator.

Two uses:
1. A coordinator baseline: the LLM picks every action from a structured
   summary of the state. The candidate evidence comes from the same function
   the learned policy's encoder uses (``candidate_evidence``).
2. The LLM teacher for DAgger (task T15): pass it as ``expert`` to
   ``taskflow.learning.imitation.collect`` / ``dagger``; it can label any
   state, including states the student reaches after its own mistakes.

Invalid replies fall back to the static-rule action for that state and are
counted per reason on the client. Fatal client errors propagate.
"""

from __future__ import annotations

from taskflow.agents.planners import effective_budget
from taskflow.coordinators.baselines import StaticRules
from taskflow.env.state import ACTIONS, CACHES, SLOT_GROUP
from taskflow.env.verifier import plan_cost
from taskflow.learning.encode import action_mask, candidate_evidence
from taskflow.llm.client import LLMFatalError, note_fallback
from taskflow.llm.prompts import coordinator_prompt


def state_summary(env) -> dict:
    rep = env.report
    cost = plan_cost(env.q, env.c, env.plan)
    d = env.diff
    return {
        "update": None if d is None else {"op": d.op, "type": d.target_type, "old": d.old, "new": d.new,
                                          "message": d.nl},
        "constraints": env.c.to_dict(),
        "verifier": {
            "fresh": rep is not None,
            "passed": bool(rep is not None and rep.passed),
            "violations": [] if rep is None else [
                {"kind": v.kind, "detail": v.detail, "components": sorted({SLOT_GROUP[s] for s in v.slots})}
                for v in rep.violations],
            "violated_components": [] if rep is None else sorted({SLOT_GROUP[s] for s in rep.slots()}),
        },
        "cache_fresh": {c: env.cache.fresh(c, env.c) for c in CACHES},
        "changed_components": sorted(env.changed),
        "actions_this_turn": list(env.history),
        "cost": {"total": round(sum(cost.values()), 2), "effective_budget": round(effective_budget(env.c), 2),
                 **{k: round(v, 2) for k, v in cost.items()}},
        "steps_left": 10 - len(env.history),
        "candidate_evidence": _rounded(candidate_evidence(env)),
    }


def _rounded(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, float):
            out[k] = round(v, 2)
        elif isinstance(v, dict):
            out[k] = {kk: round(vv, 2) for kk, vv in v.items()}
        else:
            out[k] = v
    return out


class LLMCoordinator:
    name = "llm_coordinator"

    def __init__(self, client):
        self.client = client
        self.fallback = StaticRules()
        self.fallbacks = 0

    def act(self, env) -> str:
        system, user = coordinator_prompt(state_summary(env))
        try:
            a = self.client.complete_json(system, user, max_tokens=150).get("action")
            mask = action_mask(env)
            if a in ACTIONS and mask[ACTIONS.index(a)]:
                return a
            reason = f"invalid action {a!r}"
        except LLMFatalError:
            raise
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
        self.fallbacks += 1
        note_fallback(self.client, "coordinator", reason)
        return self.fallback.act(env)
