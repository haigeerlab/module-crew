import subprocess
import unittest

from helpers import ProbeCase, git, make_worktree

from module_crew import probe, store


class GitCheckTest(ProbeCase):
    def test_normal_repo_ok(self):
        self.assertEqual(probe.check_git(self.repo).state, "ok")

    def test_outside_repo_raises(self):
        outside = self.tmp / "plain"
        outside.mkdir()
        with self.assertRaises(probe.NotInRepo):
            probe.check_git(outside)

    def test_bare_repo_is_blocker(self):
        bare = self.tmp / "bare.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        check = probe.check_git(bare)
        self.assertEqual(check.state, "blocker")
        self.assertIn("裸仓库", check.reason)


class BaselineTest(ProbeCase):
    def test_current_branch_clean(self):
        check = probe.check_baseline(self.repo)
        self.assertEqual(check.state, "ok", check.reason)
        self.assertIn("main", check.reason)

    def test_dirty_and_untracked_count(self):
        (self.repo / "README.md").write_text("changed\n")
        (self.repo / "new.txt").write_text("x\n")
        check = probe.check_baseline(self.repo)
        self.assertEqual(check.state, "blocker")
        self.assertIn("2 个文件", check.reason)

    def test_configured_branch_checked_out_in_worktree(self):
        wt = make_worktree(self.repo, "integration")
        db, _ = store.init_store(self.repo)
        with db.transaction(actor="t") as tx:
            tx.put("config", "main", {"integrationBranch": "integration"}, action="set")
        (self.repo / "README.md").write_text("dirty main checkout is not the baseline\n")
        check = probe.check_baseline(self.repo)
        self.assertEqual(check.state, "ok", check.reason)
        self.assertIn(str(wt), check.reason)
        (wt / "x.txt").write_text("x")
        self.assertEqual(probe.check_baseline(self.repo).state, "blocker")

    def test_configured_branch_not_checked_out(self):
        git(self.repo, "branch", "integration")
        db, _ = store.init_store(self.repo)
        with db.transaction(actor="t") as tx:
            tx.put("config", "main", {"integrationBranch": "integration"}, action="set")
        check = probe.check_baseline(self.repo)
        self.assertEqual(check.state, "blocker")
        self.assertIn("没有被任何 checkout 检出", check.reason)


if __name__ == "__main__":
    unittest.main()
