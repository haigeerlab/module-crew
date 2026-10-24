import unittest

from helpers import MergeCase, git
from test_changes import request

from module_crew import changes, merge, review, store


class ConfigSetPrefixTest(MergeCase):
    """S23 (T78): a started project changes its commit prefix with the user's words, without start prepare."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        self.words = self.tmp / "original.txt"
        self.words.write_text("提交前缀改成 feat(crew): ", encoding="utf-8")

    def subjects(self, since):
        return git(self.repo, "log", "--format=%s", f"{since}..HEAD").strip().splitlines()

    def test_set_prefix_used_by_approve_land_and_merge(self):
        out = self.run_cli("config", "set", "--commit-prefix", "feat(crew): ", "--original-file", str(self.words),
                           cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(store.get(self.db, "config", "main")["commitPrefix"], "feat(crew): ")
        before = git(self.repo, "rev-parse", "HEAD").strip()
        s = review.add(self.db, self.spec_review("c"), "shop-c", 5001).number
        self.assertEqual(review.approve(self.repo, [s], "批准").code, 0)
        n = changes.add(self.db, request(["a.json"]), "shop-b", 5003).number
        (self.repo / "a.json").write_text("{}\n", encoding="utf-8")
        self.assertEqual(changes.land(self.repo, n).code, 0)
        self.approve_final("b", 5004)
        res = merge.run(self.repo, check_command="python3 -c pass")
        self.assertEqual(res.code, 0, res.lines)
        subjects = self.subjects(before)
        self.assertGreaterEqual(len(subjects), 3)
        for s in subjects:
            if not s.startswith("Merge") and not s.startswith("b: "):
                self.assertTrue(s.startswith("feat(crew): "), s)
        self.assertTrue(any(s.startswith("feat(crew): 合并批准事项 C") for s in subjects), subjects)

    def test_empty_prefix(self):
        out = self.run_cli("config", "set", "--commit-prefix", "", "--original", "不要前缀", cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(store.get(self.db, "config", "main")["commitPrefix"], "")
        s = review.add(self.db, self.spec_review("b"), "shop-b", 5001).number
        self.assertEqual(review.approve(self.repo, [s], "批准").code, 0)
        self.assertTrue(git(self.repo, "log", "-1", "--format=%s").startswith("用户批准事项 C"))

    def test_refused_without_original(self):
        cfg = store.get(self.db, "config", "main")
        out = self.run_cli("config", "set", "--commit-prefix", "feat(crew): ", cwd=self.repo)
        self.assertNotEqual(out.returncode, 0)
        blank = self.tmp / "blank.txt"
        blank.write_text("  \n", encoding="utf-8")
        out = self.run_cli("config", "set", "--commit-prefix", "feat(crew): ", "--original-file", str(blank), cwd=self.repo)
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertEqual(store.get(self.db, "config", "main"), cfg)


class EmptyDiffApproveTest(MergeCase):
    """S23 (T78): when the integration branch already has the approved content, approve records HEAD instead of
    running a commit that would fail (git refuses an empty commit; LIVE-SAAS review approve C3 exited 4)."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        s = review.add(self.db, self.spec_review("b"), "shop-b", 6001).number
        p = review.add(self.db, self.plan_review("b"), "shop-b", 6002).number
        self.assertEqual(review.approve(self.repo, [s, p], "批准").code, 0)

    def test_empty_diff_records_head(self):
        hook = self.repo / ".git" / "hooks" / "commit-msg"     # any commit attempt would now fail
        hook.write_text("#!/bin/sh\necho 'scope-enum' >&2\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        head = git(self.repo, "rev-parse", "HEAD").strip()
        s = review.add(self.db, self.spec_review("b"), "shop-b", 6003).number
        p = review.add(self.db, self.plan_review("b"), "shop-b", 6004).number
        res = review.approve(self.repo, [s, p], "再批一次")
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), head)
        self.assertEqual(res.commit, head)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        approval = store.get(self.db, "item", str(res.approval))
        self.assertEqual(approval["baselineCommit"], head)
        for n in (s, p):
            self.assertEqual(store.get(self.db, "item", str(n))["closedReason"], "answered")
        self.assertEqual({x["kind"] for x in res.sends}, {"coordination-notice", "user-reply"})
        self.assertIn("没有差异", " ".join(res.lines))

    def test_marker_failure_is_not_empty_diff(self):
        import os
        s = review.add(self.db, self.spec_review("b"), "shop-b", 6005).number
        os.environ["FAKE_REVIEW_FAIL"] = "b"
        try:
            res = review.approve(self.repo, [s], "再批一次")
        finally:
            del os.environ["FAKE_REVIEW_FAIL"]
        self.assertEqual(res.code, 4, res.lines)
        self.assertEqual(store.get(self.db, "item", str(s))["state"], "open")


if __name__ == "__main__":
    unittest.main()
