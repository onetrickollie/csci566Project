"""Multi-turn episode runner.

Each user turn: the Constraint Tracker parses the update, the verifier runs
once on the current plan, then the coordinator takes actions until it ends
the turn (KEEP_PLAN / STOP / ASK_CLARIFICATION) or hits MAX_STEPS.
Ground truth from the episode file is used only for scoring.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field

from taskflow.agents import tracker
from taskflow.agents.planners import compose_global, replan_local
from taskflow.data.tasks import Episode
from taskflow.data.travelplanner import Query
from taskflow.env.state import (ACTION_CACHE, ACTION_COST, ACTION_GROUP, ALL_SLOTS, TERMINAL,
                                ConstraintDiff, Constraints, Plan)
from taskflow.env.tools import Cache
from taskflow.env.verifier import Report, constraint_item_satisfied, verify

MAX_STEPS = 10


class TurnEnv:
    def __init__(self, q: Query, before: Constraints, plan: Plan, cache: Cache, nl: str,
                 rng: random.Random, llm=None):
        self.q, self.before, self.start_plan = q, before, dict(plan)
        self.plan, self.cache, self.rng, self.llm = dict(plan), cache, rng, llm
        self.tracker_source = None
        try:
            self.diff, self.tracker_source = tracker.parse_any(nl, before, llm)
            self.diff: ConstraintDiff | None
            self.c = self.diff.apply(before)
        except ValueError:
            self.diff, self.c = None, before.copy()
        self.report: Report | None = verify(q, self.c, self.plan)
        self.history: list[str] = []
        self.changed: set[str] = set()
        self.global_done = False
        self.failed_verifies = 0
        self.llm_calls = self.tool_calls = self.tokens = 0
        self.done = False
        self.terminal: str | None = None

    def clone(self) -> "TurnEnv":
        n = object.__new__(TurnEnv)
        n.__dict__.update(self.__dict__)
        n.plan, n.cache = dict(self.plan), self.cache.copy()
        n.history, n.changed = list(self.history), set(self.changed)
        n.rng = random.Random(self.rng.random())
        return n

    def step(self, action: str) -> None:
        assert not self.done
        llm, tools, tok = ACTION_COST[action]
        self.llm_calls += llm
        self.tool_calls += tools
        self.tokens += tok
        self.history.append(action)
        if action in ACTION_CACHE:
            self.cache.search(ACTION_CACHE[action], self.q, self.c)
        elif action in ACTION_GROUP:
            g = ACTION_GROUP[action]
            self.plan = replan_local(self.q, self.c, self.plan, g, self.cache, self.llm)
            self.changed.add(g)
            self.report = None
        elif action == "REPLAN_GLOBAL":
            self.plan = compose_global(self.q, self.c, self.cache, self.rng, self.llm)
            self.changed.update(["transport", "accommodation", "meals", "attractions"])
            self.global_done = True
            self.report = None
        elif action == "VERIFY":
            self.report = verify(self.q, self.c, self.plan)
            if not self.report.passed:
                self.failed_verifies += 1
        if action in TERMINAL:
            self.done, self.terminal = True, action
        elif len(self.history) >= MAX_STEPS:
            self.done, self.terminal = True, "TIMEOUT"


@dataclass
class TurnResult:
    turn: int
    op: str
    target_type: str
    feasible: bool
    terminal: str
    actions: list[str]
    success: bool
    new_satisfied: bool | None
    retention: float | None
    preservation: float | None
    used_global: bool
    unnecessary_global: bool
    llm_calls: int
    tool_calls: int
    tokens: int
    tracker_ok: bool
    measured_llm_calls: int | None = None  # real calls when an LLM backend is active
    measured_tokens: int | None = None


@dataclass
class EpisodeResult:
    episode_id: str
    turns: list[TurnResult] = field(default_factory=list)
    final_pass: bool = False
    trajectory: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _local_fix_exists(env: TurnEnv) -> bool:
    from taskflow.coordinators.oracle import minimal_fix

    return env.report is not None and not env.report.passed and minimal_fix(env) is not None


def run_episode(ep: Episode, q: Query, policy, seed: int = 0, expert=None, beta: float = 0.0,
                record: bool = False, inject: dict | None = None, encoder=None,
                llm=None) -> EpisodeResult:
    """Roll out ``policy`` on an episode.

    expert/beta: DAgger mixing. With probability beta the expert's action is
    executed; when ``record`` is set the expert's label is stored for every
    visited state. ``inject`` = {"turn": t, "step": s, "action": a} forces a
    specific action once (used for augmentation and the recovery eval).
    """
    rng = random.Random(seed)
    base = Constraints.from_dict(ep.base)
    cache = Cache()
    plan = compose_global(q, base, cache)
    res = EpisodeResult(episode_id=ep.episode_id)
    before = base
    for ti, turn in enumerate(ep.turns):
        truth_diff = ConstraintDiff.from_dict(turn.diff)
        truth_after = Constraints.from_dict(turn.constraints_after)
        truth_applied = truth_diff.apply(before)
        u0 = llm.usage.snapshot() if llm is not None else None
        env = TurnEnv(q, before, plan, cache, truth_diff.nl, rng, llm)
        tracker_ok = env.diff is not None and env.c.to_dict() == truth_applied.to_dict()
        start_report = verify(q, truth_applied, plan)
        needed_slots = start_report.slots()
        local_possible = _local_fix_exists(env) if turn.feasible else False
        while not env.done:
            state = encoder(env) if (record and encoder) else None
            label = expert.act(env) if (expert is not None and (record or beta > 0)) else None
            if inject and inject["turn"] == ti and inject["step"] == len(env.history):
                a = inject["action"]
            elif label is not None and beta > 0 and rng.random() < beta:
                a = label
            else:
                a = policy.act(env)
            if record and label is not None:
                res.trajectory.append({"turn": ti, "step": len(env.history), "state": state,
                                       "action": a, "expert_action": label})
            env.step(a)

        if env.terminal == "ASK_CLARIFICATION":
            success = not turn.feasible
            if not turn.feasible:
                plan = env.start_plan
            else:
                plan = env.plan
        else:
            plan = env.plan
            success = turn.feasible and verify(q, truth_after, plan).passed
        end_report = verify(q, truth_after, plan)
        new_ok = None
        if turn.feasible and truth_diff.op != "delete":
            item = _diff_item(truth_diff, truth_after)
            new_ok = constraint_item_satisfied(item, end_report) if item else None
        kept = [it for it in before.items() if it in truth_after.items()
                and it[0] != truth_diff.target_type]
        retention = (sum(constraint_item_satisfied(it, end_report) for it in kept) / len(kept)
                     if kept else None)
        unaffected = [s for s in ALL_SLOTS if s not in needed_slots]
        preservation = None
        if turn.feasible and unaffected:
            preservation = sum(plan.get(s) == env.start_plan.get(s) for s in unaffected) / len(unaffected)
        res.turns.append(TurnResult(
            turn=ti, op=truth_diff.op, target_type=truth_diff.target_type, feasible=turn.feasible,
            terminal=env.terminal, actions=list(env.history), success=success,
            new_satisfied=new_ok, retention=retention, preservation=preservation,
            used_global=env.global_done, unnecessary_global=env.global_done and local_possible,
            llm_calls=env.llm_calls, tool_calls=env.tool_calls, tokens=env.tokens,
            tracker_ok=tracker_ok,
            measured_llm_calls=(llm.usage.requests - u0[0]) if llm is not None else None,
            measured_tokens=(llm.usage.tokens - u0[1]) if llm is not None else None))
        before = truth_after
    res.final_pass = verify(q, before, plan).passed and res.turns[-1].success
    return res


def _diff_item(d: ConstraintDiff, after: Constraints):
    t = d.target_type
    if t == "budget":
        return ("budget", after.budget)
    if t == "room_type":
        return ("room_type", after.room_type)
    if t == "house_rule":
        return ("house_rule", d.new)
    if t == "cuisine":
        return ("cuisine", d.new)
    if t == "transport":
        return ("transport", after.transport)
    if t == "min_rating":
        return ("min_rating", after.min_rating)
    if t == "priority":
        return ("priority", after.priority)
    return None
