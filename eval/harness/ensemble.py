"""Estimate multi-pass reviews from a scored configuration's independent reps.

    python3 -I eval/harness/ensemble.py eval/runs/<config>

For every unit, combinations of k reps stand in for a review that runs k passes
and merges their findings. Findings from different passes are merged when they
match the same expected bug, or sit in the same file within 3 lines of each
other. "union" keeps every merged finding; "vote" keeps those raised by at
least 2 passes. The merge is positional, so it approximates what an LLM merge
step would do.
"""

import argparse
import json
from itertools import combinations
from pathlib import Path
from statistics import mean


def findings(config_dir, s):
    rows = (config_dir / s["case"] / s["run"] / "findings.jsonl").read_text().splitlines()
    posted = [f for f in map(json.loads, filter(None, rows)) if f["status"] == "posted"]
    matched = {m["finding"]: m["expected"] for m in s["matches"] if m["verdict"] == "yes"}
    triage = {t["finding"]: t["verdict"] for t in s["triage"]}
    out = []
    for i, f in enumerate(posted):
        out.append({"rep": s["run"], "path": f["path"], "line": f["line"] or 0,
                    "bug": matched.get(i), "verdict": "match" if i in matched else triage.get(i, "partial")})
    return out


def merge(fs):
    clusters = []
    for f in fs:
        for c in clusters:
            if (f["bug"] is not None and f["bug"] in c["bugs"]) or any(
                    g["path"] == f["path"] and abs(g["line"] - f["line"]) <= 3 for g in c["members"]):
                c["members"].append(f)
                if f["bug"] is not None:
                    c["bugs"].add(f["bug"])
                break
        else:
            clusters.append({"members": [f], "bugs": {f["bug"]} if f["bug"] is not None else set()})
    return clusters


def evaluate(units, k, min_reps):
    recall, per_pr, noise, cost = [], [], [], []
    for u in units:
        for combo in combinations(sorted(u["reps"]), k):
            fs = [f for r in combo for f in u["reps"][r]["findings"]]
            kept = [c for c in merge(fs) if len({m["rep"] for m in c["members"]}) >= min_reps]
            caught = set().union(*(c["bugs"] for c in kept)) if kept else set()
            if u["n_bugs"]:
                recall.extend(i in caught for i in range(u["n_bugs"]))
            per_pr.append(len(kept))
            noise.append(sum(all(m["verdict"] in ("nit", "wrong") for m in c["members"]) for c in kept))
            cost.append(sum(u["reps"][r]["cost"] for r in combo))
    return mean(recall), mean(per_pr), mean(noise), mean(cost)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("config_dir", type=Path)
    args = p.parse_args()
    scores = json.loads((args.config_dir / "scores.json").read_text())["runs"]

    by_unit = {}
    for s in scores:
        if s["status"] != "ok":
            continue
        u = by_unit.setdefault(s["case"], {"n_bugs": len(s["expected"]), "reps": {}})
        u["reps"][s["run"]] = {"findings": findings(args.config_dir, s), "cost": s["cost_usd"] or 0}
    units = [u for u in by_unit.values() if len(u["reps"]) >= 2]
    reps = min(len(u["reps"]) for u in units)

    print(f"{'review':<18}{'recall':>8}{'findings/PR':>13}{'noise/PR':>10}{'cost':>8}")
    rows = [(f"{k} pass union", k, 1) for k in range(1, reps + 1)]
    rows += [(f"{k} pass vote>=2", k, 2) for k in range(2, reps + 1)]
    for label, k, min_reps in rows:
        r, n, z, c = evaluate(units, k, min_reps)
        print(f"{label:<18}{r:>8.1%}{n:>13.2f}{z:>10.2f}{c:>8.3f}")


if __name__ == "__main__":
    main()
