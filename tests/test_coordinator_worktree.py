"""S40 (0.16.1): the desktop app opens a new session in a worktree by default; the coordinator is told to work in the
integration checkout, and status reads spec-guard there instead of misreporting the stray worktree."""

import os
import unittest

from helpers import ReviewCase, git, make_worktree

from module_crew import handover, hooks, probe, store


class HandoverWordingTest(unittest.TestCase):
    def test_new_session_step_and_opening_say_no_worktree(self):
        for to, step in (("claude", "### 第 2 步"), ("codex", "### 第 3 步")):
            with self.subTest(to=to):
                text = handover.guide(to, "shop-coord", "module-crew", "/p/repo", "/p/words.txt")
                block = text.split(step, 1)[1].split("### ", 1)[0]
                self.assertIn("不要用 worktree", block)
                self.assertIn("集成 checkout `/p/repo`", block)
                opening = text.split("## 开场文字（整段贴进新会话）", 1)[1].split("## ", 1)[0]
                self.assertIn("发现自己在 worktree 里时，module-crew 命令和提交一律在集成 checkout 做", opening)
        self.assertIn("新开会话时不要用 worktree，目录选集成 checkout",
                      handover.guide("claude", "shop-coord", "module-crew", "/p/repo", "/p/words.txt"))


class StrayWorktreeTest(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        self.stray = make_worktree(self.repo, "claude-stray")       # what the desktop app makes for a new session
        (self.stray / ".agent" / "config.json").unlink()            # e.g. a project that keeps it untracked
        self.hint = f"本会话在 worktree {self.stray} 里，模块协调要在集成 checkout {self.repo} 运行命令、提交"

    def test_status_hint_and_spec_guard_read_from_integration_checkout(self):
        out = self.run_cli("status", cwd=self.stray)
        self.assertIn(self.hint, out.stdout, out.stdout + out.stderr)
        self.assertEqual(probe.run(self.stray).checks["spec-guard-enabled"].state, "ok")
        self.assertNotIn("项目还没启用 spec-guard", out.stdout)

    def test_no_hint_in_integration_checkout_or_module_worktree(self):
        self.assertIsNone(hooks.stray_worktree_line(self.repo))
        self.assertIsNone(hooks.stray_worktree_line(self.wt["b"]))
        self.assertNotIn("模块协调要在集成 checkout", self.run_cli("status", cwd=self.wt["b"]).stdout)

    def test_module_worktree_without_ignored_config_reads_integration_checkout(self):
        (self.wt["b"] / ".agent" / "config.json").unlink()          # the project keeps it git-ignored (LIVE-SAAS)
        here = probe.run(self.repo).checks
        there = probe.run(self.wt["b"]).checks
        for check in ("spec-guard-enabled", "spec-guard-planning"):
            self.assertEqual(there[check].state, here[check].state, check)
            self.assertNotEqual(there[check].state, "blocker", check)
        self.assertNotIn("项目还没启用 spec-guard", self.run_cli("status", cwd=self.wt["b"]).stdout)

    def test_bind_takeover_in_worktree_prints_hint(self):
        words = self.tmp / "w.txt"
        words.write_text("你来接手模块协调", encoding="utf-8")
        env = dict(os.environ, CLAUDE_CODE_SESSION_ID="sid-new")
        out = self.run_cli("bind", "shop-coord", "--takeover", "--original-file", str(words), cwd=self.stray, env=env)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("已接管", out.stdout)
        self.assertIn(self.hint, out.stdout)

    def test_bind_refused_in_worktree_prints_hint(self):
        words = self.tmp / "w.txt"
        words.write_text("你来做模块协调", encoding="utf-8")
        env = dict(os.environ, CLAUDE_CODE_SESSION_ID="sid-new")
        out = self.run_cli("bind", "shop-coord", "--original-file", str(words), cwd=self.stray, env=env)
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn(self.hint, out.stderr)


if __name__ == "__main__":
    unittest.main()
