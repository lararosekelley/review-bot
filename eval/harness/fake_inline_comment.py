"""Stdio MCP server standing in for claude-code-action's github_inline_comment.

Same tool name and schema. Instead of posting, each call is appended to
$REPLAY_FINDINGS. Lines outside the PR diff are rejected the way GitHub
rejects them, and calls without confirmed=true are buffered, as in the action.
"""

import json
import os
import re
import subprocess
import sys

TOOL = {
    "name": "create_inline_comment",
    "description": "Create an inline comment on a specific line or lines in a PR file",
    "inputSchema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "The file path to comment on (e.g., 'src/index.js')"},
            "body": {"type": "string", "description": (
                "The comment text (supports markdown and GitHub code suggestion blocks). "
                "For code suggestions, use: ```suggestion\\nreplacement code\\n```. "
                "IMPORTANT: The suggestion block will REPLACE the ENTIRE line range (single line or startLine to line). "
                "Ensure the replacement is syntactically complete and valid - it must work as a drop-in replacement for the selected lines.")},
            "line": {"type": "number", "minimum": 0, "description": "Line number for single-line comments (required if startLine is not provided)"},
            "startLine": {"type": "number", "minimum": 0, "description": "Start line for multi-line comments (use with line parameter for the end line)"},
            "side": {"type": "string", "enum": ["LEFT", "RIGHT"], "default": "RIGHT", "description": "Side of the diff to comment on: LEFT (old code) or RIGHT (new code)"},
            "commit_id": {"type": "string", "description": "Specific commit SHA to comment on (defaults to latest commit)"},
            "confirmed": {"type": "boolean", "description": (
                "Set true to post immediately. When omitted, the call is buffered and classified after the "
                "session completes - real review comments post, test/probe comments are dropped. Set false to "
                "buffer and never post. Only set true when posting final review comments.")},
        },
        "required": ["path", "body"],
    },
}

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def diff_lines(base, head):
    """Map path to the line numbers a review comment may target, per side."""
    out = subprocess.run(["git", "diff", "-U3", f"{base}...{head}"],
                         check=True, capture_output=True, text=True).stdout
    lines, old, target, in_hunk = {}, None, None, False
    o = n = 0
    for row in out.splitlines():
        if row.startswith("diff --git "):
            in_hunk = False
        elif not in_hunk and row.startswith("--- "):
            old = None if row == "--- /dev/null" else row[6:]
        elif not in_hunk and row.startswith("+++ "):
            new = None if row == "+++ /dev/null" else row[6:]
            target = lines.setdefault(new or old, {"LEFT": set(), "RIGHT": set()})
        elif m := HUNK.match(row):
            o, n, in_hunk = int(m[1]), int(m[3]), True
        elif in_hunk and row[:1] == " ":
            target["LEFT"].add(o)
            target["RIGHT"].add(n)
            o, n = o + 1, n + 1
        elif in_hunk and row[:1] == "+":
            target["RIGHT"].add(n)
            n += 1
        elif in_hunk and row[:1] == "-":
            target["LEFT"].add(o)
            o += 1
    return lines


def record(entry):
    with open(os.environ["REPLAY_FINDINGS"], "a") as f:
        f.write(json.dumps(entry) + "\n")


def call(args, valid):
    path, side = args.get("path"), args.get("side", "RIGHT")
    line, start = args.get("line"), args.get("startLine")
    entry = {k: args.get(k) for k in ("path", "line", "startLine", "body", "confirmed")}
    entry["side"] = side
    if not line and not start:
        entry["status"] = "rejected"
        record(entry)
        return True, "Either 'line' for single-line comments or both 'startLine' and 'line' for multi-line comments must be provided"
    targets = [x for x in (start, line) if x]
    if path not in valid or any(int(t) not in valid[path][side] for t in targets):
        entry["status"] = "rejected"
        record(entry)
        return True, "Validation Failed: pull_request_review_thread.line must be part of the diff"
    if args.get("confirmed") is not True:
        entry["status"] = "buffered"
        record(entry)
        return False, json.dumps({"success": True, "buffered": True, "message": (
            "Comment buffered. It will be classified and posted after this session completes "
            "(real review comments post, test/probe comments are dropped). Set confirmed=true to "
            "post immediately. If you are testing whether this tool works: it works - no need to test further.")})
    entry["status"] = "posted"
    record(entry)
    return False, json.dumps({"success": True, "path": path, "line": line or start})


def main():
    with open(os.environ["REPLAY_CASE"]) as f:
        pr = json.load(f)["pr"]
    valid = diff_lines(pr["base_sha"], pr["head_sha"])
    for raw in sys.stdin:
        if not raw.strip():
            continue
        msg = json.loads(raw)
        method, mid = msg.get("method"), msg.get("id")
        if mid is None:
            continue
        if method == "initialize":
            result = {
                "protocolVersion": msg["params"].get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "GitHub Inline Comment Server", "version": "0.0.1"},
            }
        elif method == "tools/list":
            result = {"tools": [TOOL]}
        elif method == "tools/call" and msg["params"]["name"] == TOOL["name"]:
            is_error, text = call(msg["params"].get("arguments", {}), valid)
            result = {"content": [{"type": "text", "text": text}], "isError": is_error}
        elif method == "ping":
            result = {}
        else:
            reply = {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"unknown method {method}"}}
            print(json.dumps(reply), flush=True)
            continue
        print(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}), flush=True)


if __name__ == "__main__":
    main()
