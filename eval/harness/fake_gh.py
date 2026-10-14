"""Stand-in for the `gh` CLI during a replay.

Answers the read-only PR commands the review prompt uses from the case file
and the local checkout. Anything else fails, so a replay can never reach
GitHub.
"""

import json
import os
import subprocess
import sys


def log(argv, status):
    path = os.environ.get("REPLAY_GH_LOG")
    if path:
        with open(path, "a") as f:
            f.write(json.dumps({"argv": argv, "status": status}) + "\n")


def fail(argv, msg):
    log(argv, "refused")
    print(f"gh (replay): {msg}", file=sys.stderr)
    sys.exit(1)


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def flag(args, name):
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            return args[i + 1]
    for a in args:
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


def pr_files(base, head):
    files = []
    for row in git("diff", "--numstat", f"{base}...{head}").splitlines():
        add, dele, path = row.split("\t", 2)
        files.append({
            "path": path,
            "additions": int(add) if add.isdigit() else 0,
            "deletions": int(dele) if dele.isdigit() else 0,
        })
    return files


def pr_view(case, args):
    pr = case["pr"]
    data = {
        "number": pr["number"] or 0,
        "title": pr["title"],
        "body": pr["body"],
        "state": "OPEN",
        "isDraft": False,
        "author": {"login": case["repo"].split("/")[0]},
        "baseRefName": "main",
        "headRefName": f"pr-{pr['number'] or 0}",
        "baseRefOid": pr["base_sha"],
        "headRefOid": pr["head_sha"],
        "labels": [],
        "comments": [],
        "reviews": [],
        "files": pr_files(pr["base_sha"], pr["head_sha"]),
        "url": f"https://github.com/{case['repo']}/pull/{pr['number'] or 0}",
    }
    fields = flag(args, "--json")
    if not fields:
        return f"{data['title']}\n\n{data['body']}\n"
    out = json.dumps({k: data.get(k) for k in fields.split(",")})
    jq = flag(args, "--jq") or flag(args, "-q")
    if jq:
        out = subprocess.run(["jq", "-r", jq], input=out, check=True,
                             capture_output=True, text=True).stdout
    return out + ("" if out.endswith("\n") else "\n")


def main():
    argv = sys.argv[1:]
    with open(os.environ["REPLAY_CASE"]) as f:
        case = json.load(f)
    base, head = case["pr"]["base_sha"], case["pr"]["head_sha"]

    if argv[:2] == ["pr", "view"]:
        out = pr_view(case, argv[2:])
    elif argv[:2] == ["pr", "diff"]:
        if "--name-only" in argv:
            out = git("diff", "--name-only", f"{base}...{head}")
        else:
            out = git("diff", f"{base}...{head}")
    elif argv[:2] == ["pr", "checks"]:
        out = "ci\tpass\t1m0s\t\n"
    else:
        fail(argv, "command not available in replay")
    log(argv, "ok")
    try:
        sys.stdout.write(out)
        sys.stdout.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


if __name__ == "__main__":
    main()
