"""Save merged PR metadata for each repo slug to <raw_dir>/<name>/prs.json."""
import json
import subprocess
import sys
from pathlib import Path

QUERY = """
query($owner: String!, $name: String!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(first: 50, states: MERGED, after: $endCursor) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title body mergedAt baseRefOid headRefOid
        author { login }
        mergeCommit { oid }
        commits { totalCount }
      }
    }
  }
}
"""


def fetch(slug):
    owner, name = slug.split("/")
    out = subprocess.run(
        ["gh", "api", "graphql", "--paginate", "--slurp", "-f", f"query={QUERY}",
         "-F", f"owner={owner}", "-F", f"name={name}"],
        check=True, capture_output=True, text=True,
    ).stdout
    nodes = []
    for page in json.loads(out):
        nodes += page["data"]["repository"]["pullRequests"]["nodes"]
    prs = [{
        "number": pr["number"],
        "title": pr["title"],
        "body": pr["body"] or "",
        "author": (pr["author"] or {}).get("login"),
        "merged_at": pr["mergedAt"],
        "base_sha": pr["baseRefOid"],
        "head_sha": pr["headRefOid"],
        "merge_sha": (pr["mergeCommit"] or {}).get("oid"),
        "commits": pr["commits"]["totalCount"],
    } for pr in nodes]
    return sorted(prs, key=lambda p: p["number"])


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: fetch_prs.py RAW_DIR OWNER/NAME...")
    raw = Path(sys.argv[1])
    for slug in sys.argv[2:]:
        dest = raw / slug.split("/")[1]
        dest.mkdir(parents=True, exist_ok=True)
        prs = fetch(slug)
        (dest / "prs.json").write_text(json.dumps(prs, indent=1) + "\n")
        print(f"{slug}: {len(prs)} merged PRs")


if __name__ == "__main__":
    main()
