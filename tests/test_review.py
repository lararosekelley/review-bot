import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import review  # noqa: E402

DIFF = """diff --git a/src/a.rs b/src/a.rs
index 1..2 100644
--- a/src/a.rs
+++ b/src/a.rs
@@ -10,4 +10,5 @@ fn a() {
 keep
-old
+new
+added
 keep
 keep
diff --git a/gone.rs b/gone.rs
--- a/gone.rs
+++ /dev/null
@@ -1,2 +0,0 @@
-x
-y
"""


def finding(path="src/a.rs", line=11, side="RIGHT", start=0, fid="1.0", pas=1, **kw):
    f = {"path": path, "line": line, "start_line": start, "side": side, "category": "Bug",
         "title": "t", "body": "b", "id": fid, "pass": pas}
    f.update(kw)
    return f


def pass_output(findings, confidence=80, prior=(), summary="s"):
    return {"summary": summary, "confidence": confidence, "findings": findings, "prior": list(prior),
            "notes": {"coverage": "", "ci": "", "praise": ""}}


class ParseDiff(unittest.TestCase):
    def test_sides(self):
        v = review.parse_diff(DIFF)
        self.assertEqual(v["src/a.rs"]["RIGHT"], {10, 11, 12, 13, 14})
        self.assertEqual(v["src/a.rs"]["LEFT"], {10, 11, 12, 13})
        self.assertEqual(v["gone.rs"]["LEFT"], {1, 2})
        self.assertEqual(v["gone.rs"]["RIGHT"], set())


class Anchor(unittest.TestCase):
    def setUp(self):
        self.valid = review.parse_diff(DIFF)

    def test_exact(self):
        self.assertEqual(review.anchor(finding(line=12), self.valid), (12, 0))

    def test_range(self):
        self.assertEqual(review.anchor(finding(line=12, start=11), self.valid), (12, 11))

    def test_moves_to_nearest_line(self):
        self.assertEqual(review.anchor(finding(line=16), self.valid), (14, 0))

    def test_too_far_or_unknown_file(self):
        self.assertIsNone(review.anchor(finding(line=40), self.valid))
        self.assertIsNone(review.anchor(finding(path="nope.rs"), self.valid))

    def test_left_side(self):
        self.assertEqual(review.anchor(finding(path="gone.rs", line=2, side="LEFT"), self.valid), (2, 0))


class Merge(unittest.TestCase):
    def test_positional_groups(self):
        fs = [finding(line=10, fid="1.0"), finding(line=12, fid="2.0", pas=2), finding(line=40, fid="2.1", pas=2)]
        groups = review.positional_groups(fs)
        self.assertEqual([g["ids"] for g in groups], [["1.0", "2.0"], ["2.1"]])

    def test_valid_groups(self):
        self.assertTrue(review.valid_groups([{"ids": ["a", "b"], "keep": "a"}], ["a", "b"]))
        self.assertFalse(review.valid_groups([{"ids": ["a"], "keep": "a"}], ["a", "b"]))
        self.assertFalse(review.valid_groups([{"ids": ["a", "b"], "keep": "c"}], ["a", "b"]))
        self.assertFalse(review.valid_groups([{"ids": ["a"], "keep": "a"}, {"ids": ["a", "b"], "keep": "b"}],
                                             ["a", "b"]))

    def test_vote_keeps_groups_from_enough_passes(self):
        p1 = pass_output([finding(fid="1.0", pas=1), finding(line=40, fid="1.1", pas=1)], confidence=70)
        p2 = pass_output([finding(fid="2.0", pas=2)], confidence=90)
        p3 = pass_output([], confidence=80, summary="median")
        groups = [{"ids": ["1.0", "2.0"], "keep": "2.0"}, {"ids": ["1.1"], "keep": "1.1"}]
        merged = review.combine([p1, p2, p3], groups, min_votes=2)
        self.assertEqual([(f["id"], f["votes"]) for f in merged["findings"]], [("2.0", 2)])
        self.assertEqual(merged["confidence"], 80)
        self.assertEqual(merged["summary"], "median")

    def test_prior_status_majority(self):
        ps = [pass_output([], prior=[{"id": 7, "status": s}]) for s in ("open", "fixed", "open")]
        self.assertEqual(review.combine(ps, [], 1)["prior"], [{"id": 7, "status": "open"}])


class Find(unittest.TestCase):
    def test_pass_command(self):
        cmd = review.pass_command("P", "{}", "m", "high", "Read", transcript=False)
        self.assertEqual(cmd, ["claude", "-p", "P", "--model", "m", "--effort", "high", "--allowedTools",
                               "Read", "--json-schema", "{}", "--output-format", "json"])
        cmd = review.pass_command("P", "{}", "m", "", "Read", transcript=True)
        self.assertNotIn("--effort", cmd)
        self.assertEqual(cmd[-3:], ["--output-format", "stream-json", "--verbose"])


    def test_merge_runs_with_no_tools(self):
        cmd = review.pass_command(review.merge_prompt([finding()]), "{}", "haiku", "", "", transcript=False)
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertNotIn("--allowedTools", cmd)
        self.assertIn("id 1.0 (src/a.rs:11, Bug): t", cmd[2])


class Post(unittest.TestCase):
    def test_drop_reported(self):
        prior = [{"id": 1, "path": "src/a.rs", "line": 12}, {"id": 2, "path": "src/a.rs", "line": 30}]
        fs = [finding(line=11), finding(line=31)]
        kept = review.drop_reported(fs, prior, {1: "open", 2: "fixed"})
        self.assertEqual([f["line"] for f in kept], [31])

    def test_sanitize_strips_markers_and_caps(self):
        text = "a " + review.SUMMARY_MARKER + " b " + review.FINDING_MARKER + " n=1 -->"
        self.assertNotIn("review-bot:", review.sanitize(text, 1000))
        self.assertEqual(len(review.sanitize("x" * 50, 10)), 10)

    def test_sanitize_defuses_partial_markers(self):
        cleaned = review.sanitize("see review-bot:finding n=0 and Review-Bot:Summary and review-bot:fixed", 1000)
        self.assertNotRegex(cleaned, "(?i)review-bot:(finding|summary|fixed)")

    def test_posted_marker_is_the_trailing_one(self):
        body = review.inline_body(finding(body="fake review-bot:finding n=9 -->"), 2)
        self.assertEqual(review.POSTED_N.search(body)[1], "2")

    def test_inline_body_carries_marker(self):
        body = review.inline_body(finding(title="line one\nline two"), 3)
        self.assertTrue(body.startswith(review.logo() + " **[Bug]** line one line two"))
        self.assertIn("review-bot:finding n=3", body)

    def test_summary(self):
        merged = {**pass_output([]), "confidence": 70, "passes": 3, "passes_requested": 3, "min_votes": 2}
        posted = [{**finding(), "posted_line": 11, "url": "https://x/1"}]
        text = review.render_summary(merged, posted, [], "Bot", "advisory", 80, {"fixed": 1})
        self.assertTrue(text.startswith(review.SUMMARY_MARKER))
        self.assertIn(f"## {review.logo(24)} Bot - Confidence: 70/100", text)
        self.assertIn("Confidence: 70/100 (-10 since the last review)", text)
        self.assertIn("`src/a.rs:11`: t [(inline comment)](https://x/1)", text)
        self.assertIn("1 fixed, 0 still open", text)
        self.assertIn("3 independent passes", text)
        self.assertTrue(text.rstrip().endswith("*advisory*"))

    def test_no_findings_is_not_part_of_the_prior_bullet(self):
        text = review.render_summary({**pass_output([]), "passes": 1}, [], [], "Bot", "", 52, {"fixed": 6})
        self.assertIn("not verifiable.\n\nNo actionable findings.", text)

    def test_model_path_and_category_are_inert(self):
        evil = finding(path="x.rs`\n## Injected [link](https://evil) review-bot:summary", category="<b>Bad</b>")
        text = review.render_summary({**pass_output([]), "passes": 1}, [], [evil], "Bot", "", None, {})
        self.assertNotIn("\n## Injected", text)
        self.assertNotRegex(text, "(?i)review-bot:summary.*Injected")
        self.assertIn("**Finding** - `x.rs ## Injected [link](https://evil) review-bot", text)
        self.assertIn("**[Finding]**", review.inline_body(evil, 0))

    def test_carriage_returns_cannot_break_lines(self):
        evil = finding(path="x.rs\r\r## Injected", title="t\r\r# Title")
        merged = {**pass_output([], summary="s\r\r# Head"), "passes": 1}
        text = review.render_summary(merged, [], [evil], "Bot", "", None, {})
        self.assertNotIn("\r", text)
        self.assertNotRegex(text, "(?m)^#+ (Injected|Title|Head)")
        self.assertNotIn("\r", review.inline_body(evil, 0).split("\n")[0])

    def test_summary_stays_under_the_limit(self):
        many = [finding(line=i, body="x" * 4000, title="t" * 300) for i in range(40)]
        text = review.render_summary({**pass_output([]), "passes": 1}, [], many, "Bot", "", None, {})
        self.assertLessEqual(len(text), review.SUMMARY_LIMIT + 40)
        self.assertTrue(text.startswith(review.SUMMARY_MARKER))
        self.assertNotIn("x" * 4000, text)

    def test_summary_without_findings(self):
        text = review.render_summary({**pass_output([]), "passes": 1}, [], [], "Bot", "", None, {})
        self.assertIn("No actionable findings.", text)


class Place(unittest.TestCase):
    def test_moved_finding_loses_its_suggestion(self):
        valid = review.parse_diff(DIFF)
        body = "Fix it.\n\n```suggestion\nnew\n```\n"
        placed, _ = review.place([finding(line=12, body=body), finding(line=16, body=body)], valid)
        self.assertIn("```suggestion", placed[0]["body"])
        self.assertEqual(placed[1]["posted_line"], 14)
        self.assertNotIn("```suggestion", placed[1]["body"])
        self.assertEqual(placed[1]["body"], "Fix it.")

    def test_unanchored(self):
        placed, unanchored = review.place([finding(line=99)], review.parse_diff(DIFF))
        self.assertEqual((placed, [f["line"] for f in unanchored]), ([], [99]))


class Redact(unittest.TestCase):
    def test_secrets_never_reach_posted_text(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-secret-value", "GH_TOKEN": "ghs_tokenvalue"}):
            text = review.sanitize("key sk-ant-secret-value and ghs_tokenvalue", 1000)
            body = review.inline_body(finding(body="leak: sk-ant-secret-value"), 0)
        self.assertEqual(text, "key [redacted] and [redacted]")
        self.assertNotIn("sk-ant-secret-value", body)


class PostInline(unittest.TestCase):
    ARGS = SimpleNamespace(repo="o/r", pr="5", bot_name="Bot")

    def placed(self):
        return [{**finding(), "posted_line": 11, "posted_start": 0}, {**finding(line=12), "posted_line": 12, "posted_start": 0}]

    def test_listing_failure_does_not_repost(self):
        calls = []

        def gh_json(*args, payload=None):
            calls.append(args[2])
            return {"id": 1, "html_url": "https://review"}

        def gh_pages(path):
            raise RuntimeError("listing failed")

        with mock.patch.object(review, "gh_json", gh_json), mock.patch.object(review, "gh_pages", gh_pages):
            unanchored = []
            posted = review.post_inline(self.ARGS, "abc1234", self.placed(), unanchored)
        self.assertEqual(calls, ["POST"])
        self.assertEqual([p["url"] for p in posted], ["https://review", "https://review"])
        self.assertEqual(unanchored, [])

    def test_rejected_batch_falls_back_to_single_comments(self):
        def gh_json(*args, payload=None):
            if args[3].endswith("/reviews"):
                raise RuntimeError("422")
            if payload["line"] == 12:
                raise RuntimeError("line not in diff")
            return {"html_url": f"https://c/{payload['line']}"}

        with mock.patch.object(review, "gh_json", gh_json):
            unanchored = []
            posted = review.post_inline(self.ARGS, "abc1234", self.placed(), unanchored)
        self.assertEqual([p["url"] for p in posted], ["https://c/11"])
        self.assertEqual([f["line"] for f in unanchored], [12])


class FailedPasses(unittest.TestCase):
    def test_summary_says_passes_failed(self):
        merged = {**pass_output([]), "passes": 1, "passes_requested": 3, "min_votes": 1, "votes_lowered": True}
        text = review.render_summary(merged, [], [], "Bot", "", None, {})
        self.assertIn("2 of 3 review passes failed", text)
        self.assertIn("vote threshold was lowered", text)

    def test_summary_counts_dropped_findings(self):
        merged = {**pass_output([]), "dropped": [{"title": "t", "path": "a", "line": 1, "reason": "r"}] * 2}
        self.assertIn("verification pass dropped 2 findings", review.render_summary(merged, [], [], "Bot", "", None, {}))
        self.assertNotIn("verification", review.render_summary(pass_output([]), [], [], "Bot", "", None, {}))


def thread(tid, resolved=False, author="Bot", body=None, cid=1, last=None):
    body = body if body is not None else "**[Bug]** Stale photo stays painted.\n\nwhy\n\n" + review.FINDING_MARKER + " n=0 -->"
    first = {"databaseId": cid, "body": body, "path": "src/a.rs", "line": None, "originalLine": 11,
             "author": {"__typename": author}}
    return {"id": tid, "isResolved": resolved, "comments": {"nodes": [first]},
            "last": {"nodes": [last or {"body": body, "author": {"__typename": author}}]}}


class Prior(unittest.TestCase):
    def test_only_open_bot_findings(self):
        threads = [thread("T1", cid=1), thread("T2", resolved=True, cid=2), thread("T3", author="User", cid=3),
                   thread("T4", body="**[Bug]** no marker", cid=4)]
        prior = review.prior_from_threads(threads)
        self.assertEqual(prior, [{"id": 1, "thread_id": "T1", "path": "src/a.rs", "line": 11,
                                  "title": "Stale photo stays painted."}])

    def test_title_drops_the_logo(self):
        body = review.inline_body(finding(title="Stale photo stays painted."), 0)
        self.assertEqual(review.prior_from_threads([thread("T1", body=body)])[0]["title"],
                         "Stale photo stays painted.")

    def test_fixed_reply_closes_until_someone_replies(self):
        fixed = {"body": "Fixed as of abc1234.\n\n" + review.FIXED_MARKER, "author": {"__typename": "Bot"}}
        human = {"body": "still broken", "author": {"__typename": "User"}}
        self.assertEqual(review.prior_from_threads([thread("T1", last=fixed)]), [])
        self.assertEqual(len(review.prior_from_threads([thread("T1", last=human)])), 1)


class Rereview(unittest.TestCase):
    def test_note(self):
        note = review.rereview_note("abcdef123", 85, 70, {"fixed": 1}, 0, "https://s")
        self.assertEqual(note, review.logo() + " Re-reviewed abcdef1: Confidence: 85/100 (+15 since the last "
                               "review); 1 fixed, 0 still open, 0 not verifiable; no new findings. [Summary](https://s)")
        note = review.rereview_note("abc1234", 60, None, {}, 2, "u")
        self.assertIn("Confidence: 60/100; 2 new finding(s) listed in the summary", note)

    def test_react_swaps_the_eyes_reaction(self):
        calls = []

        def gh(*args, payload=None):
            calls.append(("gh",) + args[1:3])
            return ""

        def gh_json(*args, payload=None):
            calls.append(("json", args[2], payload["content"]))
            return {"id": 77}

        with tempfile.TemporaryDirectory() as d, mock.patch.object(review, "gh", gh), \
                mock.patch.object(review, "gh_json", gh_json):
            ack = Path(d) / "ack.json"
            review.react("o/r", 5, "eyes", str(ack))
            self.assertTrue(ack.exists())
            review.react("o/r", 5, "+1", str(ack))
            self.assertFalse(ack.exists())
        self.assertEqual(calls, [("json", "POST", "eyes"), ("gh", "-X", "DELETE"), ("json", "POST", "+1")])

    def test_react_failure_does_not_raise(self):
        def gh_json(*args, payload=None):
            raise RuntimeError("forbidden")

        with mock.patch.object(review, "gh_json", gh_json):
            review.react("o/r", 5, "eyes", None)

    def test_close_fixed_replies_and_resolves_only_fixed(self):
        calls = []

        def gh_json(*args, payload=None):
            calls.append(args[1] if args[1] == "graphql" else payload["body"])
            return {}

        prior = [{"id": 1, "thread_id": "T1"}, {"id": 2, "thread_id": "T2"}]
        with mock.patch.object(review, "gh_json", gh_json):
            review.close_fixed(SimpleNamespace(repo="o/r", pr="5"), "abcdef123", prior, {1: "fixed", 2: "open"})
        self.assertEqual(calls, [review.logo() + " Fixed as of abcdef1.\n\n" + review.FIXED_MARKER, "graphql"])

    def test_close_fixed_survives_a_refused_resolve(self):
        def gh_json(*args, payload=None):
            if args[1] == "graphql":
                raise RuntimeError("Resource not accessible by integration")
            return {}

        with mock.patch.object(review, "gh_json", gh_json):
            review.close_fixed(SimpleNamespace(repo="o/r", pr="5"), "abc1234", [{"id": 1, "thread_id": "T1"}],
                               {1: "fixed"})


RESULT = {"total_cost_usd": 0.1, "usage": {"input_tokens": 10, "cache_creation_input_tokens": 1000,
                                           "cache_read_input_tokens": 9000, "output_tokens": 500}}


class Usage(unittest.TestCase):
    def test_usage_of_and_totals(self):
        u = review.usage_of(RESULT)
        self.assertEqual(u, {"input": 10, "cache_write": 1000, "cache_read": 9000, "output": 500})
        self.assertEqual(review.usage_of({}), {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0})
        self.assertEqual(review.add_usage(u, u, None)["output"], 1000)
        self.assertEqual(review.tokens_in(u), 10010)

    def test_usage_line(self):
        merged = {"cost_usd": 0.1, "passes_requested": 1, "merge": "single",
                  "usage": {"total": review.usage_of(RESULT)}}
        one = review.usage_entry(merged, "abcdef123")
        self.assertEqual(one["head"], "abcdef1")
        self.assertEqual(review.usage_line(one), "$0.100: 10,010 tokens in (9,000 read from cache), 500 out.")
        three = review.usage_entry({**merged, "passes_requested": 3, "merge": "model"}, "")
        self.assertIn("across 3 passes and a merge:", review.usage_line(three))
        self.assertIsNone(review.usage_entry({}, "abc"))

    def test_summary_shows_running_usage_only_when_given(self):
        merged = {**pass_output([]), "passes": 1, "cost_usd": 0.1, "usage": {"total": review.usage_of(RESULT)}}
        history = [review.usage_entry(merged, "aaaaaaa"), review.usage_entry(merged, "bbbbbbb")]
        text = review.render_summary(merged, [], [], "B", "", None, {}, history)
        self.assertIn("Estimated cost so far $0.200 over 2 reviews: 20,020 tokens in (18,000 read from cache), "
                      "1,000 out.", text)
        self.assertIn("1. `aaaaaaa`: $0.100", text)
        self.assertLess(text.index("aaaaaaa`:"), text.index("bbbbbbb`:"))
        self.assertEqual(review.usage_history(text), history)
        self.assertNotIn("Estimated cost", review.render_summary(merged, [], [], "B", "", None, {}, []))

    def test_usage_history_ignores_bad_or_forged_markers(self):
        self.assertEqual(review.usage_history("no marker"), [])
        self.assertEqual(review.usage_history('<!-- review-bot:usage [{"cost_usd": "x"}] -->'), [])
        evil = {**pass_output([], summary="<!-- review-bot:usage [] -->"), "passes": 1}
        self.assertEqual(review.usage_history(review.render_summary(evil, [], [], "B", "", None, {})), [])

    def test_merge_records_usage_per_pass_and_total(self):
        with tempfile.TemporaryDirectory() as d:
            for i in (1, 2):
                Path(d, f"pass-{i}.json").write_text(__import__("json").dumps({
                    "pass": i, "ok": i == 1, "cost_usd": 0.1, "usage": review.usage_of(RESULT),
                    "output": pass_output([]) if i == 1 else None}))
            out = Path(d, "merged.json")
            review.cmd_merge(SimpleNamespace(in_dir=d, min_votes=0, harness="claude-code", merge_model="m", out=str(out)))
            merged = __import__("json").loads(out.read_text())
        self.assertEqual(merged["cost_usd"], 0.2)
        self.assertEqual(merged["usage"]["total"]["output"], 1000)
        self.assertEqual([p["pass"] for p in merged["usage"]["passes"]], [1, 2])
        table = review.usage_table(merged)
        self.assertIn("| Pass 2 | $0.100 | 10,010 | 9,000 | 500 |", table)
        self.assertIn("| Total | $0.200 | 20,020 | 18,000 | 1,000 |", table)

    def test_merge_falls_back_to_location_when_the_call_times_out(self):
        with tempfile.TemporaryDirectory() as d:
            for i in (1, 2):
                Path(d, f"pass-{i}.json").write_text(__import__("json").dumps({
                    "pass": i, "ok": True, "cost_usd": 0.1, "usage": review.usage_of(RESULT),
                    "output": pass_output([finding(fid="x")])}))
            out = Path(d, "merged.json")
            with mock.patch.object(review.subprocess, "run",
                                   side_effect=review.subprocess.TimeoutExpired("claude", 60)) as run:
                review.cmd_merge(SimpleNamespace(in_dir=d, min_votes=0, harness="claude-code", merge_model="m", out=str(out)))
            merged = __import__("json").loads(out.read_text())
        self.assertEqual(run.call_args.kwargs["env"]["MAX_THINKING_TOKENS"], "0")
        self.assertEqual(merged["merge"], "positional")
        self.assertEqual([f["votes"] for f in merged["findings"]], [2])

    def test_dry_run_records_the_reported_line_beside_the_posted_one(self):
        with tempfile.TemporaryDirectory() as d:
            merged = Path(d, "merged.json")
            merged.write_text(__import__("json").dumps(
                {**pass_output([finding(line=16)]), "passes": 1, "passes_requested": 1, "min_votes": 1}))
            out = Path(d, "findings.jsonl")
            a = SimpleNamespace(merged=str(merged), prior=None, dry_run=str(out), show_usage="false",
                                bot_name="B", footer="", pr=1, repo="o/r")
            with mock.patch.object(review, "pr_diff", return_value=DIFF):
                review.cmd_post(a)
            row = __import__("json").loads(out.read_text().splitlines()[0])
        self.assertEqual((row["line"], row["reportedLine"]), (14, 16))



class Verify(unittest.TestCase):
    def test_apply_verdicts_keeps_findings_without_a_verdict(self):
        fs = [finding(line=11, title="a"), finding(line=12, title="b"), finding(line=13, title="c")]
        kept, dropped = review.apply_verdicts(fs, [{"id": 1, "keep": False, "reason": "intended"},
                                                   {"id": 0, "keep": True, "reason": "holds"}])
        self.assertEqual([f["title"] for f in kept], ["a", "c"])
        self.assertEqual(dropped, [{"title": "b", "path": "src/a.rs", "line": 12, "reason": "intended"}])

    def write_merged(self, d):
        merged = Path(d, "merged.json")
        merged.write_text(__import__("json").dumps({
            **pass_output([finding(line=11), finding(line=12)]), "cost_usd": 0.1,
            "notes": {"coverage": "needs a test", "ci": "", "praise": ""},
            "usage": {"total": review.usage_of(RESULT)}}))
        return merged

    def test_verify_drops_and_counts_its_cost(self):
        out = {"total_cost_usd": 0.05, "usage": RESULT["usage"],
               "structured_output": {"verdicts": [{"id": 0, "keep": False, "reason": "intended\n::error::x"}],
                                     "confidence": 90, "keep_coverage": False}}
        with tempfile.TemporaryDirectory() as d:
            merged = self.write_merged(d)
            proc = SimpleNamespace(stdout=__import__("json").dumps(out), stderr="", returncode=0)
            with mock.patch.object(review.subprocess, "run", return_value=proc), \
                    mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                review.cmd_verify(SimpleNamespace(merged=str(merged), harness="claude-code", model="m", effort="", tools="Read"))
            result = __import__("json").loads(merged.read_text())
        self.assertEqual([f["line"] for f in result["findings"]], [12])
        self.assertEqual(result["dropped"][0]["reason"], "intended\n::error::x")
        self.assertNotIn("\n::error::", stdout.getvalue())
        self.assertEqual(result["cost_usd"], 0.15)
        self.assertEqual(result["usage"]["total"]["output"], 1000)
        self.assertEqual(result["confidence"], 90)
        self.assertEqual(result["notes"]["coverage"], "")

    def test_verify_prompt_carries_the_shared_rules(self):
        with tempfile.TemporaryDirectory() as d:
            merged = self.write_merged(d)
            with mock.patch.object(review.subprocess, "run",
                                   side_effect=review.subprocess.TimeoutExpired("claude", 600)) as run:
                review.cmd_verify(SimpleNamespace(merged=str(merged), harness="claude-code", model="m", effort="", tools="Read"))
            prompt = run.call_args.args[0][2]
        self.assertIn(review.VERIFY_RULES.read_text().strip(), prompt)
        self.assertIn("Coverage note: needs a test", prompt)

    def test_verify_failure_posts_every_finding(self):
        with tempfile.TemporaryDirectory() as d:
            merged = self.write_merged(d)
            before = merged.read_text()
            with mock.patch.object(review.subprocess, "run",
                                   side_effect=review.subprocess.TimeoutExpired("claude", 600)):
                review.cmd_verify(SimpleNamespace(merged=str(merged), harness="claude-code", model="m", effort="", tools="Read"))
            self.assertEqual(merged.read_text(), before)

    def test_malformed_check_posts_every_finding(self):
        json = __import__("json")
        verdict = {"id": 0, "keep": False, "reason": "intended"}
        for stdout in ["", "not json", json.dumps({"structured_output": [verdict]}),
                       json.dumps({"result": json.dumps({"verdicts": [{"id": 0}], "confidence": 90,
                                                         "keep_coverage": True})}),
                       json.dumps({"structured_output": {"verdicts": [verdict]}})]:
            with self.subTest(stdout=stdout), tempfile.TemporaryDirectory() as d:
                merged = self.write_merged(d)
                before = merged.read_text()
                proc = SimpleNamespace(stdout=stdout, stderr="", returncode=0)
                with mock.patch.object(review.subprocess, "run", return_value=proc):
                    review.cmd_verify(SimpleNamespace(merged=str(merged), harness="claude-code", model="m", effort="", tools="Read"))
                self.assertEqual(merged.read_text(), before)


class Reply(unittest.TestCase):
    THREAD = [
        {"id": 3, "in_reply_to_id": 1, "created_at": "2026-01-03", "user": {"login": "dev", "type": "User"},
         "body": "@bot why?"},
        {"id": 1, "created_at": "2026-01-01", "user": {"login": "bot", "type": "Bot"}, "body": "finding",
         "path": "src/a.rs", "line": 11, "diff_hunk": "@@ -1 +1 @@\n+x"},
        {"id": 2, "created_at": "2026-01-02", "user": {"login": "x", "type": "User"}, "body": "other thread"},
    ]

    def test_thread_of_keeps_the_thread_in_order(self):
        self.assertEqual([c["id"] for c in review.thread_of(self.THREAD, 1)], [1, 3])

    def test_thread_section_marks_the_asker_and_fences_bodies(self):
        text = review.thread_section(review.thread_of(self.THREAD, 1), 3)
        self.assertIn("`src/a.rs:11`", text)
        self.assertIn("### @bot (bot)\n", text)
        self.assertIn("### @dev (asking)", text)

    def test_fence_outlasts_tildes_in_the_text(self):
        self.assertTrue(review.fenced("a\n~~~~~~\nb").startswith("~~~~~~~text\n"))

    def test_reply_body(self):
        body = review.reply_body("hi <!-- review-bot:summary -->", "footer")
        self.assertNotIn("review-bot:summary", body)
        self.assertTrue(body.endswith("---\n\n*footer*"))
        self.assertNotIn("---", review.reply_body("hi", " "))

    def run_reply(self, stdout, kind="review"):
        posts, reacts = [], []

        def gh_json(*args, payload=None):
            if "POST" in args:
                posts.append((args[3], payload))
                return {}
            return self.THREAD[0] if kind == "review" else {"id": 9, "body": "@bot hi", "user": {"login": "dev"}}

        with tempfile.TemporaryDirectory() as d:
            prompt = Path(d, "p.md")
            prompt.write_text("rules")
            a = SimpleNamespace(prompt_file=str(prompt), repo="o/r", pr="5", comment_id="3", kind=kind, harness="claude-code", model="m",
                                effort="", tools="Read", footer="", ack_file=None)
            proc = SimpleNamespace(stdout=stdout, stderr="", returncode=0)
            with mock.patch.object(review, "gh_json", gh_json), \
                    mock.patch.object(review, "gh_pages", return_value=self.THREAD), \
                    mock.patch.object(review, "react", lambda *x: reacts.append(x)), \
                    mock.patch.object(review.subprocess, "run", return_value=proc) as run, \
                    mock.patch("sys.stdout", new_callable=io.StringIO):
                review.cmd_reply(a)
        return posts, reacts, run.call_args[0][0]

    def test_reply_in_a_review_thread(self):
        out = __import__("json").dumps({"structured_output": {"body": "Because."}, "total_cost_usd": 0.01})
        posts, reacts, cmd = self.run_reply(out)
        self.assertEqual(posts[0][0], "repos/o/r/pulls/5/comments/1/replies")
        self.assertIn("Because.", posts[0][1]["body"])
        self.assertEqual(reacts, [("o/r", "3", "+1", None, "review")])
        self.assertIn("### @dev (asking)", cmd[2])

    def test_reply_to_a_pr_comment(self):
        out = __import__("json").dumps({"structured_output": {"body": "Sure."}})
        posts, _, _ = self.run_reply(out, kind="issue")
        self.assertEqual(posts[0][0], "repos/o/r/issues/5/comments")

    def test_unusable_reply_posts_nothing(self):
        for stdout in ["", "not json", __import__("json").dumps({"structured_output": {"body": " "}})]:
            with self.subTest(stdout=stdout), self.assertRaises(SystemExit):
                self.run_reply(stdout)

    def test_react_on_a_review_comment(self):
        paths = []
        with mock.patch.object(review, "gh_json", lambda *a, payload=None: paths.append(a[3]) or {"id": 1}):
            review.react("o/r", 5, "eyes", None, "review")
        self.assertEqual(paths, ["repos/o/r/pulls/comments/5/reactions"])


def oc_events(text, cost=0.01, session="ses_1", error=None):
    json = __import__("json")
    rows = [{"type": "step_start", "sessionID": session, "part": {}}]
    if error:
        rows.append({"type": "error", "sessionID": session, "error": {"message": error}})
    else:
        rows += [{"type": "text", "sessionID": session, "part": {"text": text}},
                 {"type": "step_finish", "sessionID": session, "part": {
                     "cost": cost, "tokens": {"input": 100, "output": 10, "reasoning": 5,
                                              "cache": {"read": 50, "write": 7}}}}]
    return "\n".join(json.dumps(r) for r in rows)


class Opencode(unittest.TestCase):
    SCHEMA = {"type": "object", "additionalProperties": False, "required": ["body"],
              "properties": {"body": {"type": "string"}, "n": {"type": "integer", "minimum": 0}}}

    def test_config_denies_by_default_and_maps_the_allowlist(self):
        config, ignored = review.opencode_config("Read,Glob,Grep,Bash(git diff:*),WebFetch")
        perm = config["permission"]
        self.assertEqual(perm["*"], "deny")
        self.assertEqual([perm[t] for t in ("read", "glob", "list", "grep")], ["allow"] * 4)
        self.assertEqual(perm["bash"], {"*": "deny", "git diff": "allow", "git diff *": "allow"})
        self.assertEqual(ignored, ["WebFetch"])
        self.assertNotIn("bash", review.opencode_config("Read")[0]["permission"])

    def test_check_schema(self):
        review.check_schema({"body": "x", "n": 2}, self.SCHEMA)
        for bad in [{"n": 1}, {"body": 1}, {"body": "x", "extra": 1}, {"body": "x", "n": -1},
                    {"body": "x", "n": True}, []]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                review.check_schema(bad, self.SCHEMA)

    def test_json_reply_ignores_fences_and_prose(self):
        self.assertEqual(review.json_reply('Here:\n```json\n{"body": "x"}\n```', self.SCHEMA), {"body": "x"})
        with self.assertRaises(ValueError):
            review.json_reply("no json here", self.SCHEMA)

    def test_events_sum_cost_and_tokens(self):
        run = review.opencode_events(oc_events('{"body": "x"}') + "\n" + oc_events('{"body": "y"}'))
        self.assertEqual(run["text"], '{"body": "y"}')
        self.assertAlmostEqual(run["cost_usd"], 0.02)
        self.assertEqual(run["usage"], {"input": 200, "output": 30, "cache_read": 100, "cache_write": 14})
        self.assertEqual(run["num_turns"], 2)

    def run_opencode(self, outputs, effort="high"):
        procs = [SimpleNamespace(stdout=o, stderr="", returncode=0) for o in outputs]
        with mock.patch.object(review.subprocess, "run", side_effect=procs) as run, \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            out = review.run_model("opencode", "P", __import__("json").dumps(self.SCHEMA), "openai/m", effort,
                                   "Read", timeout=5)
        return out, [c.args[0] for c in run.call_args_list], [c.kwargs["env"] for c in run.call_args_list]

    def test_run_ignores_repo_config_and_isolates_home(self):
        out, cmds, envs = self.run_opencode([oc_events('{"body": "ok"}')])
        self.assertEqual(out["output"], {"body": "ok"})
        self.assertEqual(cmds[0][:6], ["opencode", "run", "--standalone", "--format", "json", "-m"])
        self.assertEqual(cmds[0][6], "openai/m#high")
        self.assertIn("Output format", cmds[0][-1])
        self.assertEqual(envs[0]["OPENCODE_DISABLE_PROJECT_CONFIG"], "1")
        home = str(Path(envs[0]["OPENCODE_CONFIG"]).parent)
        self.assertTrue(all(envs[0][f"XDG_{d}_HOME"].startswith(home) for d in ("CONFIG", "DATA", "STATE")))

    def test_one_retry_in_the_same_session(self):
        out, cmds, _ = self.run_opencode([oc_events("not json"), oc_events('{"body": "ok"}', cost=0.02)])
        self.assertEqual(out["output"], {"body": "ok"})
        self.assertEqual(cmds[1][cmds[1].index("-s") + 1], "ses_1")
        self.assertAlmostEqual(out["cost_usd"], 0.03)
        with self.assertRaises(review.Unusable):
            self.run_opencode([oc_events("not json"), oc_events("still not")])

    def test_unknown_variant_falls_back_to_the_default(self):
        out, cmds, _ = self.run_opencode([oc_events("", error="Variant unavailable for openai/m: high"),
                                          oc_events('{"body": "ok"}')])
        self.assertEqual(cmds[1][6], "openai/m")
        self.assertEqual(out["output"], {"body": "ok"})

    def test_provider_error_is_unusable(self):
        with self.assertRaises(review.Unusable):
            self.run_opencode([oc_events("", error="invalid api key")], effort="")


if __name__ == "__main__":
    unittest.main()
