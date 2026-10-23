"""crew-codex-coordinator: the module coordinator running in Codex desktop (see the Spec)."""

import json
import os
import unittest

from helpers import MergeCase

from module_crew import hooks, store

SESSION_VARS = ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")


class CodexCoordCase(MergeCase):
    """MergeCase whose coordinator shop-coord was handed over to Codex and is bound to thread `thread-coord`."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        with self.db.transaction(actor="t") as tx:
            rec = tx.get("session", "shop-coord")
            tx.put("session", "shop-coord", {
                **rec, "host": "codex-desktop", "hostSession": hooks.identity("thread-coord", ""),
                "hostHandover": {"from": "claude-desktop", "to": "codex-desktop", "at": store.now(),
                                 "original": "换到 Codex", "pending": False}}, action="registered")

    def env(self, codex: str | None = None, claude: str | None = None) -> dict:
        env = {k: v for k, v in os.environ.items() if k not in SESSION_VARS}
        if codex:
            env["CODEX_THREAD_ID"] = codex
        if claude:
            env["CLAUDE_CODE_SESSION_ID"] = claude
        return env

    def cli(self, *args, codex: str | None = "thread-coord", claude: str | None = None, cwd=None):
        return self.run_cli(*args, env=self.env(codex, claude), cwd=cwd)


class StatusCodexSelfTest(CodexCoordCase):
    """Acceptance 7: with no hook to say who it is, `status` tells a Codex thread whether it is the coordinator."""

    def test_registered_thread_is_told_it_is_the_coordinator(self):
        out = self.cli("status").stdout
        self.assertEqual(out.splitlines()[0], "本会话是模块协调 shop-coord（Codex）：没有钩子，以下按状态库为准")
        doc = json.loads(self.cli("status", "--json").stdout)
        self.assertEqual(doc["store"]["codexSelf"], {"name": "shop-coord", "registered": True})

    def test_other_thread_is_told_it_is_not(self):
        out = self.cli("status", codex="thread-other").stdout
        self.assertEqual(out.splitlines()[0], "本线程不是登记的模块协调，不要按模块协调行事")
        doc = json.loads(self.cli("status", "--json", codex="thread-other").stdout)
        self.assertEqual(doc["store"]["codexSelf"], {"name": "shop-coord", "registered": False})

    def test_codex_host_line(self):
        self.assertIn("模块协调：Codex 桌面版；模块会话：Codex 桌面版", self.cli("status").stdout)

    def test_claude_output_unchanged(self):
        """Without CODEX_THREAD_ID nothing is added (a Claude conversation, or the user's own terminal)."""
        for claude in (None, "sid-x"):
            with self.subTest(claude=claude):
                out = self.cli("status", codex=None, claude=claude).stdout
                self.assertTrue(out.startswith("体检\n"))
                self.assertNotIn("Codex）：没有钩子", out)
                doc = json.loads(self.cli("status", "--json", codex=None, claude=claude).stdout)
                self.assertIsNone(doc["store"]["codexSelf"])

    def test_claude_session_wins_over_codex_variable(self):
        """A Claude conversation that inherited CODEX_THREAD_ID is still Claude (hooks.own_host)."""
        out = self.cli("status", codex="thread-coord", claude="sid-x").stdout
        self.assertTrue(out.startswith("体检\n"))


class StatusClaudeCoordinatorTest(MergeCase):
    """Acceptance 7, the other half: a Claude coordinator's status is unchanged."""

    def test_host_line_unchanged(self):
        self.assertIn("模块协调：Claude 桌面版；模块会话：Claude 或 Codex 桌面版", self.run_cli("status").stdout)


if __name__ == "__main__":
    unittest.main()
