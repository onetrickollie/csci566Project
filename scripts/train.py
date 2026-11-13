"""Train the learned coordinators: BC, BC+augmentation, BC+DAgger (1-3 iters),
BC+augmentation+DAgger.

    python scripts/train.py --seeds 0 1 2
    python scripts/train.py --teacher llm --llm openai --seeds 0 --limit 100

--teacher oracle (default): the privileged scripted expert labels states.
--teacher llm: the LLM coordinator labels states instead (task T15). Every
visited state costs one LLM request (cached on disk), so start with --limit.
Models trained with the LLM teacher are saved with an "_llmteacher" suffix.
Note: during collection the environment's own planners are deterministic
(no LLM agents); only the labels come from the LLM teacher. Evaluating such a
model with --llm therefore changes the environment it acts in.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taskflow.common import MODELS_DIR, TASKS_DIR, manifest, query_index  # noqa: E402
from taskflow.coordinators.oracle import Oracle  # noqa: E402
from taskflow.data.tasks import load  # noqa: E402
from taskflow.learning.imitation import Data, collect, dagger, save_model, train  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--inject-rate", type=float, default=0.7)
    ap.add_argument("--teacher", choices=["oracle", "llm"], default="oracle")
    ap.add_argument("--llm", default=None, help="backend for --teacher llm: fake | openai | anthropic")
    ap.add_argument("--limit", type=int, default=None, help="use only the first N training episodes")
    ap.add_argument("--no-multi", action="store_true",
                    help="train on v0 only (skip the multi-component family train_multi.jsonl)")
    a = ap.parse_args()
    MODELS_DIR.mkdir(exist_ok=True)
    Q = query_index()
    tr = load(TASKS_DIR, "train")
    if not a.no_multi and (TASKS_DIR / "train_multi.jsonl").exists():
        tr += load(TASKS_DIR, "train_multi")
    tr = tr[: a.limit]
    expert = Oracle()
    suffix = ""
    if a.teacher == "llm":
        from taskflow.coordinators.llm_coordinator import LLMCoordinator
        from taskflow.llm.client import get_client

        client = get_client(a.llm)
        if client is None:
            sys.exit("--teacher llm needs an LLM backend (--llm or TASKFLOW_LLM_PROVIDER)")
        expert, suffix = LLMCoordinator(client), "_llmteacher"
    teacher_id = expert.client.identity() if a.teacher == "llm" else "oracle"
    log = {"manifest": manifest(seeds=a.seeds, epochs=a.epochs, inject_rate=a.inject_rate,
                                teacher=teacher_id, limit=a.limit, suffix=suffix,
                                multi=not a.no_multi, train_episodes=len(tr),
                                collection_env="deterministic planners"), "runs": {}}
    for seed in a.seeds:
        t0 = time.time()
        runs = {}
        bc = collect(tr, Q, expert, expert, 0.0, seed)
        m, info = train(bc, seed, epochs=a.epochs)
        save_model(m, MODELS_DIR / f"bc{suffix}_s{seed}.pt")
        runs["bc"] = info

        aug = collect(tr, Q, expert, expert, 0.0, seed + 1000, inject_rate=a.inject_rate)
        bc_aug = Data(bc.X + aug.X, bc.y + aug.y)
        m, info = train(bc_aug, seed, epochs=a.epochs)
        save_model(m, MODELS_DIR / f"bc_aug{suffix}_s{seed}.pt")
        runs["bc_aug"] = info

        for it, m, hist in dagger(tr, Q, expert, seed, init=bc, epochs=a.epochs, log=lambda *_: None):
            save_model(m, MODELS_DIR / f"bc_dagger{it}{suffix}_s{seed}.pt")
            runs[f"bc_dagger{it}"] = hist[-1]
        for it, m, hist in dagger(tr, Q, expert, seed, init=bc_aug, epochs=a.epochs, log=lambda *_: None):
            if it == 3:
                save_model(m, MODELS_DIR / f"bc_aug_dagger3{suffix}_s{seed}.pt")
                runs["bc_aug_dagger3"] = hist[-1]
        runs["seconds"] = round(time.time() - t0, 1)
        log["runs"][seed] = runs
        print(f"seed {seed}: {json.dumps(runs)}")
    if a.teacher == "llm":
        log["teacher_usage"] = expert.client.usage.as_dict()
    (MODELS_DIR / f"training_log{suffix}.json").write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
