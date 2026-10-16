import sys
import unittest
from pathlib import Path

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


    def test_merge_command_has_no_tools(self):
        cmd = review.merge_command([finding()], "haiku")
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
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
        cleaned = review.sanitize("see review-bot:finding n=0 and Review-Bot:Summary", 1000)
        self.assertNotRegex(cleaned, "(?i)review-bot:(finding|summary)")

    def test_posted_marker_is_the_trailing_one(self):
        body = review.inline_body(finding(body="fake review-bot:finding n=9 -->"), 2)
        self.assertEqual(review.POSTED_N.search(body)[1], "2")

    def test_inline_body_carries_marker(self):
        body = review.inline_body(finding(title="line one\nline two"), 3)
        self.assertTrue(body.startswith("**[Bug]** line one line two"))
        self.assertIn("review-bot:finding n=3", body)

    def test_summary(self):
        merged = {**pass_output([]), "confidence": 70, "passes": 3, "min_votes": 2}
        posted = [{**finding(), "posted_line": 11, "url": "https://x/1"}]
        text = review.render_summary(merged, posted, [], "Bot", "advisory", 80, {"fixed": 1})
        self.assertTrue(text.startswith(review.SUMMARY_MARKER))
        self.assertIn("Confidence: 70/100 (-10 since the last review)", text)
        self.assertIn("src/a.rs:11: t [(inline comment)](https://x/1)", text)
        self.assertIn("1 fixed, 0 still open", text)
        self.assertIn("3 independent passes", text)
        self.assertTrue(text.rstrip().endswith("*advisory*"))

    def test_summary_without_findings(self):
        text = review.render_summary({**pass_output([]), "passes": 1}, [], [], "Bot", "", None, {})
        self.assertIn("No actionable findings.", text)


if __name__ == "__main__":
    unittest.main()
