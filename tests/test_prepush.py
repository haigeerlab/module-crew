"""crew-host-permissions: the pre-push guard and merge push's one-time pass (spec/crew-host-permissions.md key decision 5)."""

import json
import subprocess
import time
import unittest

from helpers import MergeCase, git

from module_crew import merge, permissions, prepush, store


class GuardCase(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        (self.repo / ".git" / "info").mkdir(exist_ok=True)
        (self.repo / ".git" / "info" / "exclude").write_text(".claude/settings.local.json\n.codex/\n", encoding="utf-8")
        self.remote = self.tmp / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(self.remote)], check=True)
        git(self.repo, "remote", "add", "origin", str(self.remote))
        git(self.repo, "push", "-q", "origin", "main")       # before the guard exists
        self.hook = self.repo / ".git" / "hooks" / "pre-push"

    def push(self, cwd, ref="main:refs/heads/try"):
        return subprocess.run(["git", "-C", str(cwd), "push", "origin", ref], capture_output=True, text=True)

    def token(self):
        return json.loads((self.db.path / prepush.TOKEN).read_text(encoding="utf-8"))


class GuardTest(GuardCase):
    def test_module_worktree_never_pushes(self):
        permissions.apply(self.repo, "预配")
        self.assertTrue(prepush.is_active(self.hook))
        out = self.push(self.wt["b"], "b:refs/heads/b")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("模块会话不推送", out.stderr)
        self.assertNotIn("b", git(self.remote, "branch", "--list"))

    def test_integration_checkout_needs_a_pass(self):
        permissions.apply(self.repo, "预配")
        out = self.push(self.repo)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("没有放行凭证", out.stderr)
        self.assertIn("--no-verify", out.stderr)

    def test_expired_wrong_ref_and_spent_passes_are_refused(self):
        permissions.apply(self.repo, "预配")
        prepush.write_token(self.db.path, "refs/heads/other")
        self.assertIn("不符", self.push(self.repo).stderr)
        prepush.write_token(self.db.path, "refs/heads/try")
        path = self.db.path / prepush.TOKEN
        path.write_text(json.dumps({**self.token(), "expires": time.time() - 1}), encoding="utf-8")
        self.assertIn("过期", self.push(self.repo).stderr)
        prepush.write_token(self.db.path, "refs/heads/try")
        self.assertEqual(self.push(self.repo).returncode, 0)
        self.assertTrue(self.token()["used"])
        self.assertIn("没有放行凭证", self.push(self.repo, "main:refs/heads/try2").stderr)

    def test_merge_push_goes_through_and_leaves_no_live_pass(self):
        permissions.apply(self.repo, "预配")
        self.approve_final("b", 1)
        assert merge.run(self.repo, check_command="python3 -c pass").code == 0
        import os
        os.environ["MODULE_CREW_GH"] = ""
        self.addCleanup(lambda: os.environ.pop("MODULE_CREW_GH", None))
        res = merge.push(self.repo, "推吧")
        self.assertEqual(res.code, 0, res.lines)
        self.assertIn(res.branch, git(self.remote, "branch", "--list"))
        self.assertTrue(self.token()["used"])

    def test_no_store_means_no_guard(self):
        other = self.tmp / "hook-elsewhere"
        prepush.install(other, str(self.tmp / "nowhere-crew"), self.tmp / "nowhere-store")
        out = subprocess.run([str(other)], input="refs/heads/main x refs/heads/main y\n", capture_output=True,
                             text=True, cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_not_installed_with_hooks_path_or_foreign_hook(self):
        git(self.repo, "config", "core.hooksPath", ".husky")
        lines = permissions.apply(self.repo, "预配")
        self.assertTrue(any("没装" in l and "core.hooksPath" in l for l in lines))
        self.assertFalse(self.hook.exists())
        git(self.repo, "config", "--unset", "core.hooksPath")
        self.hook.parent.mkdir(exist_ok=True)
        self.hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        lines = permissions.apply(self.repo, "预配")
        self.assertTrue(any("已有别的 pre-push 钩子" in l for l in lines))
        self.assertEqual(self.hook.read_text(encoding="utf-8"), "#!/bin/sh\nexit 0\n")

    def test_remove_turns_the_guard_off(self):
        permissions.apply(self.repo, "预配")
        permissions.remove(self.repo, "撤掉")
        self.assertTrue(self.hook.exists())
        self.assertFalse(prepush.is_active(self.hook))
        self.assertEqual(self.push(self.repo).returncode, 0)
        self.assertTrue(prepush.is_active(self.hook) is False)
        permissions.apply(self.repo, "再预配")
        self.assertTrue(prepush.is_active(self.hook))


if __name__ == "__main__":
    unittest.main()
