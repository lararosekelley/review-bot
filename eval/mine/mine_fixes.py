"""Blame the lines each fix removed and write <raw_dir>/candidates.json.

usage: mine_fixes.py REPO_PATH RAW_DIR
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gitutil as g  # noqa: E402

FIX = re.compile(r"^(fix|revert)\b|regression|^Revert ", re.I)
FIXES_REF = re.compile(r"\bfix(es|ed)? #\d+", re.I)


def fix_ranges(unit, prs):
    """Return (base, tip) ranges to blame: each fix commit, or the whole unit for a fix PR."""
    commits = [(f"{c}^", c) for c, s in zip(unit["commits"], unit["subjects"]) if FIX.search(s)]
    if commits:
        return commits
    pr = prs.get(unit["pr"])
    if pr and (FIX.search(pr["title"]) or FIXES_REF.search(pr["body"])):
        return [(unit["base"], unit["tip"])]
    return []


def label(unit):
    return unit["pr"] if unit["pr"] is not None else f"c-{unit['commits'][0][:7]}"


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    repo, raw = Path(sys.argv[1]), Path(sys.argv[2])
    prs = {p["number"]: p for p in g.load_prs(raw)}
    units = g.units(repo, list(prs.values()))
    owner = {sha: u for u in units for sha in u["commits"]}
    candidates = []
    for unit in units:
        ranges = fix_ranges(unit, prs) if unit["base"] else []
        if not ranges:
            continue
        blamed = defaultdict(list)
        for base, tip in ranges:
            for path, lines in g.removed_lines(repo, base, tip).items():
                for line, (sha, orig, orig_path) in g.blame(repo, base, path, lines).items():
                    intro = owner.get(sha)
                    if intro and intro is not unit:
                        blamed[label(intro)].append({"path": path, "fix_commit": tip,
                                                     "fix_parent_line": line,
                                                     "commit": sha, "orig_line": orig,
                                                     "orig_path": orig_path})
        candidates.append({
            "fix": label(unit),
            "fix_tip": unit["tip"],
            "fix_base": unit["base"],
            "title": prs[unit["pr"]]["title"] if unit["pr"] is not None else unit["subjects"][0],
            "fix_commits": [tip for _, tip in ranges],
            "subjects": unit["subjects"],
            "introduced_by": [
                {"unit": k, "lines": len(v), "files": dict(Counter(x["path"] for x in v)),
                 "blamed": v}
                for k, v in sorted(blamed.items(), key=lambda kv: -len(kv[1]))
            ],
        })
    (raw / "candidates.json").write_text(json.dumps(candidates, indent=1) + "\n")
    (raw / "units.json").write_text(json.dumps(units, indent=1) + "\n")
    print(f"{repo.name}: {len(candidates)} fix units, "
          f"{sum(1 for c in candidates if c['introduced_by'])} with blamed lines")


if __name__ == "__main__":
    main()
