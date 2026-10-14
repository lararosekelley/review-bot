"""Compare two scored configurations case by case.

    python3 -I eval/harness/compare.py eval/runs/<a> eval/runs/<b> [--split dev]

Each metric is averaged over a case's reps, then differenced (b - a) on the
cases both configurations ran. The interval is a 95% paired bootstrap over
cases.
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean

METRICS = {
    "recall_strict": lambda s: (
        mean(any(m["expected"] == i and m["verdict"] == "yes" for m in s["matches"])
             for i in range(len(s["expected"])))
        if s["expected"] else None),
    "noise_per_pr": lambda s: sum(t["verdict"] != "valid" for t in s["triage"]),
    "valid_unlabeled_per_pr": lambda s: sum(t["verdict"] == "valid" for t in s["triage"]),
    "posted_per_pr": lambda s: s["posted"],
    "cost_usd": lambda s: s["cost_usd"] or 0,
}


def per_case(path, split):
    runs = json.loads((path / "scores.json").read_text())["runs"]
    out = defaultdict(dict)
    grouped = defaultdict(list)
    for s in runs:
        if s["status"] == "ok" and (split is None or s["split"] == split):
            grouped[s["case"]].append(s)
    for case, rs in grouped.items():
        for name, fn in METRICS.items():
            vals = [v for v in (fn(s) for s in rs) if v is not None]
            if vals:
                out[name][case] = mean(vals)
    return out


def bootstrap(diffs, n=10000, seed=0):
    rng = random.Random(seed)
    means = sorted(mean(rng.choices(diffs, k=len(diffs))) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n)]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("a", type=Path)
    p.add_argument("b", type=Path)
    p.add_argument("--split", choices=["dev", "holdout"])
    args = p.parse_args()
    a, b = per_case(args.a, args.split), per_case(args.b, args.split)

    print(f"{'metric':<24}{'cases':>6}{'a':>10}{'b':>10}{'b - a':>10}   95% CI")
    for name in METRICS:
        shared = sorted(set(a[name]) & set(b[name]))
        if not shared:
            continue
        diffs = [b[name][c] - a[name][c] for c in shared]
        lo, hi = bootstrap(diffs) if len(diffs) > 1 else (diffs[0], diffs[0])
        print(f"{name:<24}{len(shared):>6}{mean(a[name][c] for c in shared):>10.3f}"
              f"{mean(b[name][c] for c in shared):>10.3f}{mean(diffs):>+10.3f}   [{lo:+.3f}, {hi:+.3f}]")


if __name__ == "__main__":
    main()
