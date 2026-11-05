"""Replay eval cases through the review prompt with a local, headless Claude Code or opencode.

Each run reviews a pruned clone of the case's repo at the PR head, with the
exact prompt and tool allowlist that scripts/assemble-prompt.sh produces. A
fake `gh` stands in for GitHub, and no GitHub token is passed, so nothing can
be posted.

    python3 -I eval/harness/replay.py eval/cases/git-stk-326.json \\
        --model claude-sonnet-5-5 --effort high --reps 3
    python3 -I eval/harness/replay.py --split dev --reps 3
    python3 -I eval/harness/replay.py --split dev --harness opencode --model openai/gpt-6.1-sol
    python3 -I eval/harness/replay.py --split dev --harness git-stk --git-stk ~/Code/personal/git-stk/target/debug/git-stk

Cases are grouped into units, one per PR (see units.py), and each unit is
replayed once. Output per run, under eval/runs/<config>/<unit>/<rep>/:
findings.jsonl, summary.md, meta.json, transcript.jsonl, gh.jsonl.
"""

import argparse
import fcntl
import re
import shlex
import hashlib
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
# opencode's model catalog and provider packages, shared across runs so each run does not refetch them.
OPENCODE_CACHE = Path.home() / ".cache/review-bot-eval/opencode-cache"
# The key each opencode provider reads; a run gets only the one its model needs.
PROVIDER_KEYS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "google": "GEMINI_API_KEY",
                 "openrouter": "OPENROUTER_API_KEY", "xai": "XAI_API_KEY", "mistral": "MISTRAL_API_KEY",
                 "deepseek": "DEEPSEEK_API_KEY"}


# git-stk's finding categories, as review-bot names them.
GIT_STK_CATEGORIES = {"bug": "Bug", "safety": "Safety", "security": "Security", "architecture": "Architecture",
                      "escape-hatch": "Escape Hatch", "error-handling": "Error Handling",
                      "coverage": "Missing Coverage", "surface-drift": "Surface Drift", "complexity": "Complexity"}


def model_key(cfg):
    """The API key variable a configuration's model needs."""
    return PROVIDER_KEYS.get(cfg.model.split("/")[0]) if cfg.harness == "opencode" else "ANTHROPIC_API_KEY"


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
    # The seed is named by a hash of its patch: a case id would tell the reviewer what to find.
    seed = unit.get("seed")
    name = pr["head_sha"][:12] + (f"-{hashlib.sha256(seed['patch'].encode()).hexdigest()[:8]}" if seed else "")
    dest = work_root / unit["repo"].replace("/", "__") / name
    if (dest / ".replay-ready").exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Concurrent sweeps share checkouts; one builds each, the others wait for it.
    with open(dest.parent / f".{dest.name}.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (dest / ".replay-ready").exists():
            return dest
        return build_checkout(unit, src_root, dest)


def build_checkout(unit, src_root, dest):
    pr = unit["pr"]
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = src_root / unit["repo"].split("/")[1]
    subprocess.run(["git", "clone", "--quiet", "--no-checkout", str(src), str(dest)], check=True)
    branch = f"pr-{pr['number'] or 0}"
    git(dest, "checkout", "--quiet", "-B", branch, pr["head_sha"])
    if unit.get("seed"):
        apply_seed(dest, unit["seed"]["patch"])
    for ref in git(dest, "for-each-ref", "--format=%(refname)").splitlines():
        if ref != f"refs/heads/{branch}":
            git(dest, "update-ref", "-d", ref)
    git(dest, "remote", "remove", "origin")
    git(dest, "update-ref", "refs/remotes/origin/main", pr["base_sha"])
    git(dest, "reflog", "expire", "--expire=now", "--all")
    git(dest, "gc", "--quiet", "--prune=now")
    hidden = unit["fixes"] + ([pr["head_sha"]] if unit.get("seed") else [])
    for sha in hidden:
        if subprocess.run(["git", "cat-file", "-e", sha], cwd=dest).returncode == 0:
            raise RuntimeError(f"{unit['id']}: {sha} still reachable in replay checkout")
    (dest / ".git" / "info" / "exclude").write_text(".replay-ready\n")
    (dest / ".replay-ready").touch()
    return dest


def apply_seed(dest, patch):
    """Fold the seeded defect into the PR's last commit, keeping its message, author, and dates.

    The unseeded head is then unreachable and pruned, so the reviewer cannot
    diff against it to find the seed.
    """
    subprocess.run(["git", "apply", "--index", "-"], cwd=dest, input=patch, text=True, check=True)
    name, email, date = git(dest, "log", "-1", "--format=%cn%x00%ce%x00%cI").split("\0")
    env = {**os.environ, "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email,
           "GIT_COMMITTER_DATE": date}
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "--quiet", "--amend", "--no-edit",
                    "--no-verify"], cwd=dest, env=env, check=True)


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
    """Review one unit with the action's own scripts: find, merge, optionally verify, then a dry-run post.

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
    if cfg.harness != "git-stk":
        shutil.copy(prompt_file, out_dir / "prompt.md")

    case_path = run_tmp / "pr.json"
    # A seeded head differs from the recorded one.
    pr = {**case["pr"], "head_sha": git(repo_dir, "rev-parse", "HEAD")}
    case_path.write_text(json.dumps({"repo": case["repo"], "pr": pr}))
    gh_log = run_tmp / "gh.jsonl"
    gh_log.write_text("")
    shutil.copy(HERE / "fake_gh.py", bin_dir / "fake_gh.py")
    shutil.copy(ROOT / "scripts/review.py", bin_dir / "scripts/review.py")
    shutil.copy(ROOT / "prompts/findings.schema.json", bin_dir / "prompts/findings.schema.json")
    shutil.copytree(ROOT / "prompts/rubric", bin_dir / "prompts/rubric")
    gh = bin_dir / "gh"
    gh.write_text(f'#!/bin/sh\nexec python3 -I {bin_dir / "fake_gh.py"} "$@"\n')
    gh.chmod(0o755)

    env = {
        "HOME": str(home),
        "TMPDIR": str(tmp),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        model_key(cfg): os.environ[model_key(cfg)],
        "REPLAY_CASE": str(case_path),
        "REPLAY_GH_LOG": str(gh_log),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        **({"XDG_CACHE_HOME": str(OPENCODE_CACHE)} if cfg.harness == "opencode" else {}),
    }
    review = ["python3", "-I", str(bin_dir / "scripts/review.py")]
    post = [*review, "post", "--merged", str(run_tmp / "merged.json"), "--pr", str(case["pr"]["number"] or 0),
            "--dry-run", str(run_tmp / "findings.jsonl")]
    if cfg.harness == "git-stk":
        return finish(case, cfg, out_dir, run_tmp, *run_git_stk(case, repo_dir, cfg, run_tmp, env, post))
    steps = [
        [*review, "find", "--harness", cfg.harness, "--prompt-file", str(prompt_file), "--passes", str(cfg.passes),
         "--model", cfg.model, "--effort", cfg.effort, "--tools", tools,
         "--out-dir", str(run_tmp / "passes"), "--transcript-dir", str(run_tmp / "transcripts")],
        [*review, "merge", "--harness", cfg.harness, "--in-dir", str(run_tmp / "passes"), "--min-votes", str(cfg.min_votes),
         "--merge-model", cfg.merge_model, "--out", str(run_tmp / "merged.json")],
        *([[*review, "verify", "--harness", cfg.harness, "--merged", str(run_tmp / "merged.json"), "--model", cfg.model,
             "--effort", cfg.effort, "--tools", tools]] if cfg.verify else []),
        post,
    ]
    start = time.time()
    status, log = run_steps(steps, repo_dir, env, cfg)
    return finish(case, cfg, out_dir, run_tmp, status, log, start)


def run_steps(steps, cwd, env, cfg):
    """Run each command in turn, stopping at the first that fails; return the status and their output."""
    status, log = "ok", []
    for step in steps:
        try:
            proc = subprocess.run(step, cwd=cwd, env=env, capture_output=True, text=True,
                                  timeout=cfg.timeout_min * 60)
            log.append(proc.stdout + proc.stderr)
            if proc.returncode:
                status = "error"
                break
        except subprocess.TimeoutExpired:
            status = "timeout"
            break
    return status, log


def run_git_stk(case, repo_dir, cfg, run_tmp, env, post):
    """Review one unit with git-stk's agent review (`git stk tour --findings`), then the action's dry-run post.

    git-stk reviews a local branch against the trunk, so it runs in a clone of
    the replay checkout made for this run, where its saved reviews cannot reach
    another run. Its findings are posted as the action posts its own, so both
    are scored the same way. A local review reads commit messages in place of
    the PR description.
    """
    start = time.time()
    branch = f"pr-{case['pr']['number'] or 0}"
    work = run_tmp / "repo"
    subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout", str(repo_dir), str(work)], check=True)
    git(work, "checkout", "--quiet", "-B", branch, f"origin/{branch}")
    git(work, "branch", "--force", "main", case["pr"]["base_sha"])
    git(work, "remote", "remove", "origin")

    agent_log = run_tmp / "agent.jsonl"
    agent = run_tmp / "bin" / "tour-agent"
    effort = f" --effort {shlex.quote(cfg.effort)}" if cfg.effort else ""
    prompts = run_tmp / "prompts"
    prompts.mkdir()
    agent.write_text("#!/bin/sh\nset -e\n"
                     f"prompt=$(mktemp {shlex.quote(str(prompts))}/prompt-XXXXXX)\n"
                     'cat > "$prompt"\n'
                     f'reply=$(claude -p --model {shlex.quote(cfg.model)}{effort} --output-format json < "$prompt")\n'
                     f"printf '%s\\n' \"$reply\" >> {shlex.quote(str(agent_log))}\n"
                     "printf '%s\\n' \"$reply\"\n")
    agent.chmod(0o755)
    settings = {"stk.tourAgentAllowed": str(agent), "stk.tourVerify": str(cfg.verify).lower(),
                "stk.noUpdateCheck": "true"}
    stk_env = {**env, "GIT_CONFIG_COUNT": str(len(settings)),
               **{f"GIT_CONFIG_{kind}_{i}": value for i, item in enumerate(settings.items())
                  for kind, value in zip(("KEY", "VALUE"), item)}}
    tour = [cfg.git_stk, "tour", branch, "--local", "--no-stack", "--findings", "--refresh-plan", "--agent", str(agent)]
    try:
        proc = subprocess.run(tour, cwd=work, env=stk_env, capture_output=True, text=True,
                              timeout=cfg.timeout_min * 60)
    except subprocess.TimeoutExpired:
        return "timeout", [], start
    log = [proc.stderr]
    if proc.returncode:
        return "error", log, start
    review = json.loads(proc.stdout)
    replies = [json.loads(line) for line in agent_log.read_text().splitlines() if line.strip()] \
        if agent_log.exists() else []
    dropped = re.search(r"dropped (\d+) it could rule out", proc.stderr)
    merged = {
        "summary": review["review"].get("title") or "",
        "confidence": (review.get("assessment") or {}).get("confidence") or 0,
        "findings": [git_stk_finding(f) for f in review["findings"]],
        "prior": [], "notes": {"coverage": "", "ci": "", "praise": ""},
        "passes": 1, "passes_requested": 1, "min_votes": 1,
        "dropped": [{}] * int(dropped[1]) if dropped else [],
        "cost_usd": round(sum(r.get("total_cost_usd") or 0 for r in replies), 4),
        "num_turns": sum(r.get("num_turns") or 0 for r in replies),
    }
    (run_tmp / "merged.json").write_text(json.dumps(merged, indent=2) + "\n")
    status, posted = run_steps([post], repo_dir, env, cfg)
    return status, log + posted, start


def git_stk_finding(f):
    """A git-stk finding in the shape the action's post step reads."""
    body = f["body"]
    if f.get("evidence"):
        body += f"\n\nEvidence: {f['evidence']}"
    if f.get("suggestion"):
        body += f"\n\n```suggestion\n{f['suggestion']}\n```"
    return {"path": f["path"], "line": f["line"], "start_line": f.get("startLine") or 0,
            "side": "LEFT" if f["side"] == "old" else "RIGHT",
            "category": GIT_STK_CATEGORIES.get(f.get("category") or "", "Bug"), "title": f["title"], "body": body}


def finish(case, cfg, out_dir, run_tmp, status, log, start):
    """Copy a run's output into its directory and write its meta.json."""
    for src, dst in (("findings.jsonl", "findings.jsonl"), ("findings.summary.md", "summary.md"),
                     ("merged.json", "merged.json"), ("gh.jsonl", "gh.jsonl")):
        if (run_tmp / src).exists():
            shutil.copy(run_tmp / src, out_dir / dst)
    for d in ("passes", "transcripts", "prompts"):
        if (run_tmp / d).exists():
            shutil.copytree(run_tmp / d, out_dir / d, dirs_exist_ok=True)
    shutil.rmtree(run_tmp, ignore_errors=True)

    passes = [json.loads(p.read_text()) for p in sorted((out_dir / "passes").glob("pass-*.json"))] \
        if (out_dir / "passes").exists() else []
    merged = json.loads((out_dir / "merged.json").read_text()) if (out_dir / "merged.json").exists() else {}
    meta = {
        "case": case["id"], "harness": cfg.harness, "model": cfg.model, "effort": cfg.effort, "notes": cfg.notes,
        "passes": cfg.passes, "min_votes": merged.get("min_votes"), "merge": merged.get("merge"),
        "verify": cfg.verify, "dropped": len(merged.get("dropped", [])),
        "status": status, "wall_s": round(time.time() - start, 1),
        "pass_wall_s": [p["wall_s"] for p in passes],
        "cost_usd": merged.get("cost_usd", sum(p.get("cost_usd") or 0 for p in passes)),
        "num_turns": merged.get("num_turns", sum(p.get("num_turns") or 0 for p in passes)),
        "log": "".join(log)[-4000:],
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cases", nargs="*", type=Path, help="case files (default: every case)")
    p.add_argument("--split", choices=["dev", "holdout"])
    p.add_argument("--kind", choices=["historical", "seeded", "control"])
    p.add_argument("--harness", choices=["claude-code", "opencode", "git-stk"], default="claude-code",
                   help="git-stk reviews with `git stk tour --findings`, its agent being `claude -p`")
    p.add_argument("--git-stk", default="git-stk", help="the git-stk binary for --harness git-stk")
    p.add_argument("--model", default="claude-sonnet-5-5", help="with opencode, provider/model")
    p.add_argument("--effort", default="high")
    p.add_argument("--notes", choices=["head", "none"], default="head",
                   help="use the repo notes file present at the PR head, or none")
    p.add_argument("--passes", type=int, default=1)
    p.add_argument("--min-votes", type=int, default=0, help="0 picks 1 for one pass, 2 otherwise")
    p.add_argument("--merge-model", help="default: claude-haiku-4-5-20251001, or --model with opencode")
    p.add_argument("--verify", action="store_true", help="check the merged findings before posting")
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--timeout-min", type=int, default=20)
    p.add_argument("--config", help="run directory name (default: model-effort-notes)")
    p.add_argument("--src-root", type=Path, default=Path.home() / "Code/personal")
    p.add_argument("--work-root", type=Path, default=WORK_ROOT)
    cfg = p.parse_args()
    if cfg.harness == "git-stk" and cfg.passes != 1:
        p.error("--harness git-stk reviews in one pass")
    cfg.merge_model = cfg.merge_model or (cfg.model if cfg.harness == "opencode" else "claude-haiku-4-5-20251001")
    key = model_key(cfg)
    if not key or key not in os.environ:
        sys.exit(f"{key or 'a known provider'} is required for {cfg.model}: replays run with an isolated HOME, "
                 "like CI.")
    name = cfg.config or (("git-stk-" if cfg.harness == "git-stk" else "")
                          + f"{cfg.model.replace('/', '_')}-{cfg.effort or 'unset'}-p{cfg.passes}-notes_{cfg.notes}"
                          + ("-verify" if cfg.verify else ""))

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
