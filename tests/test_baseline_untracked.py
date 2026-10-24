"""S26 (T132): untracked files in the integration checkout no longer block; only tracked changes do."""

import unittest

from helpers import ProbeCase, ReviewCase, StartCase

from module_crew import coordinator, probe, review, start, store


class CheckTest(ProbeCase):
    def test_untracked_only_is_ok_with_hint(self):
        (self.repo / "new.txt").write_text("x\n")
        check = probe.check_baseline(self.repo)
        self.assertEqual(check.state, "ok", check.reason)
        self.assertIn("1 个未跟踪文件", check.reason)
        self.assertIn("同路径", check.reason)

    def test_tracked_change_still_blocks(self):
        (self.repo / "README.md").write_text("changed\n")
        (self.repo / "new.txt").write_text("x\n")
        check = probe.check_baseline(self.repo)
        self.assertEqual(check.state, "blocker")
        self.assertIn("1 个已跟踪文件", check.reason)

    def test_status_shows_hint(self):
        (self.repo / "new.txt").write_text("x\n")
        r = self.run_cli("status")
        self.assertNotIn("集成分支所在的 checkout 不干净", r.stdout)
        self.assertIn("未跟踪文件", r.stdout)


class FlowTest(StartCase):
    def test_coordinator_up(self):
        (self.repo / "new.txt").write_text("x\n")
        code, lines = coordinator.up(self.repo, "shop", "升级", session_id="sid-1")
        self.assertEqual(code, 0, lines)

    def test_start_prepare(self):
        (self.repo / "new.txt").write_text("x\n")
        res = start.prepare(self.repo, ["b"], "开 b", short="shop")
        self.assertEqual(res.code, 0, res.lines)

    def test_start_prepare_tracked_change_refused(self):
        (self.repo / "README.md").write_text("changed\n")
        res = start.prepare(self.repo, ["b"], "开 b", short="shop")
        self.assertEqual(res.code, 3, res.lines)
        self.assertIn("集成分支所在的 checkout 不干净", " ".join(res.lines))


class ApproveTest(ReviewCase):
    def test_review_approve(self):
        db = store.open_store(self.repo)
        n = review.add(db, self.spec_review("b"), "shop-b", 4600).number
        (self.repo / "new.txt").write_text("x\n")
        res = review.approve(self.repo, [n], "b 的 Spec 批准")
        self.assertEqual(res.code, 0, res.lines)
        self.assertTrue((self.repo / "new.txt").exists())


if __name__ == "__main__":
    unittest.main()
