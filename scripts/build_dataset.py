"""Build the evolving-constraint task set from TravelPlanner.

    python scripts/build_dataset.py --seed 0 --episodes-per-query 4
"""

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taskflow.common import TASKS_DIR, manifest, query_index  # noqa: E402
from taskflow.data.tasks import build_dataset, save  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--episodes-per-query", type=int, default=4)
    ap.add_argument("--out", type=Path, default=TASKS_DIR)
    a = ap.parse_args()
    Q = query_index()
    ds = build_dataset(list(Q.values()), seed=a.seed, episodes_per_query=a.episodes_per_query)
    stats = {}
    for s, eps in ds["episodes"].items():
        turns = [t for e in eps for t in e.turns]
        stats[s] = {
            "queries": len({e.qid for e in eps}), "episodes": len(eps), "turns": len(turns),
            "infeasible_turns": sum(not t.feasible for t in turns),
            "ops": dict(collections.Counter(t.diff["op"] for t in turns)),
            "types": dict(collections.Counter(t.diff["target_type"] for t in turns)),
            "chain_lengths": dict(collections.Counter(len(e.turns) for e in eps)),
        }
    m = manifest(seed=a.seed, episodes_per_query=a.episodes_per_query)
    m["stats"] = stats
    m["usable_queries"] = len(ds["bases"])
    m["source_queries"] = len(Q)
    save(ds, a.out, m)
    (a.out / "split_of_query.json").write_text(json.dumps(ds["split_of"], indent=1))
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
