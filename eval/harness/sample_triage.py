"""Write a sample of the judge's calls for a person to label, or read the labels back.

    python3 -I eval/harness/sample_triage.py eval/runs/<config> [--valid 20 --nit 8 --wrong 2]
        [--matches 0] [--name triage-sample] [--exclude eval/labels/<earlier>.json]
    python3 -I eval/harness/sample_triage.py --apply eval/labels/<name>.md

Picks findings that matched no known bug (triage calls), and optionally pairs the
judge matched to a historical bug (match calls), from public repos only, at most two
per unit, and writes eval/labels/<name>.md (to fill in) and <name>.json (to join
the labels back to runs). `--apply` copies the filled-in labels into the json.
"""

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import units  # noqa: E402

HEADER = """<!-- markdownlint-disable MD013 -->

# Judge calibration: {name}

Fill in each `label:` and leave it blank to skip. A triage item is a comment the reviewer posted
that matched no known bug; label it:

- valid: a real defect worth asking the author to change.
- nit: true, but not worth a requested change.
- wrong: false, or not supported by the code.

A match item pairs a comment with a known bug the judge says it found; label it:

- yes: the comment names the same defect.
- partial: same code and a related concern, but it misses what actually goes wrong.
- no: a different defect.
"""
LABEL = re.compile(r"^label:[ \t]*(valid|nit|wrong|yes|partial|no)\b", re.M)


def apply_labels(md):
    """Copy the labels filled in on <name>.md into <name>.json, as a person's."""
    sheet = Path(md)
    labels = {}
    for block in re.split(r"(?m)^(?=## \d+\. )", sheet.read_text()):
        head, found = re.match(r"## (\d+)\. ", block), LABEL.search(block)
        if head and found:
            labels[int(head[1])] = found[1]
    meta_path = sheet.with_suffix(".json")
    meta = json.loads(meta_path.read_text())
    for m in meta:
        if m["n"] in labels:
            m.update(label=labels[m["n"]], label_source="person")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    print(f"{len(labels)} of {len(meta)} items labeled")


def item(i, u, f, title, judge_line):
    sha = u["pr"]["head_sha"]
    url = f"https://github.com/{u['repo']}/blob/{sha}/{f['path']}#L{f.get('startLine') or f['line']}"
    pr = f"PR #{u['pr']['number']}" if u["pr"]["number"] else f"commit {sha[:7]}"
    return f"""## {i}. {u['repo'].split('/')[1]} {pr}: `{f['path']}:{f['line']}` ({title})

[Code at the PR head]({url}). PR title: {u['pr']['title']}

~~~~text
{f['body'].strip()}
~~~~

{judge_line}

label:
"""


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("config_dir", type=Path, nargs="?")
    p.add_argument("--valid", type=int, default=20)
    p.add_argument("--nit", type=int, default=8)
    p.add_argument("--wrong", type=int, default=2)
    p.add_argument("--matches", type=int, default=0, help="judge match calls to include")
    p.add_argument("--name", default="triage-sample")
    p.add_argument("--exclude", type=Path, action="append", default=[],
                   help="an earlier sample's json; its findings are not picked again")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--apply", metavar="MD", help="read the labels filled in on a sample's .md")
    args = p.parse_args()
    if args.apply:
        return apply_labels(args.apply)
    if not args.config_dir:
        p.error("config_dir is required")

    all_units = units.load()
    private = {json.loads(c.read_text())["repo"] for c in (units.EVAL / "cases-private").glob("*.json")}
    scores = json.loads((args.config_dir / "scores.json").read_text())
    excluded = {(m["unit"], m["path"], m["line"]) for e in args.exclude for m in json.loads(e.read_text())}
    pool = {"valid": [], "nit": [], "wrong": [], "match": []}
    for s in scores["runs"]:
        u = all_units[s["case"]]
        if u["repo"] in private:
            continue
        rows = (args.config_dir / s["case"] / s["run"] / "findings.jsonl").read_text().splitlines()
        posted = [f for f in map(json.loads, filter(None, rows)) if f["status"] == "posted"]
        for t in s["triage"]:
            pool[t["verdict"]].append((s, u, posted[t["finding"]], t))
        # Seeded matches are near-certain; historical ones are where the judge's calls vary.
        for m in s["matches"] if u["kind"] == "historical" else []:
            pool["match"].append((s, u, posted[m["finding"]], m))

    rng = random.Random(args.seed)
    picked, seen, per_unit = [], set(excluded), Counter()
    for kind, want in (("valid", args.valid), ("nit", args.nit), ("wrong", args.wrong), ("match", args.matches)):
        cands = pool[kind][:]
        rng.shuffle(cands)
        got = 0
        for s, u, f, t in cands:
            key = (u["id"], f["path"], f["line"])
            if got == want or key in seen or per_unit[u["id"]] >= 2:
                continue
            seen.add(key)
            per_unit[u["id"]] += 1
            picked.append((kind, s, u, f, t))
            got += 1
    rng.shuffle(picked)

    out, meta = [HEADER.format(name=args.name)], []
    for i, (kind, s, u, f, t) in enumerate(picked, 1):
        record = {"n": i, "kind": "match" if kind == "match" else "triage", "config": args.config_dir.name,
                  "unit": u["id"], "run": s["run"], "path": f["path"], "line": f["line"]}
        if kind == "match":
            exp = u["expected"][t["expected"]]
            out.append(item(i, u, f, "match", f"Known bug, at `{exp['path']}:{exp['line']}`: "
                            f"{exp['description']}\n\nJudge: **{t['verdict']}**. {t['reason'].strip()}"))
            record.update(expected=t["expected"], judge=t["verdict"])
        else:
            out.append(item(i, u, f, "triage", f"Judge: **{t['verdict']}**. {t['reason'].strip()}"))
            record["judge"] = t["verdict"]
        meta.append(record)

    labels = units.EVAL / "labels"
    labels.mkdir(exist_ok=True)
    (labels / f"{args.name}.md").write_text("\n".join(out))
    (labels / f"{args.name}.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(len(meta), dict(Counter(m["judge"] for m in meta)))


if __name__ == "__main__":
    main()
