"""Write one case JSON per curated entry.

usage: build_cases.py REPO_PATH OWNER/NAME RAW_DIR CURATION_JSON OUT_DIR

Curated expected entries anchor either on a blamed line ("blame": {"line": N,
"fix_commit": sha-prefix}, a line number at the fix commit's parent) or on a
line at the introducing head ("line": N, location_source "manual").
"""
import difflib
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gitutil as g  # noqa: E402


def split_of(slug, head_sha):
    """Split by PR, so bugs from one PR never land on both sides."""
    key = f"{slug}@{head_sha}".encode()
    return "holdout" if int(hashlib.sha256(key).hexdigest()[:8], 16) % 10 < 3 else "dev"


class Repo:
    def __init__(self, path, raw):
        self.path = Path(path)
        self.prs = {p["number"]: p for p in g.load_prs(raw)}
        self.units = json.loads((Path(raw) / "units.json").read_text())
        self.candidates = {str(c["fix"]): c for c in json.loads((Path(raw) / "candidates.json").read_text())}
        self.by_label = {}
        for u in self.units:
            self.by_label[str(u["pr"]) if u["pr"] is not None else f"c-{u['commits'][0][:7]}"] = u

    def unit(self, label):
        return self.by_label[str(label)]

    def pr_range(self, label):
        """Return (pr dict or None, base, head) for an introducing unit."""
        unit = self.unit(label)
        pr = self.prs.get(unit["pr"])
        if pr is None:
            return None, unit["base"], unit["tip"]
        head, base = pr["head_sha"], pr["base_sha"]
        if g.exists(self.path, head) and g.exists(self.path, base):
            mb = g.git(self.path, "merge-base", base, head).strip()
            if int(g.git(self.path, "rev-list", "--count", f"{mb}..{head}")) == pr["commits"]:
                return pr, mb, head
        return pr, unit["base"], unit["tip"]

    def blob(self, rev, path):
        return g.git(self.path, "show", f"{rev}:{path}", check=False)

    def map_line(self, src_rev, dst_rev, path, line):
        src, dst = self.blob(src_rev, path), self.blob(dst_rev, path)
        if src is None or dst is None:
            return None
        if src == dst:
            return line
        sm = difflib.SequenceMatcher(None, src.splitlines(), dst.splitlines(), autojunk=False)
        for tag, i1, i2, j1, _ in sm.get_opcodes():
            if i1 < line <= i2:
                return j1 + (line - i1) if tag == "equal" else j1 + 1
        return None

    def blamed_line(self, fix_label, intro_label, path, anchor):
        cand = self.candidates[str(fix_label)]
        rows = [b for i in cand["introduced_by"] if str(i["unit"]) == str(intro_label)
                for b in i["blamed"]
                if b["path"] == path and b["fix_parent_line"] == anchor["line"]
                and b["fix_commit"].startswith(anchor.get("fix_commit", ""))]
        if len(rows) != 1:
            raise ValueError(f"{fix_label}: {len(rows)} blame rows for {path}:{anchor}")
        row = rows[0]
        tip, path = self.unit(intro_label)["tip"], row["orig_path"]
        at_tip = [n for n, origin in g.blame(self.path, tip, path).items()
                  if origin[:2] == (row["commit"], row["orig_line"])]
        if not at_tip:
            raise ValueError(f"{fix_label}: blamed line not found at {tip[:7]}:{path}")
        return tip, path, at_tip[0]

    def resolve(self, fix_label, intro_label, head, loc):
        """Return (path, line) at the introducing head."""
        if "blame" in loc:
            tip, path, line = self.blamed_line(fix_label, intro_label, loc["path"], loc["blame"])
            return path, self.map_line(tip, head, path, line)
        return loc["path"], loc.get("line")

    def blamed_by_later_fix(self, label):
        return sorted({c for c, cand in self.candidates.items()
                       for i in cand["introduced_by"] if str(i["unit"]) == str(label)})


def build(repo, slug, entry):
    intro = entry["intro"]
    pr, base, head = repo.pr_range(intro)
    unit = repo.unit(intro)
    case = {
        "id": entry["id"],
        "repo": slug,
        "kind": entry.get("kind", "historical"),
        "split": split_of(slug, head),
        "pr": {
            "number": pr["number"] if pr else None,
            "title": pr["title"] if pr else unit["subjects"][0],
            "body": pr["body"] if pr else g.git(repo.path, "show", "-s", "--format=%b", head).strip(),
            "base_sha": base,
            "head_sha": head,
            "commits": pr["commits"] if pr else 1,
        },
        "fix": None,
        "expected": [],
        "prior_bot": entry.get("prior_bot", {"status": "n/a", "comment_ids": [], "note": ""}),
    }
    if case["kind"] == "control":
        later = repo.blamed_by_later_fix(intro)
        if later:
            raise ValueError(f"{entry['id']}: lines blamed by fixes {later}")
        return case
    fix_unit = repo.unit(entry["fix"])
    case["fix"] = {"pr": fix_unit["pr"], "sha": fix_unit["tip"]}
    for exp in entry["expected"]:
        path, line = repo.resolve(entry["fix"], intro, head, exp)
        alt = [dict(zip(("path", "line"), repo.resolve(entry["fix"], intro, head, a)))
               for a in exp.get("alt", [])]
        case["expected"].append({
            "path": path,
            "line": line,
            "window": exp.get("window", 5),
            "alt": alt,
            "description": exp["description"],
            "severity": exp["severity"],
            "visibility": exp["visibility"],
            "location_source": "blame" if "blame" in exp else "manual",
        })
    return case


def main():
    if len(sys.argv) != 6:
        sys.exit(__doc__)
    repo = Repo(sys.argv[1], sys.argv[3])
    slug = sys.argv[2]
    out = Path(sys.argv[5])
    out.mkdir(parents=True, exist_ok=True)
    entries = json.loads(Path(sys.argv[4]).read_text())
    for entry in entries:
        case = build(repo, slug, entry)
        (out / f"{case['id']}.json").write_text(json.dumps(case, indent=2) + "\n")
    print(f"{slug}: wrote {len(entries)} cases to {out}")


if __name__ == "__main__":
    main()
