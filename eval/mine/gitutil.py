"""Shared read-only git helpers and mainline-to-PR mapping."""
import json
import re
import subprocess
from pathlib import Path

MAINLINE = "origin/main"
EXCLUDE = re.compile(
    r"(^|/)(tests?|docs?|e2e|fixtures|__tests__|benches)/|_test\.rs$|\.(test|spec)\.[jt]sx?$"
    r"|\.md$|\.lock$|(^|/)package-lock\.json$|(^|/)CHANGELOG|\.snap$|(^|/)LICENSE"
)


def git(repo, *args, check=True):
    res = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and res.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {res.stderr.strip()}")
    return res.stdout if res.returncode == 0 else None


def exists(repo, sha):
    return bool(sha) and git(repo, "cat-file", "-e", f"{sha}^{{commit}}", check=False) is not None


def load_prs(raw_dir):
    return json.loads((Path(raw_dir) / "prs.json").read_text())


def mainline(repo):
    """Return (ordered shas, {sha: subject})."""
    out = git(repo, "log", "--first-parent", "--reverse", "--format=%H%x00%s", MAINLINE)
    shas, subjects = [], {}
    for line in out.splitlines():
        sha, subject = line.split("\0", 1)
        shas.append(sha)
        subjects[sha] = subject
    return shas, subjects


def units(repo, prs):
    """Group mainline commits into PR units and direct-push units, in mainline order."""
    shas, subjects = mainline(repo)
    index = {s: i for i, s in enumerate(shas)}
    owner = {}
    for pr in sorted(prs, key=lambda p: index.get(p["merge_sha"], -1)):
        tip = index.get(pr["merge_sha"])
        if tip is None:
            continue
        for i in range(tip, max(tip - pr["commits"], -1), -1):
            owner.setdefault(shas[i], pr["number"])
    by_pr = {p["number"]: p for p in prs}
    result, seen = [], set()
    for i, sha in enumerate(shas):
        num = owner.get(sha)
        if num is None:
            result.append({"pr": None, "commits": [sha], "subjects": [subjects[sha]]})
        elif num not in seen:
            seen.add(num)
            commits = [s for s in shas if owner.get(s) == num]
            result.append({"pr": num, "title": by_pr[num]["title"], "commits": commits,
                           "subjects": [subjects[s] for s in commits]})
    for u in result:
        u["tip"] = u["commits"][-1]
        u["base"] = git(repo, "rev-parse", f"{u['commits'][0]}^", check=False)
        u["base"] = u["base"].strip() if u["base"] else None
    return result


def removed_lines(repo, base, tip):
    """Yield (path, [line numbers in base]) for non-excluded files the range removes lines from."""
    out = git(repo, "diff", "-U0", "-M", "--no-color", base, tip)
    path = None
    hunks = {}
    for line in out.splitlines():
        if line.startswith("--- "):
            path = None if line == "--- /dev/null" else line[6:]
        elif line.startswith("@@") and path and not EXCLUDE.search(path):
            m = re.match(r"@@ -(\d+)(?:,(\d+))?", line)
            start, count = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            if count:
                hunks.setdefault(path, []).extend(range(start, start + count))
    return hunks


def blame(repo, rev, path, lines=None):
    """Return {final_line: (orig_sha, orig_line, orig_path)} from porcelain blame."""
    args = ["blame", "--porcelain", "-w"]
    if lines:
        for a, b in ranges(lines):
            args += ["-L", f"{a},{b}"]
    out = git(repo, *args, rev, "--", path)
    rows, names, sha = {}, {}, None
    for line in out.splitlines():
        m = re.match(r"^([0-9a-f]{40}) (\d+) (\d+)", line)
        if m:
            sha = m.group(1)
            rows[int(m.group(3))] = (sha, int(m.group(2)))
        elif line.startswith("filename "):
            names[sha] = line[len("filename "):]
    return {n: (sha, orig, names[sha]) for n, (sha, orig) in rows.items()}


def ranges(lines):
    lines = sorted(set(lines))
    start = prev = lines[0]
    for n in lines[1:]:
        if n != prev + 1:
            yield start, prev
            start = n
        prev = n
    yield start, prev
