import os
import subprocess
import unittest

from helpers import MergeCase, git

from module_crew import merge, store


class CleanupTest(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def test_cleanup_after_merge(self):
        self.approve_final("b", 1)
        self.assertEqual(merge.run(self.repo, check_command="python3 -c pass").code, 0)
        res = merge.cleanup(self.repo, "b", "b 可以收回")
        self.assertEqual(res.code, 0, res.lines)
        self.assertFalse(self.wt["b"].exists())
        self.assertIn("b", git(self.repo, "branch", "--list", "b"))
        self.assertEqual(store.get(self.db, "session", "shop-b")["status"], "retired")

    def test_cleanup_refused(self):
        res = merge.cleanup(self.repo, "c", "收回 c")          # not merged
        self.assertEqual(res.code, 3)
        self.assertTrue(self.wt["c"].exists())
        self.approve_final("b", 1)
        merge.run(self.repo, check_command="python3 -c pass")
        (self.wt["b"] / "scratch.txt").write_text("x")
        self.assertEqual(merge.cleanup(self.repo, "b", "收回").code, 3)
        self.assertTrue(self.wt["b"].exists())
        self.assertEqual(store.get(self.db, "session", "shop-b")["status"], "active")


class PushTest(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        self.remote = self.tmp / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(self.remote)], check=True)
        git(self.repo, "remote", "add", "origin", str(self.remote))
        git(self.repo, "push", "-q", "origin", "main")
        git(self.repo, "fetch", "-q", "origin")
        self.remote_main = git(self.remote, "rev-parse", "main").strip()
        self.approve_final("b", 1)
        assert merge.run(self.repo, check_command="python3 -c pass").code == 0
        self.addCleanup(lambda: os.environ.pop("MODULE_CREW_GH", None))

    def test_push_plan(self):
        plan = merge.push_plan(self.repo)
        self.assertEqual(plan.code, 0, plan.lines)
        self.assertTrue(plan.branch.startswith("crew/batch-"))
        self.assertEqual(plan.base, "main")
        self.assertEqual(len(plan.commits), 3)
        self.assertIn("b", plan.body)
        self.assertNotIn("crew/", git(self.remote, "branch", "--list"))

    def test_push_with_fake_gh(self):
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        log = self.tmp / "gh-args.txt"
        gh = bin_dir / "gh"
        gh.write_text(f"#!/bin/sh\necho \"$@\" > {log}\necho https://example.invalid/pr/1\n")
        gh.chmod(0o755)
        os.environ["MODULE_CREW_GH"] = str(gh)
        res = merge.push(self.repo, "推吧")
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(git(self.remote, "rev-parse", res.branch).strip(), git(self.repo, "rev-parse", "main").strip())
        self.assertEqual(git(self.remote, "rev-parse", "main").strip(), self.remote_main)
        args = log.read_text()
        self.assertIn(f"--base main --head {res.branch}", args)
        self.assertNotIn("auto", args)
        rec = store.get(self.db, "item", str(res.record))
        self.assertEqual((rec["kind"], rec["remoteBranch"], rec["pr"]), ("push", res.branch, "https://example.invalid/pr/1"))
        self.assertEqual(rec["answer"]["original"], "推吧")

    def test_push_without_gh_prints_body(self):
        os.environ["MODULE_CREW_GH"] = ""
        res = merge.push(self.repo, "推吧")
        self.assertEqual(res.code, 0, res.lines)
        self.assertIn("PR 正文", " ".join(res.lines))
        self.assertIsNone(store.get(self.db, "item", str(res.record))["pr"])

    def test_no_remote(self):
        git(self.repo, "remote", "remove", "origin")
        self.assertEqual(merge.push_plan(self.repo).code, 3)
        self.assertEqual(merge.push(self.repo, "推").code, 3)
