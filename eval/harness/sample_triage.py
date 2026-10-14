"""Write a sample of the judge's triage calls for a person to label.

    python3 -I eval/harness/sample_triage.py eval/runs/<config> [--valid 20 --nit 8 --wrong 2]

Picks findings that matched no known bug, from public repos only, at most two
per unit, and writes eval/labels/triage-sample.md (to fill in) and
triage-sample.json (to join the labels back to runs).
"""

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import units  # noqa: E402

HEADER = """<!-- markdownlint-disable MD013 -->

# Judge calibration: triage sample

Each item is a comment the reviewer posted that matched no known bug, with the judge's call.
Fill in `label:` with valid, nit, or wrong. Leave it blank to skip.

- valid: a real defect worth asking the author to change.
- nit: true, but not worth a requested change.
- wrong: false, or not supported by the code.
"""


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("config_dir", type=Path)
    p.add_argument("--valid", type=int, default=20)
    p.add_argument("--nit", type=int, default=8)
    p.add_argument("--wrong", type=int, default=2)
    p.add_argument("--seed", type=int, default=1)
    args = p.parse_args()

    all_units = units.load()
    private = {json.loads(c.read_text())["repo"] for c in (units.EVAL / "cases-private").glob("*.json")}
    scores = json.loads((args.config_dir / "scores.json").read_text())
    pool = {"valid": [], "nit": [], "wrong": []}
    for s in scores["runs"]:
        u = all_units[s["case"]]
        if u["repo"] in private:
            continue
        rows = (args.config_dir / s["case"] / s["run"] / "findings.jsonl").read_text().splitlines()
        posted = [f for f in map(json.loads, filter(None, rows)) if f["status"] == "posted"]
        for t in s["triage"]:
            pool[t["verdict"]].append((s, u, posted[t["finding"]], t))

    rng = random.Random(args.seed)
    picked, seen, per_unit = [], set(), Counter()
    for verdict in ("valid", "nit", "wrong"):
        want = getattr(args, verdict)
        cands = pool[verdict][:]
        rng.shuffle(cands)
        got = 0
        for s, u, f, t in cands:
            key = (u["id"], f["path"], f["line"])
            if got == want or key in seen or per_unit[u["id"]] >= 2:
                continue
            seen.add(key)
            per_unit[u["id"]] += 1
            picked.append((s, u, f, t))
            got += 1
    rng.shuffle(picked)

    out, meta = [HEADER], []
    for i, (s, u, f, t) in enumerate(picked, 1):
        sha = u["pr"]["head_sha"]
        url = f"https://github.com/{u['repo']}/blob/{sha}/{f['path']}#L{f.get('startLine') or f['line']}"
        pr = f"PR #{u['pr']['number']}" if u["pr"]["number"] else f"commit {sha[:7]}"
        out.append(f"""## {i}. {u['repo'].split('/')[1]} {pr}: `{f['path']}:{f['line']}`

[Code at the PR head]({url}). PR title: {u['pr']['title']}

~~~~text
{f['body'].strip()}
~~~~

Judge: **{t['verdict']}**. {t['reason'].strip()}

label:
""")
        meta.append({"n": i, "unit": u["id"], "run": s["run"], "path": f["path"],
                     "line": f["line"], "judge": t["verdict"]})

    labels = units.EVAL / "labels"
    labels.mkdir(exist_ok=True)
    (labels / "triage-sample.md").write_text("\n".join(out))
    (labels / "triage-sample.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(len(meta), dict(Counter(m["judge"] for m in meta)))


if __name__ == "__main__":
    main()
