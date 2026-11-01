"""Run smoke cases through the real action in the sandbox repo, and compare with the replay.

    python3 -I eval/harness/replay.py $(python3 -I eval/sandbox/smoke.py cases) --reps 3 --config smoke
    python3 -I eval/sandbox/smoke.py push --ref v1.4.0      # open one PR per smoke case
    python3 -I eval/sandbox/smoke.py rereview               # ask each PR for a re-review
    python3 -I eval/sandbox/smoke.py compare eval/runs/smoke
    python3 -I eval/sandbox/smoke.py close                  # close the PRs, delete the branches

The replay fakes GitHub, so only the real action exercises posting the review
and its inline comments, updating the summary comment, and loading prior
findings on a re-review. Each smoke case becomes a PR in the sandbox repo whose
base and head carry the case's trees, with the source repo's own workflows
swapped for a review workflow that runs the action at `--ref`. The PR diff is the
case's diff, except for changes to `.github/workflows`.

Every PR runs a real review against the sandbox repo's ANTHROPIC_API_KEY.
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "harness"))
import replay  # noqa: E402
import units  # noqa: E402

SANDBOX = "lararosekelley/review-bot-eval"
WORKFLOW = ".github/workflows/code-review.yml"
BRANCH = "smoke/"
FINDING_MARKER = "<!-- review-bot:finding"
# The sandbox is public, so only the owner's PRs and comments may spend its key.
WORKFLOW_TEMPLATE = """name: "Code Review Bot"

on:
  pull_request:
    types: [opened, ready_for_review]
  issue_comment:
    types: [created]

permissions:
  contents: read
  pull-requests: write
  issues: write
  id-token: write
  actions: read

jobs:
  review:
    if: >-
      (github.event_name == 'pull_request' && github.event.pull_request.author_association == 'OWNER') ||
      (github.event_name == 'issue_comment' && github.event.issue.pull_request &&
        contains(github.event.comment.body, '@bot review') && github.event.comment.author_association == 'OWNER')
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 1
          ref: refs/pull/${{ github.event.pull_request.number || github.event.issue.number }}/head
      - uses: lararosekelley/review-bot@REF
        with:
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
"""
SUMMARY_MARKER = "<!-- review-bot:summary -->"


def run(*args, cwd=None, env=None, input=None):
    return subprocess.run(args, cwd=cwd, env=env, input=input, check=True,
                          capture_output=True, text=True).stdout.strip()


def gh_json(*args):
    return json.loads(run("gh", *args))


def smoke_units(ids):
    every = units.load()
    ids = ids or json.loads((HERE / "smoke.json").read_text())["units"]
    missing = [i for i in ids if i not in every]
    if missing:
        sys.exit(f"unknown units: {', '.join(missing)}")
    return [every[i] for i in ids]


def workflow(ref):
    """The action called directly at `ref`: the reusable workflow always runs the action at @v1."""
    return WORKFLOW_TEMPLATE.replace("REF", ref)


def tree(repo, commit, blob):
    """The commit's tree with its workflows replaced by the sandbox's review workflow."""
    with tempfile.NamedTemporaryFile(dir=repo / ".git", prefix="smoke-index-") as idx:
        env = {**os.environ, "GIT_INDEX_FILE": idx.name}
        run("git", "read-tree", commit, cwd=repo, env=env)
        run("git", "rm", "--cached", "-r", "-q", "--ignore-unmatch", ".github/workflows", cwd=repo, env=env)
        run("git", "update-index", "--add", "--cacheinfo", f"100644,{blob},{WORKFLOW}", cwd=repo, env=env)
        return run("git", "write-tree", cwd=repo, env=env)


def cmd_cases(a):
    print(" ".join(str(HERE.parent / "cases" / f"{c}.json") for u in smoke_units([]) for c in u["cases"]))


def cmd_push(a):
    text = workflow(a.ref)
    open_heads = {p["headRefName"] for p in open_prs()}
    with tempfile.TemporaryDirectory(prefix="smoke-") as work:
        for unit in smoke_units(a.units):
            branch = f"{BRANCH}{unit['id']}"
            if f"{branch}/head" in open_heads:
                print(f"{unit['id']}: already open, skipped")
                continue
            repo = replay.checkout(unit, a.src_root, Path(work))
            blob = run("git", "hash-object", "-w", "--stdin", cwd=repo, input=text)
            pr = unit["pr"]
            base = run("git", "commit-tree", tree(repo, pr["base_sha"], blob), "-p", pr["base_sha"],
                       "-m", "chore: add the review workflow", cwd=repo)
            head = run("git", "commit-tree", tree(repo, "HEAD", blob), "-p", base,
                       "-m", pr["title"], cwd=repo)
            run("git", "push", "--quiet", "--force", f"git@github.com:{SANDBOX}.git",
                f"{base}:refs/heads/{branch}/base", f"{head}:refs/heads/{branch}/head", cwd=repo)
            url = run("gh", "pr", "create", "--repo", SANDBOX, "--base", f"{branch}/base",
                      "--head", f"{branch}/head", "--title", pr["title"], "--body", pr["body"] or "")
            print(f"{unit['id']}: {url}")


def open_prs():
    prs = gh_json("pr", "list", "--repo", SANDBOX, "--state", "open", "--limit", "100",
                  "--json", "number,headRefName,url")
    return [p for p in prs if p["headRefName"].startswith(BRANCH)]


def unit_of(pr):
    return pr["headRefName"][len(BRANCH):].removesuffix("/head")


def cmd_rereview(a):
    for pr in open_prs():
        run("gh", "pr", "comment", str(pr["number"]), "--repo", SANDBOX, "--body", "@bot review")
        print(f"{unit_of(pr)}: asked for a re-review on {pr['url']}")


def real_review(number):
    comments = gh_json("api", "--paginate", "--slurp", f"repos/{SANDBOX}/pulls/{number}/comments")
    issue = gh_json("api", "--paginate", "--slurp", f"repos/{SANDBOX}/issues/{number}/comments")
    inline = [c for page in comments for c in page
              if c["user"]["type"] == "Bot" and FINDING_MARKER in (c["body"] or "")]
    summaries = [c for page in issue for c in page
                 if c["user"]["type"] == "Bot" and SUMMARY_MARKER in (c["body"] or "")]
    return inline, summaries


def local_reviews(config, unit_id):
    reps = []
    for meta in sorted((config / unit_id).glob("*/meta.json")):
        if json.loads(meta.read_text())["status"] != "ok":
            continue
        rows = [json.loads(r) for r in (meta.parent / "findings.jsonl").read_text().splitlines() if r.strip()]
        reps.append([r for r in rows if r["status"] == "posted"])
    return reps


def cmd_compare(a):
    problems = 0
    print(f"{'unit':<40}{'real':>6}{'local':>12}  files in common  summary")
    for pr in open_prs():
        uid = unit_of(pr)
        inline, summaries = real_review(pr["number"])
        reps = local_reviews(a.config, uid)
        counts = [len(r) for r in reps]
        span = f"{min(counts)}-{max(counts)}" if counts else "none"
        real_files = {c["path"] for c in inline}
        local_files = {f["path"] for r in reps for f in r}
        common = f"{len(real_files & local_files)}/{len(real_files)}" if real_files else "-"
        summary = "ok" if len(summaries) == 1 else f"{len(summaries)} found"
        flag = (not counts or not min(counts) <= len(inline) <= max(counts) or len(summaries) != 1)
        problems += flag
        print(f"{uid:<40}{len(inline):>6}{span:>12}  {common:>15}  {summary}{'  <- check' if flag else ''}")
        if counts and a.verbose:
            print(f"    local mean {mean(counts):.1f}; {pr['url']}")
    if problems:
        print(f"\n{problems} PR(s) differ from the replay: a count outside the local range, or not "
              "exactly one summary. Read those reviews before trusting the replay for this release.")


def cmd_close(a):
    for pr in open_prs():
        run("gh", "pr", "close", str(pr["number"]), "--repo", SANDBOX)
        branch = pr["headRefName"].removesuffix("/head")
        for side in ("head", "base"):
            subprocess.run(["gh", "api", "-X", "DELETE", f"repos/{SANDBOX}/git/refs/heads/{branch}/{side}"],
                           capture_output=True)
        print(f"{unit_of(pr)}: closed")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("cases", help="print the smoke cases' files, for replay.py")
    push = sub.add_parser("push", help="open a sandbox PR per smoke case")
    push.add_argument("units", nargs="*", help="unit ids (default: smoke.json)")
    push.add_argument("--ref", required=True, help="review-bot tag, branch, or commit to run")
    push.add_argument("--src-root", type=Path, default=Path.home() / "Code/personal")
    sub.add_parser("rereview", help="ask every open smoke PR for a re-review")
    comp = sub.add_parser("compare", help="compare the posted reviews with a replay configuration")
    comp.add_argument("config", type=Path, help="eval/runs/<config> holding replays of the smoke units")
    comp.add_argument("--verbose", action="store_true")
    sub.add_parser("close", help="close every smoke PR and delete its branches")
    a = p.parse_args()
    {"cases": cmd_cases, "push": cmd_push, "rereview": cmd_rereview, "compare": cmd_compare, "close": cmd_close}[a.cmd](a)


if __name__ == "__main__":
    main()
