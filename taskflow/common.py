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


def git_dirty() -> bool | None:
    try:
        # Result files are outputs of the run itself, so they don't count.
        out = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no", "--",
                                       ".", ":!results"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL)
        return bool(out.strip())
    except Exception:
        return None


def fingerprint(paths) -> str:
    """Content hash of files (or every .py under directories), order-independent."""
    h = hashlib.sha256()
    files = []
    for p in paths:
        p = Path(p)
        files += sorted(p.rglob("*.py")) if p.is_dir() else ([p] if p.exists() else [])
    for f in sorted(set(files)):
        h.update(str(f.relative_to(ROOT)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:12]


def manifest(**kw) -> dict:
    """Run identity: config, code/prompt/data fingerprints, and git state.

    ``git_sha`` alone is not enough (uncommitted edits); ``source`` and
    ``prompts`` fingerprints identify the code that actually ran.
    """
    cfg = json.dumps(kw, sort_keys=True, default=str)
    return {
        "git_sha": git_sha(), "git_dirty": git_dirty(), "config": kw,
        "config_hash": hashlib.sha1(cfg.encode()).hexdigest()[:10],
        "fingerprints": {
            "source": fingerprint([ROOT / "taskflow", ROOT / "scripts"]),
            "prompts": fingerprint([ROOT / "taskflow" / "llm" / "prompts.py"]),
            "tasks": fingerprint(sorted(TASKS_DIR.glob("*.jsonl"))),
        },
    }


def query_index():
    from taskflow.data.travelplanner import ensure_downloaded, load_queries

    ensure_downloaded()
    return {q.qid: q for q in load_queries()}


def baseline_policies(llm=None) -> dict:
    from taskflow.coordinators.baselines import (AlwaysGlobal, AlwaysGlobalDeterministic, StaticRules,
                                                 StaticRulesCostAware)
    from taskflow.coordinators.oracle import Oracle

    out = {"always_global": AlwaysGlobal(), "always_global_det": AlwaysGlobalDeterministic(),
           "static_rules": StaticRules(), "static_cost_aware": StaticRulesCostAware()}
    if llm is None:
        out["oracle"] = Oracle()
    if llm is not None:
        from taskflow.coordinators.llm_coordinator import LLMCoordinator

        out["llm_coordinator"] = LLMCoordinator(llm)
    return out


LEARNED = ["bc", "bc_aug", "bc_dagger1", "bc_dagger2", "bc_dagger3", "bc_aug_dagger3"]


def learned_policy(name: str, seed: int):
    from taskflow.learning.imitation import LearnedPolicy, load_model

    return LearnedPolicy(load_model(MODELS_DIR / f"{name}_s{seed}.pt"), name=name)
