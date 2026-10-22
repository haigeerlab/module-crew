"""crew-merge decisions 1 and 11 (0.11.3): the PR base when the integration branch is local only; push timeout and errors."""

import os
import subprocess
import unittest

from helpers import MergeCase, git

from module_crew import merge, store


class LocalIntegrationCase(MergeCase):
    """The remote has only `trunk` (its default branch); the integration branch `main` is local only."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        self.remote = self.tmp / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(self.remote)], check=True)
        git(self.repo, "remote", "add", "origin", str(self.remote))
        git(self.repo, "push", "-q", "origin", "main:trunk")
        git(self.remote, "symbolic-ref", "HEAD", "refs/heads/trunk")
        git(self.repo, "fetch", "-q", "origin")
        self.approve_final("b", 1)
        assert merge.run(self.repo, check_command="python3 -c pass").code == 0
        os.environ["MODULE_CREW_GH"] = ""
        self.addCleanup(lambda: os.environ.pop("MODULE_CREW_GH", None))


class PrBaseTest(LocalIntegrationCase):
    """Acceptance 24."""

    def test_remote_default_branch(self):
        git(self.repo, "remote", "set-head", "origin", "-a")
        plan = merge.push_plan(self.repo)
        self.assertEqual(plan.code, 0, plan.lines)
        self.assertEqual(plan.base, "trunk")
        self.assertEqual(len(plan.commits), 3)                    # only what trunk lacks, not the whole history
        self.assertIn("远端默认分支", " ".join(plan.lines))

    def test_no_default_asks_for_pr_base(self):
        subprocess.run(["git", "-C", str(self.repo), "remote", "set-head", "origin", "-d"], capture_output=True)
        plan = merge.push_plan(self.repo)
        self.assertEqual(plan.code, 3, plan.lines)
        self.assertIn("--pr-base", " ".join(plan.lines))

    def test_pr_base_given(self):
        plan = merge.push_plan(self.repo, pr_base="trunk")
        self.assertEqual((plan.code, plan.base, len(plan.commits)), (0, "trunk", 3))
        self.assertNotIn("prBase", store.get(self.db, "config", "main"))   # used once, not stored
        r = self.run_cli("merge", "push-plan", "--pr-base", "trunk")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PR 开向 trunk", r.stdout)


class PushTimeoutTest(LocalIntegrationCase):
    """Acceptance 25."""

    def hook(self, body):
        path = self.repo / ".git" / "hooks" / "pre-push"
        path.write_text(body, encoding="utf-8")
        os.chmod(path, 0o755)

    def test_slow_hook_times_out_readably(self):
        with self.db.transaction(actor="t") as tx:
            tx.put("config", "main", dict(tx.get("config", "main"), checkTimeout=2), action="updated")
        self.hook("#!/bin/sh\nsleep 6\n")
        res = merge.push(self.repo, "推送", pr_base="trunk")
        self.assertEqual(res.code, 4, res.lines)
        self.assertIn("超时（2 秒）", " ".join(res.lines))
        self.assertNotIn("crew/", git(self.remote, "branch", "--list"))

    def test_push_timeout_is_check_timeout(self):
        self.assertEqual(merge.push_timeout({}), merge.DEFAULT_CHECK_TIMEOUT)
        self.assertEqual(merge.push_timeout({"checkTimeout": 90}), 90)

    def test_hook_refusal_readable_no_traceback(self):
        self.hook("#!/bin/sh\necho '完整检查没通过' >&2\nexit 1\n")
        r = self.run_cli("merge", "push", "--pr-base", "trunk", "--original", "推送")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("推送失败", r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
