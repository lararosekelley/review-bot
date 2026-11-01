"""Group cases into replay units: one per PR head, holding every bug from it.

A PR that introduced several bugs is reviewed once and scored against all of
them, so a finding about any of its bugs counts. A seeded case is a unit of its
own, since its seed changes the PR head.
"""

import json
from pathlib import Path

EVAL = Path(__file__).resolve().parent.parent


def unit_id(case):
    if case.get("seed"):
        return case["id"]
    repo = case["repo"].split("/")[1]
    pr = case["pr"]
    return f"{repo}-pr{pr['number']}" if pr["number"] else f"{repo}-c{pr['head_sha'][:7]}"


def group(cases):
    units = {}
    for case in sorted(cases, key=lambda c: c["id"]):
        if "git-stk:stack" in (case["pr"]["body"] or ""):
            raise ValueError(f"{case['id']}: PR body still carries git-stk's stack note")
        uid = unit_id(case)
        unit = units.setdefault(uid, {
            "id": uid, "repo": case["repo"], "kind": "control", "split": case["split"],
            "pr": case["pr"], "seed": case.get("seed"), "cases": [], "fixes": [], "expected": [],
        })
        if unit["split"] != case["split"]:
            raise ValueError(f"{uid}: cases disagree on split")
        unit["cases"].append(case["id"])
        if case.get("fix"):
            unit["fixes"].append(case["fix"]["sha"])
        for exp in case["expected"]:
            unit["expected"].append({**exp, "case": case["id"]})
        if case["kind"] != "control":
            unit["kind"] = case["kind"]
    return units


def load(paths=None):
    """Units from the given case files, or from every case when none are given."""
    if not paths:
        paths = [p for d in ("cases", "cases-private") for p in (EVAL / d).glob("*.json")]
    return group(json.loads(Path(p).read_text()) for p in paths)
