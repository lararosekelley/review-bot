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


def assemble(case, repo_dir, cfg, prompt_file):
    """Run the real assemble-prompt.sh in review mode; return the tool allowlist."""
    with tempfile.NamedTemporaryFile("r", suffix=".out") as out:
        notes = NOTES_FILE if cfg.notes == "head" and (repo_dir / NOTES_FILE).exists() else ""
        env = {
            "PATH": os.environ["PATH"],
            "GITHUB_ACTION_PATH": str(ROOT),
            "GITHUB_REPOSITORY": case["repo"],
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_OUTPUT": out.name,
            "MODE": "review",
            "BOT_NAME": "Code Review Bot",
            "REPO_NOTES": "",
            "REPO_NOTES_FILE": notes,
            "MODEL": cfg.model,
            "EFFORT": cfg.effort,
            "EXTRA_TOOLS": "",
            "PROMPT_FILE": str(prompt_file),
            "PR_NUMBER": str(case["pr"]["number"] or 0),
            "PR_TITLE": case["pr"]["title"],
            "PR_DRAFT": "false",
        }
        subprocess.run(["bash", str(ROOT / "scripts/assemble-prompt.sh")],
                       cwd=repo_dir, env=env, check=True)
        text = Path(out.name).read_text()
    return next(line[len("tools="):] for line in text.splitlines() if line.startswith("tools="))


def run_one(case, repo_dir, cfg, out_dir):
    """Review one unit with the action's own scripts: find, merge, then a dry-run post.

    Everything the reviewer can see, including its environment, HOME, and the
    scripts it runs under, lives in a private temp directory outside this repo,
    and holds only the PR's own fields, never the expected bugs.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    run_tmp = Path(tempfile.mkdtemp(prefix="replay-"))
    home, tmp, bin_dir = run_tmp / "home", run_tmp / "tmp", run_tmp / "bin"
    for d in (home, tmp, bin_dir / "scripts", bin_dir / "prompts"):
        d.mkdir(parents=True)
    prompt_file = run_tmp / "prompt.md"
    tools = assemble(case, repo_dir, cfg, prompt_file)
    shutil.copy(prompt_file, out_dir / "prompt.md")

    case_path = run_tmp / "pr.json"
    case_path.write_text(json.dumps({"repo": case["repo"], "pr": case["pr"]}))
    gh_log = run_tmp / "gh.jsonl"
    gh_log.write_text("")
    shutil.copy(HERE / "fake_gh.py", bin_dir / "fake_gh.py")
    shutil.copy(ROOT / "scripts/review.py", bin_dir / "scripts/review.py")
    shutil.copy(ROOT / "prompts/findings.schema.json", bin_dir / "prompts/findings.schema.json")
    gh = bin_dir / "gh"
    gh.write_text(f'#!/bin/sh\nexec python3 -I {bin_dir / "fake_gh.py"} "$@"\n')
    gh.chmod(0o755)

    env = {
        "HOME": str(home),
        "TMPDIR": str(tmp),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"],
        "REPLAY_CASE": str(case_path),
        "REPLAY_GH_LOG": str(gh_log),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    review = ["python3", "-I", str(bin_dir / "scripts/review.py")]
    steps = [
        [*review, "find", "--prompt-file", str(prompt_file), "--passes", str(cfg.passes),
         "--model", cfg.model, "--effort", cfg.effort, "--tools", tools,
         "--out-dir", str(run_tmp / "passes"), "--transcript-dir", str(run_tmp / "transcripts")],
        [*review, "merge", "--in-dir", str(run_tmp / "passes"), "--min-votes", str(cfg.min_votes),
         "--merge-model", cfg.merge_model, "--out", str(run_tmp / "merged.json")],
        [*review, "post", "--merged", str(run_tmp / "merged.json"), "--pr", str(case["pr"]["number"] or 0),
         "--dry-run", str(run_tmp / "findings.jsonl")],
    ]
    start, status, log = time.time(), "ok", []
    for step in steps:
        try:
            proc = subprocess.run(step, cwd=repo_dir, env=env, capture_output=True, text=True,
                                  timeout=cfg.timeout_min * 60)
            log.append(proc.stdout + proc.stderr)
            if proc.returncode:
                status = "error"
                break
        except subprocess.TimeoutExpired:
            status = "timeout"
            break

    for src, dst in (("findings.jsonl", "findings.jsonl"), ("findings.summary.md", "summary.md"),
                     ("merged.json", "merged.json"), ("gh.jsonl", "gh.jsonl")):
        if (run_tmp / src).exists():
            shutil.copy(run_tmp / src, out_dir / dst)
    for d in ("passes", "transcripts"):
        if (run_tmp / d).exists():
            shutil.copytree(run_tmp / d, out_dir / d, dirs_exist_ok=True)
    shutil.rmtree(run_tmp, ignore_errors=True)

    passes = [json.loads(p.read_text()) for p in sorted((out_dir / "passes").glob("pass-*.json"))] \
        if (out_dir / "passes").exists() else []
    merged = json.loads((out_dir / "merged.json").read_text()) if (out_dir / "merged.json").exists() else {}
    meta = {
        "case": case["id"], "model": cfg.model, "effort": cfg.effort, "notes": cfg.notes,
        "passes": cfg.passes, "min_votes": merged.get("min_votes"), "merge": merged.get("merge"),
        "status": status, "wall_s": round(time.time() - start, 1),
        "pass_wall_s": [p["wall_s"] for p in passes],
        "cost_usd": merged.get("cost_usd", sum(p.get("cost_usd") or 0 for p in passes)),
        "num_turns": sum(p.get("num_turns") or 0 for p in passes),
        "log": "".join(log)[-4000:],
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
    p.add_argument("--passes", type=int, default=1)
    p.add_argument("--min-votes", type=int, default=0, help="0 picks 1 for one pass, 2 otherwise")
    p.add_argument("--merge-model", default="claude-haiku-4-5-20251001")
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--timeout-min", type=int, default=20)
    p.add_argument("--config", help="run directory name (default: model-effort-notes)")
    p.add_argument("--src-root", type=Path, default=Path.home() / "Code/personal")
    p.add_argument("--work-root", type=Path, default=WORK_ROOT)
    cfg = p.parse_args()
    if "ANTHROPIC_API_KEY" not in os.environ:
        sys.exit("ANTHROPIC_API_KEY is required: replays run with an isolated HOME, like CI.")
    name = cfg.config or f"{cfg.model}-{cfg.effort or 'unset'}-p{cfg.passes}-notes_{cfg.notes}"

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
