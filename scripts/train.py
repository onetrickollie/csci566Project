"""Train the learned coordinators: BC, BC+augmentation, BC+DAgger (1-3 iters),
BC+augmentation+DAgger.

    python scripts/train.py --seeds 0 1 2
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
    a = ap.parse_args()
    MODELS_DIR.mkdir(exist_ok=True)
    Q = query_index()
    tr = load(TASKS_DIR, "train")
    expert = Oracle()
    log = {"manifest": manifest(seeds=a.seeds, epochs=a.epochs, inject_rate=a.inject_rate), "runs": {}}
    for seed in a.seeds:
        t0 = time.time()
        runs = {}
        bc = collect(tr, Q, expert, expert, 0.0, seed)
        m, info = train(bc, seed, epochs=a.epochs)
        save_model(m, MODELS_DIR / f"bc_s{seed}.pt")
        runs["bc"] = info

        aug = collect(tr, Q, expert, expert, 0.0, seed + 1000, inject_rate=a.inject_rate)
        bc_aug = Data(bc.X + aug.X, bc.y + aug.y)
        m, info = train(bc_aug, seed, epochs=a.epochs)
        save_model(m, MODELS_DIR / f"bc_aug_s{seed}.pt")
        runs["bc_aug"] = info

        for it, m, hist in dagger(tr, Q, expert, seed, init=bc, epochs=a.epochs, log=lambda *_: None):
            save_model(m, MODELS_DIR / f"bc_dagger{it}_s{seed}.pt")
            runs[f"bc_dagger{it}"] = hist[-1]
        for it, m, hist in dagger(tr, Q, expert, seed, init=bc_aug, epochs=a.epochs, log=lambda *_: None):
            if it == 3:
                save_model(m, MODELS_DIR / f"bc_aug_dagger3_s{seed}.pt")
                runs["bc_aug_dagger3"] = hist[-1]
        runs["seconds"] = round(time.time() - t0, 1)
        log["runs"][seed] = runs
        print(f"seed {seed}: {json.dumps(runs)}")
    (MODELS_DIR / "training_log.json").write_text(json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
