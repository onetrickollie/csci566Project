"""Visual demo: one episode, every coordinator side by side, as a self-contained HTML page.

    python scripts/demo_html.py                          # a test episode -> demo.html, opens it
    python scripts/demo_html.py --episode test-0123-e1
    python scripts/demo_html.py --split test_multi       # a multi-component budget cut
    python scripts/demo_html.py --no-open --out /tmp/demo.html

Each turn shows the user's message, each coordinator's actions, the itinerary
after the turn with changed slots highlighted, cost, and whether the plan is
valid. Works offline; with --llm it uses the configured backend.
"""

import argparse
import html
import random
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taskflow.agents.planners import compose_global  # noqa: E402
from taskflow.common import ROOT, TASKS_DIR, baseline_policies, learned_policy, query_index  # noqa: E402
from taskflow.data.tasks import load  # noqa: E402
from taskflow.env.episode import TurnEnv  # noqa: E402
from taskflow.env.state import ConstraintDiff, Constraints  # noqa: E402
from taskflow.env.tools import Cache  # noqa: E402
from taskflow.env.verifier import verify  # noqa: E402

ORDER = [("transport_out", "Day 1 · transport"), ("d1_attraction", "Day 1 · attraction"),
         ("d1_dinner", "Day 1 · dinner"), ("accommodation", "Nights 1–2 · stay"),
         ("d2_breakfast", "Day 2 · breakfast"), ("d2_attraction_1", "Day 2 · attraction"),
         ("d2_lunch", "Day 2 · lunch"), ("d2_attraction_2", "Day 2 · attraction"),
         ("d2_dinner", "Day 2 · dinner"), ("d3_breakfast", "Day 3 · breakfast"),
         ("d3_attraction", "Day 3 · attraction"), ("d3_lunch", "Day 3 · lunch"),
         ("transport_back", "Day 3 · transport")]
SYSTEMS = [("always_global", "Always regenerate"), ("static_rules", "Static rules"),
           ("bc_aug_dagger3", "Learned (BC + aug + DAgger)"), ("oracle", "Scripted expert")]

CSS = """
:root{--bg:#fafaf9;--fg:#1c1917;--muted:#78716c;--card:#fff;--line:#e7e5e4;--hl:#fef3c7;--hlfg:#92400e;
--ok:#15803d;--bad:#b91c1c;--chip:#f5f5f4;--accent:#1d4ed8}
@media (prefers-color-scheme:dark){:root{--bg:#1c1917;--fg:#f5f5f4;--muted:#a8a29e;--card:#292524;--line:#44403c;
--hl:#422006;--hlfg:#fcd34d;--ok:#4ade80;--bad:#f87171;--chip:#3f3a36;--accent:#93c5fd}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,sans-serif}
main{max-width:1400px;margin:0 auto;padding:24px 16px 64px}h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--muted);margin-bottom:20px}.turn{margin:28px 0 8px;padding-top:16px;border-top:1px solid var(--line)}
.turn h2{font-size:16px;margin:0 0 4px}.msg{font-size:15px;margin:4px 0 2px}.parsed{color:var(--muted);font-size:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin-top:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;min-width:0}
.card h3{font-size:14px;margin:0 0 6px;display:flex;justify-content:space-between;gap:8px}
.badge{font-size:11px;padding:1px 8px;border-radius:99px;font-weight:600;white-space:nowrap}
.ok{color:var(--ok);border:1px solid var(--ok)}.bad{color:var(--bad);border:1px solid var(--bad)}
.acts{display:flex;flex-wrap:wrap;gap:4px;margin:6px 0 8px}.act{background:var(--chip);border-radius:6px;padding:1px 6px;font:11px ui-monospace,monospace}
.stats{color:var(--muted);font-size:12px;margin-bottom:6px}table{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed}
td{padding:2px 4px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}td.k{color:var(--muted);width:42%}
tr.ch td{background:var(--hl);color:var(--hlfg)}.legend{font-size:12px;color:var(--muted)}.legend span{background:var(--hl);color:var(--hlfg);padding:0 4px;border-radius:3px}
.initial{max-width:520px}
"""


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
        parts.append(f"restaurants ≥ {c.min_rating}")
    if c.priority:
        parts.append(f"priority: {c.priority}")
    return "; ".join(parts)


def plan_table(plan, prev=None) -> str:
    rows = []
    for slot, label in ORDER:
        v = html.escape(str(plan.get(slot, "-")).replace("\n", " / "))
        cls = ' class="ch"' if prev is not None and prev.get(slot) != plan.get(slot) else ""
        rows.append(f"<tr{cls}><td class=k>{label}</td><td>{v}</td></tr>")
    return "<table>" + "".join(rows) + "</table>"


def run_system(ep, q, policy, llm):
    """Yield per-turn snapshots for one coordinator."""
    c = Constraints.from_dict(ep.base)
    cache = Cache()
    plan = compose_global(q, c, cache)
    if ep.initial_plan:
        plan = dict(ep.initial_plan)
    rng = random.Random(0)
    out = []
    for t in ep.turns:
        nl = ConstraintDiff.from_dict(t.diff).nl
        env = TurnEnv(q, c, plan, cache, nl, rng, llm, sample_global=getattr(policy, "sample_global", True))
        while not env.done:
            env.step(policy.act(env))
        if env.terminal == "ASK_CLARIFICATION" and not t.feasible:
            new_plan, new_c = env.start_plan, env.before
        else:
            new_plan, new_c = env.plan, env.c
        truth = Constraints.from_dict(t.constraints_after)
        rep = verify(q, truth, new_plan)
        ok = (not t.feasible) if env.terminal == "ASK_CLARIFICATION" else (t.feasible and rep.passed)
        out.append({"env": env, "plan": new_plan, "prev": env.start_plan, "ok": ok, "cost": rep.total_cost,
                    "violations": sorted(rep.kinds()), "asked": env.terminal == "ASK_CLARIFICATION",
                    "feasible": t.feasible})
        plan, c = new_plan, new_c
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode")
    ap.add_argument("--split", default="test")
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--llm", default=None)
    ap.add_argument("--out", type=Path, default=ROOT / "demo.html")
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()
    from taskflow.llm.client import get_client

    llm = get_client(a.llm)
    Q = query_index()
    eps = load(TASKS_DIR, a.split)
    if a.episode:
        ep = next(e for e in eps if e.episode_id == a.episode)
    else:
        # Multi family: a two-component cut, where local repair and a full rebuild differ most.
        pool = ([e for e in eps if e.episode_id.endswith("-L2")] if a.split.endswith("_multi") else
                [e for e in eps if len(e.turns) >= 3 and all(t.feasible for t in e.turns[:2])]) or eps
        ep = random.Random(a.seed).choice(pool)
    q = Q[ep.qid]
    base = baseline_policies(llm)
    systems = [(k, lbl) for k, lbl in SYSTEMS if not (llm is not None and k == "oracle")]
    if llm is not None:
        systems.insert(2, ("llm_coordinator", "LLM coordinator"))
    runs = {k: run_system(ep, q, base[k] if k in base else learned_policy(k, 0), llm) for k, _ in systems}

    c0 = Constraints.from_dict(ep.base)
    p0 = dict(ep.initial_plan) if ep.initial_plan else compose_global(q, c0, Cache())
    r0 = verify(q, c0, p0)
    parts = [f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
             f"<title>TaskFlow-Travel demo</title><style>{CSS}</style></head><body><main>",
             f"<h1>{html.escape(q.org)} → {html.escape(q.dest)}, {q.dates[0]} to {q.dates[-1]}</h1>",
             f"<div class=sub>Episode {html.escape(ep.episode_id)} · LLM: {html.escape(llm.label) if llm else 'offline'} · "
             f"initial request: {html.escape(describe(c0))}</div>",
             f"<div class='card initial'><h3>Starting itinerary <span class='badge ok'>valid · ${r0.total_cost:,.0f}</span></h3>"
             f"{plan_table(p0)}</div>",
             "<p class=legend>In each turn, <span>highlighted</span> rows changed during that turn.</p>"]
    totals = {k: {"ok": 0, "calls": 0, "kept": []} for k, _ in systems}
    for i, t in enumerate(ep.turns):
        d = ConstraintDiff.from_dict(t.diff)
        parts.append(f"<section class=turn><h2>Turn {i + 1}</h2><div class=msg>“{html.escape(d.nl)}”</div>"
                     f"<div class=parsed>{d.op} {d.target_type}: {html.escape(str(d.old))} → {html.escape(str(d.new))}"
                     f"{' · cannot be satisfied (correct response: ask)' if not t.feasible else ''}</div><div class=grid>")
        for k, label in systems:
            s = runs[k][i]
            env = s["env"]
            changed = sum(s["plan"].get(x) != s["prev"].get(x) for x, _ in ORDER)
            totals[k]["ok"] += s["ok"]
            totals[k]["calls"] += env.llm_calls
            badge = ("<span class='badge ok'>asked · correct</span>" if s["asked"] and s["ok"] else
                     "<span class='badge bad'>asked · unnecessary</span>" if s["asked"] else
                     f"<span class='badge ok'>valid · ${s['cost']:,.0f}</span>" if s["ok"] else
                     f"<span class='badge bad'>{html.escape(', '.join(s['violations']) or 'failed')}</span>")
            acts = "".join(f"<span class=act>{html.escape(x)}</span>" for x in env.history)
            parts.append(f"<div class=card><h3>{html.escape(label)} {badge}</h3><div class=acts>{acts}</div>"
                         f"<div class=stats>{changed}/13 slots changed · {env.llm_calls} LLM calls · "
                         f"{env.tool_calls} searches</div>{plan_table(s['plan'], s['prev'])}</div>")
        parts.append("</div></section>")
    parts.append("<section class=turn><h2>Summary</h2><div class=grid>")
    for k, label in systems:
        parts.append(f"<div class=card><h3>{html.escape(label)}</h3><div class=stats>"
                     f"{totals[k]['ok']}/{len(ep.turns)} turns handled correctly · {totals[k]['calls']} LLM calls "
                     f"(cost model)</div></div>")
    parts.append("</div></section></main></body></html>")
    a.out.write_text("".join(parts))
    print(f"wrote {a.out}")
    if not a.no_open:
        webbrowser.open(a.out.resolve().as_uri())


if __name__ == "__main__":
    main()
