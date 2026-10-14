"""Replay eval cases through the review prompt with a local, headless Claude Code.

Each run reviews a pruned clone of the case's repo at the PR head, with the
exact prompt and tool allowlist that scripts/assemble-prompt.sh produces. A
fake `gh` and a fake inline-comment MCP server stand in for GitHub, and no
GitHub token is passed, so nothing can be posted.

    python3 -I eval/harness/replay.py eval/cases/git-stk-326.json \\
        --model claude-sonnet-5-5 --effort high --reps 3
    python3 -I eval/harness/replay.py --split dev --reps 3

Cases are grouped into units, one per PR (see units.py), and each unit is
replayed once. Output per run, under eval/runs/<config>/<unit>/<rep>/:
findings.jsonl, summary.md, meta.json, transcript.jsonl, gh.jsonl.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import units  # noqa: E402

ROOT = HERE.parent.parent
EVAL = ROOT / "eval"
NOTES_FILE = ".github/review-bot/REPO_NOTES.md"
# Outside this repo, so a reviewer exploring around its checkout cannot reach
# the cases and their expected bugs.
WORK_ROOT = Path.home() / ".cache/review-bot-eval/work"


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def checkout(unit, src_root, work_root):
    """Clone the source repo at the PR head, with no history past it.

    The source clone is never written to. Every ref except the PR branch and
    origin/main (the base) is dropped and unreachable objects are pruned, so
    the reviewer cannot find the fix in `git log`.
    """
    pr = unit["pr"]
    dest = work_root / unit["repo"].replace("/", "__") / pr["head_sha"][:12]
    if (dest / ".replay-ready").exists():
        return dest
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = src_root / unit["repo"].split("/")[1]
    subprocess.run(["git", "clone", "--quiet", "--no-checkout", str(src), str(dest)], check=True)
    branch = f"pr-{pr['number'] or 0}"
    git(dest, "checkout", "--quiet", "-B", branch, pr["head_sha"])
    for ref in git(dest, "for-each-ref", "--format=%(refname)").splitlines():
        if ref != f"refs/heads/{branch}":
            git(dest, "update-ref", "-d", ref)
    git(dest, "remote", "remove", "origin")
    git(dest, "update-ref", "refs/remotes/origin/main", pr["base_sha"])
    git(dest, "reflog", "expire", "--expire=now", "--all")
    git(dest, "gc", "--quiet", "--prune=now")
    for fix in unit["fixes"]:
        if subprocess.run(["git", "cat-file", "-e", fix], cwd=dest).returncode == 0:
            raise RuntimeError(f"{unit['id']}: fix {fix} still reachable in replay checkout")
    (dest / ".git" / "info" / "exclude").write_text(".replay-ready\n")
    (dest / ".replay-ready").touch()
    return dest


def assemble(case, repo_dir, cfg):
    """Run the real assemble-prompt.sh and return (prompt, claude_args)."""
    with tempfile.NamedTemporaryFile("r", suffix=".out") as out:
        notes = NOTES_FILE if cfg.notes == "head" and (repo_dir / NOTES_FILE).exists() else ""
        env = {
            "PATH": os.environ["PATH"],
            "GITHUB_ACTION_PATH": str(ROOT),
            "GITHUB_REPOSITORY": case["repo"],
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_OUTPUT": out.name,
            "BOT_NAME": "Code Review Bot",
            "REPO_NOTES": "",
            "REPO_NOTES_FILE": notes,
            "FOOTER": "",
            "MODEL": cfg.model,
            "EFFORT": cfg.effort,
            "EXTRA_TOOLS": "",
            "PR_NUMBER": str(case["pr"]["number"] or 0),
            "PR_TITLE": case["pr"]["title"],
            "PR_DRAFT": "false",
        }
        subprocess.run(["bash", str(ROOT / "scripts/assemble-prompt.sh")],
                       cwd=repo_dir, env=env, check=True)
        text = Path(out.name).read_text()
    head, _, rest = text.partition("\n")
    delim = head.split("<<", 1)[1]
    prompt, _, tail = rest.partition(f"\n{delim}\n")
    args = tail.strip().split("claude-args=", 1)[1]
    return prompt, args


def parse_args_line(line):
    """Split the claude-args output, which quotes only the tool list."""
    before, _, tools = line.partition(' --allowedTools "')
    return before.split() + ["--allowedTools", tools.rstrip('"')]


def run_one(case, repo_dir, cfg, out_dir):
    """Review one unit.

    Everything the reviewer can see, including its environment and HOME, lives
    in a private temp directory outside this repo, and holds only the PR's own
    fields, never the expected bugs.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt, args_line = assemble(case, repo_dir, cfg)
    (out_dir / "prompt.md").write_text(prompt)

    run_tmp = Path(tempfile.mkdtemp(prefix="replay-"))
    home, tmp, bin_dir = run_tmp / "home", run_tmp / "tmp", run_tmp / "bin"
    for d in (home, tmp, bin_dir):
        d.mkdir()
    case_path = run_tmp / "pr.json"
    case_path.write_text(json.dumps({"repo": case["repo"], "pr": case["pr"]}))
    findings, gh_log = run_tmp / "findings.jsonl", run_tmp / "gh.jsonl"
    for f in (findings, gh_log):
        f.write_text("")
    for script in ("fake_gh.py", "fake_inline_comment.py"):
        shutil.copy(HERE / script, bin_dir / script)
    gh = bin_dir / "gh"
    gh.write_text(f'#!/bin/sh\nexec python3 -I {bin_dir / "fake_gh.py"} "$@"\n')
    gh.chmod(0o755)
    mcp = run_tmp / "mcp.json"
    mcp.write_text(json.dumps({"mcpServers": {"github_inline_comment": {
        "command": "python3", "args": ["-I", str(bin_dir / "fake_inline_comment.py")],
        "env": {"REPLAY_CASE": str(case_path), "REPLAY_FINDINGS": str(findings)},
    }}}))

    env = {
        "HOME": str(home),
        "TMPDIR": str(tmp),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"],
        "REPLAY_CASE": str(case_path),
        "REPLAY_GH_LOG": str(gh_log),
        "PR_NUMBER": str(case["pr"]["number"] or 0),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    cmd = ["claude", "-p", prompt, *parse_args_line(args_line),
           "--mcp-config", str(mcp), "--strict-mcp-config",
           "--output-format", "stream-json", "--verbose"]
    start = time.time()
    with open(out_dir / "transcript.jsonl", "w") as transcript:
        try:
            proc = subprocess.run(cmd, cwd=repo_dir, env=env, stdout=transcript,
                                  stderr=subprocess.PIPE, text=True, timeout=cfg.timeout_min * 60)
            status, stderr = ("ok" if proc.returncode == 0 else "error"), proc.stderr
        except subprocess.TimeoutExpired:
            status, stderr = "timeout", ""
    shutil.copy(findings, out_dir / "findings.jsonl")
    shutil.copy(gh_log, out_dir / "gh.jsonl")
    shutil.rmtree(run_tmp, ignore_errors=True)

    result = {}
    for row in (out_dir / "transcript.jsonl").read_text().splitlines():
        try:
            event = json.loads(row)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            result = event
    (out_dir / "summary.md").write_text(result.get("result") or "")
    meta = {
        "case": case["id"], "model": cfg.model, "effort": cfg.effort, "notes": cfg.notes,
        "status": status, "wall_s": round(time.time() - start, 1),
        "cost_usd": result.get("total_cost_usd"), "num_turns": result.get("num_turns"),
        "usage": result.get("usage"), "stderr": stderr[-2000:],
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cases", nargs="*", type=Path, help="case files (default: every case)")
    p.add_argument("--split", choices=["dev", "holdout"])
    p.add_argument("--kind", choices=["historical", "control"])
    p.add_argument("--model", default="claude-sonnet-5-5")
    p.add_argument("--effort", default="high")
    p.add_argument("--notes", choices=["head", "none"], default="head",
                   help="use the repo notes file present at the PR head, or none")
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--timeout-min", type=int, default=20)
    p.add_argument("--config", help="run directory name (default: model-effort-notes)")
    p.add_argument("--src-root", type=Path, default=Path.home() / "Code/personal")
    p.add_argument("--work-root", type=Path, default=WORK_ROOT)
    cfg = p.parse_args()
    if "ANTHROPIC_API_KEY" not in os.environ:
        sys.exit("ANTHROPIC_API_KEY is required: replays run with an isolated HOME, like CI.")
    name = cfg.config or f"{cfg.model}-{cfg.effort or 'unset'}-notes_{cfg.notes}"

    jobs = []
    for unit in units.load(cfg.cases).values():
        if cfg.split and unit["split"] != cfg.split or cfg.kind and unit["kind"] != cfg.kind:
            continue
        repo_dir = checkout(unit, cfg.src_root, cfg.work_root)
        for rep in range(cfg.reps):
            out = EVAL / "runs" / name / unit["id"] / str(rep)
            if (out / "meta.json").exists() and json.loads((out / "meta.json").read_text())["status"] == "ok":
                continue
            jobs.append((unit, repo_dir, cfg, out))

    with ThreadPoolExecutor(cfg.jobs) as pool:
        for meta in pool.map(lambda j: run_one(*j), jobs):
            print(json.dumps({k: meta[k] for k in ("case", "status", "wall_s", "cost_usd", "num_turns")}))


if __name__ == "__main__":
    main()
