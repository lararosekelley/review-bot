"""List merged PRs that could serve as controls, with the split each would land on.

usage: pick_controls.py REPO_PATH OWNER/NAME RAW_DIR [--min-later N]

A control is a merged, non-fix PR whose lines no later fix blames, old enough
that later work had a chance to find its bugs. Run after mine_fixes.py; add the
ones worth keeping to the repo's curation file as {"kind": "control"} entries.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_cases  # noqa: E402
import gitutil as g  # noqa: E402
import mine_fixes  # noqa: E402

DOCS = (".md", ".txt", ".lock", ".json", ".yml", ".yaml", ".toml", ".svg", ".png")


def code_lines(repo, base, head):
    total = 0
    for row in g.git(repo, "diff", "--numstat", f"{base}...{head}").splitlines():
        add, dele, path = row.split("\t", 2)
        if add.isdigit() and not path.endswith(DOCS):
            total += int(add) + int(dele)
    return total


def bot_comments(raw, number):
    path = raw / "comments" / f"{number}.json"
    if not path.exists():
        return None
    c = json.loads(path.read_text())
    return len(c["review_comments"]), len(c["issue_comments"])


def main():
    p = argparse.ArgumentParser(usage=__doc__)
    p.add_argument("repo", type=Path)
    p.add_argument("slug")
    p.add_argument("raw", type=Path)
    p.add_argument("--min-later", type=int, default=15, help="mainline units that must follow the PR")
    p.add_argument("--min-lines", type=int, default=40)
    p.add_argument("--max-lines", type=int, default=800)
    a = p.parse_args()

    repo = build_cases.Repo(a.repo, a.raw)
    prs = repo.prs
    order = [u["pr"] for u in repo.units]
    for i, unit in enumerate(repo.units):
        pr = prs.get(unit["pr"])
        if pr is None or mine_fixes.fix_ranges(unit, prs) or len(order) - i - 1 < a.min_later:
            continue
        if repo.blamed_by_later_fix(unit["pr"]):
            continue
        _, base, head = repo.pr_range(unit["pr"])
        lines = code_lines(a.repo, base, head)
        if not a.min_lines <= lines <= a.max_lines:
            continue
        comments = bot_comments(a.raw, unit["pr"])
        print(json.dumps({"pr": unit["pr"], "split": build_cases.split_of(a.slug, head), "lines": lines,
                          "inline_summary": comments, "title": pr["title"]}))


if __name__ == "__main__":
    main()
