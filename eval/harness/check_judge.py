"""Check the judge's triage calls against labeled findings.

    python3 -I eval/harness/check_judge.py eval/runs/<config> [--judge-model M]

Re-asks the judge, with score.py's current triage prompt, about every labeled
finding in eval/labels/triage-sample.json, and prints how often it agrees with
the labels.
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
    p.add_argument("--judge-model", default="claude-opus-5-5")
    p.add_argument("--jobs", type=int, default=6)
    args = p.parse_args()
    if "ANTHROPIC_API_KEY" not in os.environ:
        sys.exit("ANTHROPIC_API_KEY is required for the judge.")

    labeled = [m for m in json.loads((units.EVAL / "labels/triage-sample.json").read_text())
               if m.get("label") in ("valid", "nit", "wrong")]
    all_units = units.load()
    judge = score.Judge(args.judge_model, args.config_dir / "judge-cache.json")

    def ask(m):
        u = all_units[m["unit"]]
        rows = (args.config_dir / m["unit"] / m["run"] / "findings.jsonl").read_text().splitlines()
        f = next(f for f in map(json.loads, filter(None, rows))
                 if f["status"] == "posted" and f["path"] == m["path"] and f["line"] == m["line"])
        repo_dir = replay.checkout(u, Path.home() / "Code/personal", replay.WORK_ROOT)
        answer = judge.ask(score.TRIAGE_PROMPT.format(
            title=u["pr"]["title"], find_loc=score.loc(f["path"], f["line"], f.get("startLine")),
            body=f["body"]), score.TRIAGE_SCHEMA, repo_dir)
        return m, answer["verdict"]

    with ThreadPoolExecutor(args.jobs) as pool:
        results = list(pool.map(ask, labeled))

    pairs = Counter((verdict, m["label"]) for m, verdict in results)
    agree = sum(v for (j, lab), v in pairs.items() if j == lab)
    print(f"agreement: {agree}/{len(results)}")
    for j in ("valid", "nit", "wrong"):
        row = {lab: v for (jj, lab), v in pairs.items() if jj == j}
        print(f"  judge {j:<6} -> {row}")
    for m, verdict in results:
        if verdict != m["label"]:
            print(f"  #{m['n']}: judge {verdict}, label {m['label']}")
    print(f"judge cost this pass: ${judge.cost:.2f}")


if __name__ == "__main__":
    main()
