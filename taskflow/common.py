"""Shared helpers for scripts: paths, dataset/model loading, policy registry."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "data" / "tasks" / "v0"
MODELS_DIR = ROOT / "models"
RESULTS_DIR = ROOT / "results"


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def manifest(**kw) -> dict:
    cfg = json.dumps(kw, sort_keys=True, default=str)
    return {"git_sha": git_sha(), "config": kw, "config_hash": hashlib.sha1(cfg.encode()).hexdigest()[:10]}


def query_index():
    from taskflow.data.travelplanner import ensure_downloaded, load_queries

    ensure_downloaded()
    return {q.qid: q for q in load_queries()}


def baseline_policies(llm=None) -> dict:
    from taskflow.coordinators.baselines import AlwaysGlobal, StaticRules
    from taskflow.coordinators.oracle import Oracle

    out = {"always_global": AlwaysGlobal(), "static_rules": StaticRules(), "oracle": Oracle()}
    if llm is not None:
        from taskflow.coordinators.llm_coordinator import LLMCoordinator

        out["llm_coordinator"] = LLMCoordinator(llm)
    return out


LEARNED = ["bc", "bc_aug", "bc_dagger1", "bc_dagger2", "bc_dagger3", "bc_aug_dagger3"]


def learned_policy(name: str, seed: int):
    from taskflow.learning.imitation import LearnedPolicy, load_model

    return LearnedPolicy(load_model(MODELS_DIR / f"{name}_s{seed}.pt"), name=name)
