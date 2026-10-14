"""Save review comments, issue comments, and reviews for merged PRs numbered >= MIN_PR.

usage: fetch_comments.py RAW_DIR OWNER/NAME MIN_PR
Writes <raw_dir>/<name>/comments/<number>.json; existing files are kept.
"""
import json
import subprocess
import sys
from pathlib import Path

ENDPOINTS = {
    "review_comments": "pulls/{n}/comments",
    "issue_comments": "issues/{n}/comments",
    "reviews": "pulls/{n}/reviews",
}
KEEP = ("id", "path", "line", "original_line", "commit_id", "original_commit_id",
        "body", "created_at", "in_reply_to_id", "state", "submitted_at", "html_url")


def get(slug, endpoint):
    out = subprocess.run(["gh", "api", "--paginate", "--slurp", f"repos/{slug}/{endpoint}?per_page=100"],
                         check=True, capture_output=True, text=True).stdout
    items = [item for page in json.loads(out) for item in page]
    return [{"user": (i.get("user") or {}).get("login"), **{k: i[k] for k in KEEP if k in i}}
            for i in items]


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    raw, slug, min_pr = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
    dest = raw / slug.split("/")[1]
    (dest / "comments").mkdir(parents=True, exist_ok=True)
    for pr in json.loads((dest / "prs.json").read_text()):
        path = dest / "comments" / f"{pr['number']}.json"
        if pr["number"] < min_pr or path.exists():
            continue
        data = {key: get(slug, ep.format(n=pr["number"])) for key, ep in ENDPOINTS.items()}
        path.write_text(json.dumps(data, indent=1) + "\n")
    print(f"{slug}: comments saved under {dest / 'comments'}")


if __name__ == "__main__":
    main()
