"""Render results/metrics.json into REPORT.md and figures."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ORDER = ["always_global", "always_global_det", "static_rules", "llm_coordinator", "bc", "bc_aug", "bc_dagger1", "bc_dagger2", "bc_dagger3",
         "bc_aug_dagger3", "oracle"]
LABEL = {"always_global": "Always-Global", "always_global_det": "Always-Global (deterministic control)",
         "static_rules": "Static rules",
         "llm_coordinator": "LLM coordinator", "bc": "BC",
         "bc_aug": "BC + augmentation", "bc_dagger1": "BC + DAgger (1)", "bc_dagger2": "BC + DAgger (2)",
         "bc_dagger3": "BC + DAgger (3)", "bc_aug_dagger3": "BC + aug + DAgger (3)",
         "oracle": "Deterministic scripted expert"}
MAIN = [("final_pass_rate", "Final pass"), ("revision_success_rate", "Revision success"),
        ("new_constraint_satisfaction", "New constr. sat."), ("constraint_retention_rate", "Retention"),
        ("unaffected_preserved", "Legacy unaffected preserved"), ("edit_rate", "Slots edited"),
        ("unnecessary_global_rate", "Unneeded global"),
        ("llm_calls_per_turn", "LLM calls/turn"), ("tool_calls_per_turn", "Tool calls/turn"),
        ("est_tokens_per_turn", "Est. tokens/turn")]


def _fmt(cell, key):
    if cell is None:
        return "–"
    m, s = cell["mean"], cell["std"]
    if key.endswith("per_turn"):
        txt = f"{m:,.0f}" if "tokens" in key else f"{m:.2f}"
        return txt + (f" ± {s:.2f}" if s and "tokens" not in key else "")
    return f"{100 * m:.1f}" + (f" ± {100 * s:.1f}" if s else "")


MEASURED = [("measured_llm_requests_per_turn", "Measured LLM requests/turn"),
            ("measured_tokens_per_turn", "Measured tokens/turn")]


def write_report(out: dict, d: Path) -> None:
    S = out["systems"]
    names = [n for n in ORDER if n in S]
    has_measured = any(S[n]["summary"].get("measured_tokens_per_turn") for n in names)
    MAIN_COLS = MAIN + (MEASURED if has_measured else [])
    m = out["manifest"]
    cfg = m["config"]
    llm_mode = cfg.get("llm", "offline") != "offline"
    lines = [f"# Results ({cfg.get('split', 'test')} split)", ""]
    if out.get("degraded"):
        u = out.get("llm_usage_total", {})
        lines += [f"> **DEGRADED RUN:** the LLM client had {u.get('errors', 0)} failed requests and "
                  f"{sum(u.get('fallbacks', {}).values())} component fallbacks. Numbers partly reflect the "
                  "deterministic fallbacks, not the model. See the LLM usage table.", ""]
    lines += [f"Config: `{cfg}`", "",
              f"git `{m['git_sha']}`{' (uncommitted changes)' if m.get('git_dirty') else ''} · "
              f"fingerprints `{m.get('fingerprints', {})}`", "",
              "Rates are percentages. Learned systems: mean ± std over training seeds. "
              "LLM calls/tool calls/est. tokens come from the simulated cost model (see README)"
              + ("; measured columns come from the live client." if llm_mode else "."), ""]
    if cfg.get("call_cap") is not None:
        lines += [f"Matched budget: at most {cfg['call_cap']} cost-model LLM calls per turn; a turn that "
                  "would exceed it ends as BUDGET_EXHAUSTED with the plan as it is.", ""]
    lines += [
             "| System | " + " | ".join(h for _, h in MAIN_COLS) + " |",
             "|---|" + "---|" * len(MAIN_COLS)]
    for n in names:
        sm = S[n]["summary"]
        lines.append(f"| {LABEL[n]} | " + " | ".join(_fmt(sm.get(k), k) for k, _ in MAIN_COLS) + " |")

    if any(S[n]['summary'].get('minimum_edits_per_turn') for n in names):
        lines += ['', '## Minimum necessary changes', '',
                  'Exact minimum slot edits over complete feasible plans. Scored only on successful feasible turns; '
                  'read alongside revision success and the scored-turn count. Budget turns include all costed slots. '
                  'Optimal preservation = 1 − excess edits / (13 − minimum edits); undefined when all 13 must change. '
                  'The legacy unaffected-slot metric above is retained for comparison.', '',
                  '| System | Scored turns (mean) | Minimum edits | Excess edits | Optimal preservation % |',
                  '|---|---|---|---|---|']
        for n in names:
            sm = S[n]['summary']
            count = sm.get('edit_scored_turns', {}).get('mean', 0)
            lines.append(f"| {LABEL[n]} | {count:g} | " +
                         ' | '.join(_fmt(sm.get(k), k) for k in
                                    ('minimum_edits_per_turn', 'excess_edits_per_turn', 'edit_optimal_preservation')) + ' |')
    if llm_mode:
        lines += ['', 'The scripted expert and expert-disagreement labels are disabled for LLM transitions. '
                  'An LLM teacher is a fallible demonstrator, not an optimality oracle.', '']

    lines += ["", "## Clarification behaviour", "",
              "| System | Recall on infeasible updates | Precision | Timeouts | Budget exhausted |",
              "|---|---|---|---|---|"]
    for n in names:
        sm = S[n]["summary"]
        lines.append(f"| {LABEL[n]} | {_fmt(sm.get('clarification_recall'), 'r')} | "
                     f"{_fmt(sm.get('clarification_precision'), 'p')} | {_fmt(sm.get('timeout_rate'), 't')} | "
                     f"{_fmt(sm.get('budget_exhausted_rate'), 'b')} |")

    if llm_mode:
        lines += ["", "## LLM usage per system (first seed for learned systems)", "",
                  "| System | Requests | Billed calls | Cache hits | Errors | Fallbacks | Fallback rate | Degraded |",
                  "|---|---|---|---|---|---|---|---|"]
        for n in names:
            u = S[n].get("llm_usage") or {}
            if not u:
                continue
            fb = ", ".join(f"{k} {v}" for k, v in u.get("fallbacks", {}).items()) or "0"
            lines.append(f"| {LABEL[n]} | {u['requests']} | {u['calls']} | {u['cache_hits']} | {u['errors']} | "
                         f"{fb} | {100 * u['fallback_rate']:.1f}% | {'yes' if u['degraded'] else 'no'} |")

    if S[names[0]].get("recovery"):
        lines += ["", f"## Recovery from a forced mistake ({out['recovery_episodes']} episodes whose "
                  "first update needs a repair)", "",
                  "The listed action is forced as the first step of the turn; the coordinator then continues. "
                  "Cell = turn success % over all selected episodes / over the episodes where the forced "
                  "action left the plan broken (n), then LLM calls. Mistakes that already fix the plan "
                  "(e.g. a global rebuild) say nothing about recovery.", "",
                  "| System | " + " | ".join(out["systems"][names[0]]["recovery"].keys()) + " |",
                  "|---|" + "---|" * len(S[names[0]]["recovery"])]
        for n in names:
            cells = []
            for mk, v in S[n]["recovery"].items():
                def val(x):
                    return x["mean"] if isinstance(x, dict) else x
                ts, c = val(v["turn_success"]), val(v["llm_calls"])
                nr = val(v.get("needs_recovery_n", 0))
                hs = v.get("needs_recovery_success")
                hs = val(hs) if hs is not None else None
                hard = f"{100 * hs:.1f} (n={nr:.0f})" if hs is not None else f"– (n={nr:.0f})"
                cells.append(f"{100 * ts:.1f} / {hard}, {c:.2f}")
            lines.append(f"| {LABEL[n]} | " + " | ".join(cells) + " |")

    for key, title in (("by_op", "By update type"), ("by_turn", "By turn position (4th turn only exists in test)")):
        cats = sorted({c for n in names for c in S[n][key]})
        lines += ["", f"## {title}", "", "Revision success % / unaffected preserved %. Learned systems: training seed 0.", "",
                  "| System | " + " | ".join(cats) + " |", "|---|" + "---|" * len(cats)]
        for n in names:
            row = []
            for c in cats:
                v = S[n][key].get(c)
                if not v:
                    row.append("–")
                    continue
                p = v["unaffected_preserved"]
                row.append(f"{100 * v['revision_success_rate']:.1f} / " + (f"{100 * p:.0f}" if p is not None else "–"))
            lines.append(f"| {LABEL[n]} | " + " | ".join(row) + " |")

    lines += ["", "## Figures", "", "![pareto](pareto.png)", "", "![error](error_vs_step.png)", "",
              "![recovery](recovery.png)", ""]
    (d / "REPORT.md").write_text("\n".join(lines))
    _figures(out, d, names)


def _figures(out, d, names):
    S = out["systems"]
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    for n in names:
        sm = S[n]["summary"]
        x, y = sm["llm_calls_per_turn"]["mean"], 100 * sm["revision_success_rate"]["mean"]
        pres = 100 * sm["unaffected_preserved"]["mean"]
        ax.scatter(x, y, s=30 + 2.5 * pres, alpha=0.75)
        ax.annotate(f"{LABEL[n]}\n(preserved {pres:.0f}%)", (x, y), fontsize=7,
                    xytext=(5, -4), textcoords="offset points")
    ax.set_xlabel("LLM calls per turn (lower is cheaper)")
    ax.set_ylabel("Revision success (%)")
    ax.set_title("Partial vs. global replanning")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(d / "pareto.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
    for n in names:
        e = S[n].get("error_vs_step")
        if not e:
            continue
        for ax, key, xl in ((axes[0], "by_step", "step within turn"), (axes[1], "by_turn", "turn index")):
            ks = sorted(e[key], key=int)
            ax.plot([int(k) for k in ks], [100 * e[key][k] for k in ks], marker="o", label=LABEL[n])
            ax.set_xlabel(xl)
            ax.set_ylabel("disagreement with expert (%)")
            ax.grid(alpha=0.3)
    axes[0].set_title("Error vs. step")
    axes[1].set_title("Error vs. turn")
    axes[1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(d / "error_vs_step.png", dpi=150)
    plt.close(fig)

    mks = list(S[names[0]].get("recovery") or {})
    if not mks:
        return
    fig, ax = plt.subplots(figsize=(9, 3.8))
    w = 0.8 / len(names)
    for i, n in enumerate(names):
        vals = []
        for mk in mks:
            ts = S[n]["recovery"][mk]["turn_success"]
            vals.append(100 * (ts["mean"] if isinstance(ts, dict) else ts))
        ax.bar([j + i * w for j in range(len(mks))], vals, width=w, label=LABEL[n])
    ax.set_xticks([j + 0.4 - w / 2 for j in range(len(mks))])
    ax.set_xticklabels([m.replace("REPLAN_", "").replace("_", " ").lower() for m in mks], fontsize=8)
    ax.set_ylabel("turn success after forced mistake (%)")
    ax.set_ylim(0, 105)
    ax.legend(fontsize=6, ncol=3)
    fig.tight_layout()
    fig.savefig(d / "recovery.png", dpi=150)
    plt.close(fig)
