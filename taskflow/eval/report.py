"""Render results/metrics.json into REPORT.md and figures."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ORDER = ["always_global", "static_rules", "bc", "bc_aug", "bc_dagger1", "bc_dagger2", "bc_dagger3",
         "bc_aug_dagger3", "oracle"]
LABEL = {"always_global": "Always-Global", "static_rules": "Static rules", "bc": "BC",
         "bc_aug": "BC + augmentation", "bc_dagger1": "BC + DAgger (1)", "bc_dagger2": "BC + DAgger (2)",
         "bc_dagger3": "BC + DAgger (3)", "bc_aug_dagger3": "BC + aug + DAgger (3)",
         "oracle": "Privileged oracle (upper bound)"}
MAIN = [("final_pass_rate", "Final pass"), ("revision_success_rate", "Revision success"),
        ("new_constraint_satisfaction", "New constr. sat."), ("constraint_retention_rate", "Retention"),
        ("unaffected_preserved", "Unaffected preserved"), ("unnecessary_global_rate", "Unneeded global"),
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


def write_report(out: dict, d: Path) -> None:
    S = out["systems"]
    names = [n for n in ORDER if n in S]
    lines = ["# Results (test split)", "",
             f"Config: `{out['manifest']['config']}` · git `{out['manifest']['git_sha']}`", "",
             "Rates are percentages. Learned systems: mean ± std over training seeds. "
             "Token counts come from the simulated cost model (see README).", "",
             "| System | " + " | ".join(h for _, h in MAIN) + " |",
             "|---|" + "---|" * len(MAIN)]
    for n in names:
        sm = S[n]["summary"]
        lines.append(f"| {LABEL[n]} | " + " | ".join(_fmt(sm.get(k), k) for k, _ in MAIN) + " |")

    lines += ["", "## Clarification behaviour", "",
              "| System | Recall on infeasible updates | Precision | Timeouts |", "|---|---|---|---|"]
    for n in names:
        sm = S[n]["summary"]
        lines.append(f"| {LABEL[n]} | {_fmt(sm.get('clarification_recall'), 'r')} | "
                     f"{_fmt(sm.get('clarification_precision'), 'p')} | {_fmt(sm.get('timeout_rate'), 't')} |")

    lines += ["", f"## Recovery from a forced mistake ({out['recovery_episodes']} episodes whose "
              "first update needs a repair)", "",
              "The listed action is forced as the first step of the turn; the coordinator then continues. "
              "Cell = turn success % (LLM calls).", "",
              "| System | " + " | ".join(out["systems"][names[0]]["recovery"].keys()) + " |",
              "|---|" + "---|" * len(S[names[0]]["recovery"])]
    for n in names:
        cells = []
        for mk, v in S[n]["recovery"].items():
            ts = v["turn_success"]
            m = ts["mean"] if isinstance(ts, dict) else ts
            c = v["llm_calls"]["mean"] if isinstance(v["llm_calls"], dict) else v["llm_calls"]
            cells.append(f"{100 * m:.1f} ({c:.2f})")
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

    mks = list(S[names[0]]["recovery"])
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
