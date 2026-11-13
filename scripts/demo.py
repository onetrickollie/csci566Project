"""Turn-by-turn demo of the learned coordinator.

    python scripts/demo.py                       # a scripted test episode
    python scripts/demo.py --episode test-0123-e1
    python scripts/demo.py --interactive         # type your own updates
    python scripts/demo.py --policy static_rules # compare against a baseline
    python scripts/demo.py --llm fake            # exercise every LLM code path offline
    python scripts/demo.py --llm openai --policy llm_coordinator   # needs a key, see .env.example

LLM mode: the tracker understands free-form messages, the component agents
choose from shortlists, and usage is measured. Without a key everything runs
offline with deterministic components.

Example updates for --interactive:
    Let's change the budget to $1,200.
    Could we also try some Mexican food?
    Please, no flight on this trip.
    The place needs to allow pets.
    Now quality matters more to me than anything else.
"""

import argparse
import random
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taskflow.agents.planners import compose_global  # noqa: E402
from taskflow.common import TASKS_DIR, baseline_policies, learned_policy, query_index  # noqa: E402
from taskflow.data.tasks import load  # noqa: E402
from taskflow.env.episode import TurnEnv, run_episode  # noqa: E402
from taskflow.env.state import ALL_SLOTS, ConstraintDiff, Constraints  # noqa: E402
from taskflow.env.tools import Cache  # noqa: E402
from taskflow.env.verifier import verify  # noqa: E402

B, D, R = "\033[1m", "\033[2m", "\033[0m"
SLOT_LABEL = {
    "transport_out": "Day 1  transport", "d1_dinner": "Day 1  dinner", "d1_attraction": "Day 1  attraction",
    "accommodation": "Nights 1-2 stay", "d2_breakfast": "Day 2  breakfast", "d2_lunch": "Day 2  lunch",
    "d2_dinner": "Day 2  dinner", "d2_attraction_1": "Day 2  attraction", "d2_attraction_2": "Day 2  attraction",
    "d3_breakfast": "Day 3  breakfast", "d3_lunch": "Day 3  lunch", "d3_attraction": "Day 3  attraction",
    "transport_back": "Day 3  transport",
}
ORDER = ["transport_out", "d1_attraction", "d1_dinner", "accommodation", "d2_breakfast",
         "d2_attraction_1", "d2_lunch", "d2_attraction_2", "d2_dinner", "d3_breakfast",
         "d3_attraction", "d3_lunch", "transport_back"]


LLM = None


def get_policy(name: str):
    base = baseline_policies(LLM)
    if name == "llm_coordinator" and LLM is None:
        sys.exit("llm_coordinator needs an LLM backend: pass --llm fake|openai|anthropic")
    return base[name] if name in base else learned_policy(name, 0)


def describe(c: Constraints) -> str:
    parts = [f"budget ${c.budget:,.0f}", f"{c.people} traveler(s)"]
    if c.room_type:
        parts.append(c.room_type)
    parts += [f"must allow {h}" for h in c.house_rules]
    if c.cuisines:
        parts.append("cuisines: " + ", ".join(c.cuisines))
    if c.transport:
        parts.append(c.transport)
    if c.min_rating is not None:
        parts.append(f"restaurants rated >= {c.min_rating}")
    if c.priority:
        parts.append(f"priority: {c.priority}")
    return "; ".join(parts)


def show_plan(q, c, plan, prev=None):
    rep = verify(q, c, plan)
    for s in ORDER:
        mark = f"{B}*{R}" if prev is not None and prev.get(s) != plan.get(s) else " "
        print(f"   {mark} {SLOT_LABEL[s]:<18} {plan.get(s, '-')}")
    cost = rep.component_cost
    print(f"     {D}total ${rep.total_cost:,.0f}  (transport ${cost['transport']:,.0f}, stay "
          f"${cost['accommodation']:,.0f}, meals ${cost['meals']:,.0f}){R}")
    status = f"{B}valid{R}" if rep.passed else "INVALID: " + "; ".join(v.kind for v in rep.violations)
    print(f"     verifier: {status}")


def run_turn(q, before, plan, cache, nl, policy, rng):
    u0 = LLM.usage.snapshot() if LLM else None
    env = TurnEnv(q, before, plan, cache, nl, rng, LLM)
    if env.diff is None and env.tracker_source == "llm-none":
        print("   tracker (llm): that message doesn't change any constraint; keeping the plan.")
        return before, plan, None
    if env.diff is None:
        print("   tracker: could not parse that update; try one of the example phrasings"
              + ("" if LLM else " (or run with an LLM backend for free-form messages)") + ".")
        return before, plan, None
    d = env.diff
    print(f"   {D}tracker ({env.tracker_source}) -> {d.op} {d.target_type}: {d.old} -> {d.new}{R}")
    r0 = env.report
    print(f"   {D}verifier on current plan: "
          f"{'valid' if r0.passed else ', '.join(sorted(r0.kinds()))}{R}")
    while not env.done:
        a = policy.act(env)
        env.step(a)
        extra = ""
        if a == "VERIFY":
            extra = " -> " + ("valid" if env.report.passed else ", ".join(sorted(env.report.kinds())))
        print(f"   coordinator: {a}{extra}")
    if env.terminal == "ASK_CLARIFICATION":
        print(f"   {B}assistant:{R} I can't satisfy that together with your other requirements "
              f"(nothing in the database fits). Want to adjust it? Keeping the previous plan.")
        return before, env.start_plan, env
    if env.terminal == "TIMEOUT":
        print("   (step limit reached)")
    changed = [s for s in ALL_SLOTS if env.plan.get(s) != env.start_plan.get(s)]
    measured = ""
    if LLM:
        calls, tok = LLM.usage.snapshot()
        measured = f" · measured: {calls - u0[0]} LLM requests, {tok - u0[1]:,} tokens"
    print(f"   {D}{len(changed)}/{len(ALL_SLOTS)} slots changed · {env.llm_calls} LLM calls (cost model) · "
          f"{env.tool_calls} tool calls{measured}{R}")
    show_plan(q, env.c, env.plan, env.start_plan)
    return env.c, env.plan, env


def header(q, c):
    print(f"\n{B}Trip:{R} {q.org} -> {q.dest}, {q.dates[0]} to {q.dates[-1]}")
    print(f"{B}Initial request:{R} {describe(c)}")


def scripted(args, Q):
    eps = load(TASKS_DIR, "test")
    if args.episode:
        ep = next(e for e in eps if e.episode_id == args.episode)
    else:
        rng = random.Random(args.seed)
        long = [e for e in eps if len(e.turns) >= 3 and all(t.feasible for t in e.turns[:2])]
        ep = rng.choice(long)
    q = Q[ep.qid]
    policy = get_policy(args.policy)
    c = Constraints.from_dict(ep.base)
    cache = Cache()
    plan = compose_global(q, c, cache)
    print(f"{B}Episode {ep.episode_id}{R} · coordinator: {args.policy} · LLM: {mode()}")
    header(q, c)
    show_plan(q, c, plan)
    rng = random.Random(0)
    for i, t in enumerate(ep.turns):
        nl = ConstraintDiff.from_dict(t.diff).nl
        print(f"\n{B}Turn {i + 1} · user:{R} {nl}")
        c, plan, _ = run_turn(q, c, plan, cache, nl, policy, rng)

    print(f"\n{B}Same episode, all coordinators{R}")
    names = ["always_global", "static_rules", args.policy if args.policy not in
             ("always_global", "static_rules", "oracle") else "bc_aug_dagger3", "oracle"]
    if LLM and "llm_coordinator" not in names:
        names.insert(2, "llm_coordinator")
    print(f"   {'coordinator':<16}{'turns ok':>9}{'LLM calls':>11}{'unaffected kept':>17}"
          + (f"{'measured reqs':>15}" if LLM else ""))
    for n in names:
        r = run_episode(ep, q, get_policy(n), seed=0, llm=LLM)
        ok = sum(t.success for t in r.turns)
        calls = sum(t.llm_calls for t in r.turns)
        pres = [t.preservation for t in r.turns if t.preservation is not None]
        kept = f"{100 * sum(pres) / len(pres):.0f}%" if pres else "-"
        meas = (f"{sum(t.measured_llm_calls for t in r.turns):>15}" if LLM else "")
        print(f"   {n:<16}{ok:>5}/{len(r.turns):<3}{calls:>11}{kept:>17}{meas}")


def interactive(args, Q):
    qs = [q for q in Q.values() if q.budget]
    q = random.Random(args.seed).choice(qs)
    from taskflow.data.tasks import base_constraints

    c = base_constraints(q, random.Random(args.seed))
    cache = Cache()
    plan = compose_global(q, c, cache)
    policy = get_policy(args.policy)
    print(f"coordinator: {args.policy} · LLM: {mode()}")
    header(q, c)
    show_plan(q, c, plan)
    print(textwrap.dedent(__doc__).split("Example updates for --interactive:")[1])
    rng = random.Random(0)
    while True:
        try:
            nl = input(f"\n{B}you:{R} ").strip()
        except EOFError:
            break
        if nl.lower() in ("", "q", "quit", "exit"):
            break
        c, plan, _ = run_turn(q, c, plan, cache, nl, policy, rng)
        print(f"   {D}now: {describe(c)}{R}")


def mode() -> str:
    return LLM.label if LLM else "offline (deterministic components)"


def main():
    global LLM
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode")
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--policy", default="bc_aug_dagger3")
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--llm", default=None,
                    help="offline | fake | openai | anthropic (default: TASKFLOW_LLM_PROVIDER or offline)")
    a = ap.parse_args()
    from taskflow.llm.client import get_client

    LLM = get_client(a.llm)
    Q = query_index()
    interactive(a, Q) if a.interactive else scripted(a, Q)


if __name__ == "__main__":
    main()
