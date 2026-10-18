"""Task 2 of crew-review-nearby: crew numbers shown as C<N>, accepted as 15 or C15."""

import argparse
import unittest

from helpers import ReviewCase

from module_crew import protocol, refs, review, store


class RefsTest(unittest.TestCase):
    def test_fmt_and_parse(self):
        self.assertEqual(refs.fmt(15), "C15")
        for raw in ("15", "C15", "c15", " C15 "):
            self.assertEqual(refs.parse(raw), 15)
        for raw in ("#15", "D1", "0", "C"):
            with self.assertRaises(argparse.ArgumentTypeError):
                refs.parse(raw)


class OutwardTextTest(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        self.spec = review.add(self.db, self.spec_review("b"), "shop-b", 4001).number
        self.plan = review.add(self.db, self.plan_review("b"), "shop-b", 4002).number

    def test_messages_and_commits_use_c(self):
        res = review.approve(self.repo, [self.spec, self.plan], "批准")
        self.assertEqual(res.code, 0, res.lines)
        replies = [x for x in res.sends if x["kind"] == "user-reply"]
        reply = protocol.parse(replies[0]["path"].read_text(encoding="utf-8"))
        self.assertTrue(reply.fields["事项"].startswith(f"C{self.spec}"))
        notice = [x for x in res.sends if x["kind"] == "coordination-notice"][0]["path"].read_text(encoding="utf-8")
        self.assertIn(f"C{res.approval}", notice)
        self.assertTrue(protocol.parse(notice).ok)
        from helpers import git
        self.assertIn(f"C{res.approval}", git(self.repo, "log", "-1", "--format=%s"))
        self.assertNotIn(f"#{res.approval}", git(self.repo, "log", "-1", "--format=%s"))

    def test_cli_accepts_both_and_prints_c(self):
        out = self.run_cli("review", "batch", cwd=self.repo).stdout
        self.assertIn(f"C{self.spec} b 的 Spec", out)
        self.assertNotIn(f"#{self.spec} ", out)
        res = self.run_cli("review", "approve", f"C{self.spec}", str(self.plan), "--original", "批准", cwd=self.repo)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.run_cli("review", "answer", "#3", "--original", "x", cwd=self.repo).returncode, 2)

    def test_json_keeps_numbers_and_adds_ref(self):
        import json
        doc = json.loads(self.run_cli("review", "batch", "--json", cwd=self.repo).stdout)
        row = doc["items"][0]
        self.assertEqual((row["number"], row["ref"]), (self.spec, f"C{self.spec}"))


if __name__ == "__main__":
    unittest.main()


class WaitRefTest(unittest.TestCase):
    """crew-glossary-rename acceptance 3: wait records show as W<N>; W, C and bare numbers are all accepted."""

    def test_wait_prefix(self):
        from module_crew import refs
        self.assertEqual(refs.wait(25), "W25")
        self.assertEqual([refs.parse(v) for v in ("W25", "w25", "C25", "25")], [25, 25, 25, 25])
