"""Aggregate episode results into the metrics named in the proposal."""

from __future__ import annotations

from collections import defaultdict

import numpy as np


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return float(np.mean(xs)) if xs else None


def summarize(results) -> dict:
    turns = [t for r in results for t in r.turns]
    feas = [t for t in turns if t.feasible]
    infeas = [t for t in turns if not t.feasible]
    asked = [t for t in turns if t.terminal == "ASK_CLARIFICATION"]
    return {
        "episodes": len(results),
        "turns": len(turns),
        "final_pass_rate": _mean([r.final_pass for r in results]),
        "revision_success_rate": _mean([t.success for t in turns]),
        "new_constraint_satisfaction": _mean([t.new_satisfied for t in feas]),
        "constraint_retention_rate": _mean([t.retention for t in feas]),
        "unaffected_preserved": _mean([t.preservation for t in feas]),
        "edit_rate": _mean([t.edit_rate for t in feas]),
        "minimum_edits_per_turn": _mean([t.minimum_edits for t in feas]),
        "excess_edits_per_turn": _mean([t.excess_edits for t in feas]),
        "edit_optimal_preservation": _mean([t.edit_optimal_preservation for t in feas]),
        "edit_scored_turns": sum(t.minimum_edits is not None for t in feas),
        "global_replan_rate": _mean([t.used_global for t in turns]),
        "unnecessary_global_rate": _mean([t.unnecessary_global for t in turns]),
        "clarification_recall": _mean([t.terminal == "ASK_CLARIFICATION" for t in infeas]),
        "clarification_precision": _mean([not t.feasible for t in asked]),
        "timeout_rate": _mean([t.terminal == "TIMEOUT" for t in turns]),
        "budget_exhausted_rate": _mean([t.terminal == "BUDGET_EXHAUSTED" for t in turns]),
        "llm_calls_per_turn": _mean([t.llm_calls for t in turns]),
        "tool_calls_per_turn": _mean([t.tool_calls for t in turns]),
        "est_tokens_per_turn": _mean([t.tokens for t in turns]),
        "steps_per_turn": _mean([len(t.actions) for t in turns]),
        "tracker_accuracy": _mean([t.tracker_ok for t in turns]),
        # Only present when an LLM backend was active (None offline).
        "measured_llm_requests_per_turn": _mean([t.measured_llm_calls for t in turns]),
        "measured_tokens_per_turn": _mean([t.measured_tokens for t in turns]),
    }


def breakdown(results, key: str) -> dict:
    groups = defaultdict(list)
    for r in results:
        for t in r.turns:
            k = {"op": t.op, "target_type": t.target_type,
                 "turn_index": "held-out (4th turn)" if t.turn >= 3 else f"turn {t.turn + 1}"}[key]
            groups[k].append(t)
    out = {}
    for k, ts in sorted(groups.items()):
        out[k] = {"turns": len(ts), "revision_success_rate": _mean([t.success for t in ts]),
                  "unaffected_preserved": _mean([t.preservation for t in ts if t.feasible]),
                  "edit_scored_turns": sum(t.minimum_edits is not None for t in ts),
                  "minimum_edits": _mean([t.minimum_edits for t in ts]),
                  "excess_edits": _mean([t.excess_edits for t in ts]),
                  "edit_optimal_preservation": _mean([t.edit_optimal_preservation for t in ts]),
                  "llm_calls_per_turn": _mean([t.llm_calls for t in ts])}
    return out


def by_chain_length(results) -> dict:
    groups = defaultdict(list)
    for r in results:
        groups[len(r.turns)].append(r)
    return {f"L={k}" + (" (held-out)" if k == 4 else ""): {
        "episodes": len(v), "final_pass_rate": _mean([r.final_pass for r in v])}
        for k, v in sorted(groups.items())}
