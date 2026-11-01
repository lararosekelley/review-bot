"""Check the judge's calls against labeled findings.

    python3 -I eval/harness/check_judge.py eval/runs/<config> [--labels eval/labels/<name>.json]
        [--person-only] [--judge-model M]

Re-asks the judge, with score.py's current prompts, about every labeled item in
the sample (triage items with the triage prompt, match items with the match
prompt), and prints how often it agrees with the labels. An item that names its
own config is read from that config's runs.
"""

import argparse
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay  # noqa: E402
import score  # noqa: E402
import units  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("config_dir", type=Path)
    p.add_argument("--labels", type=Path, default=units.EVAL / "labels/triage-sample.json")
    p.add_argument("--person-only", action="store_true", help="skip labels not written by a person")
    p.add_argument("--judge-model", default="claude-opus-5-5")
    p.add_argument("--jobs", type=int, default=6)
    args = p.parse_args()
    if "ANTHROPIC_API_KEY" not in os.environ:
        sys.exit("ANTHROPIC_API_KEY is required for the judge.")

    labeled = [m for m in json.loads(args.labels.read_text())
               if m.get("label") in ("valid", "nit", "wrong", "yes", "partial", "no")
               and (m.get("label_source") == "person" or not args.person_only)]
    all_units = units.load()
    configs = {m.get("config") for m in labeled}
    judges = {c: score.Judge(args.judge_model, (args.config_dir.parent / c if c else args.config_dir)
                             / "judge-cache.json") for c in configs}

    def ask(m):
        u = all_units[m["unit"]]
        config = args.config_dir.parent / m["config"] if m.get("config") else args.config_dir
        rows = (config / m["unit"] / m["run"] / "findings.jsonl").read_text().splitlines()
        f = next(f for f in map(json.loads, filter(None, rows))
                 if f["status"] == "posted" and f["path"] == m["path"] and f["line"] == m["line"])
        repo_dir = replay.checkout(u, Path.home() / "Code/personal", replay.WORK_ROOT)
        find_loc = score.loc(f["path"], f["line"], f.get("startLine"))
        if m.get("kind") == "match":
            exp = u["expected"][m["expected"]]
            answer = judges[m.get("config")].ask(score.MATCH_PROMPT.format(
                exp_loc=score.loc(exp["path"], exp["line"]), exp_desc=exp["description"],
                find_loc=find_loc, body=f["body"]), score.MATCH_SCHEMA, repo_dir)
        else:
            answer = judges[m.get("config")].ask(score.TRIAGE_PROMPT.format(
                title=u["pr"]["title"], find_loc=find_loc, body=f["body"]), score.TRIAGE_SCHEMA, repo_dir)
        return m, answer["verdict"]

    with ThreadPoolExecutor(args.jobs) as pool:
        results = list(pool.map(ask, labeled))

    pairs = Counter((verdict, m["label"]) for m, verdict in results)
    agree = sum(v for (j, lab), v in pairs.items() if j == lab)
    print(f"agreement: {agree}/{len(results)}")
    for j in ("valid", "nit", "wrong", "yes", "partial", "no"):
        row = {lab: v for (jj, lab), v in pairs.items() if jj == j}
        if row:
            print(f"  judge {j:<7} -> {row}")
    for m, verdict in results:
        if verdict != m["label"]:
            print(f"  #{m['n']}: judge {verdict}, label {m['label']}")
    print(f"judge cost this pass: ${sum(j.cost for j in judges.values()):.2f}")


if __name__ == "__main__":
    main()
