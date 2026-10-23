"""crew-codex-coordinator: the module coordinator running in Codex desktop (see the Spec)."""

import io
import json
import os
import subprocess
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from helpers import MergeCase, spec_guard_interface

from module_crew import __main__ as cli
from module_crew import hooks, probe, store

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


class HostCheckCoordinatorTest(CodexCoordCase):
    """Acceptance 6: `host-check` in the integration checkout checks what the coordinator needs."""

    def check(self, *args):
        return self.cli("host-check", *args)

    def test_all_pass(self):
        r = self.check("--json")
        self.assertEqual(r.returncode, 0, r.stdout)
        doc = json.loads(r.stdout)
        self.assertEqual(doc["role"], "coordinator")
        self.assertEqual({c["id"] for c in doc["checks"]},
                         {"store", "registered", "version", "git-writable", "spec-guard", "entry"})
        self.assertTrue(all(c["ok"] for c in doc["checks"]), doc["checks"])

    def test_git_common_dir_read_only(self):
        gitdir = self.repo / ".git"
        mode = gitdir.stat().st_mode
        gitdir.chmod(0o555)
        self.addCleanup(gitdir.chmod, mode)
        r = self.check("--json")
        self.assertEqual(r.returncode, 3)
        bad = {c["id"]: c for c in json.loads(r.stdout)["checks"] if not c["ok"]}
        self.assertEqual(set(bad), {"git-writable"})
        self.assertIn("沙箱外运行", bad["git-writable"]["fix"])

    def test_spec_guard_missing(self):
        self.plugins.entries.pop("spec-guard@m")
        self.plugins.write()
        bad = {c["id"] for c in json.loads(self.check("--json").stdout)["checks"] if not c["ok"]}
        self.assertEqual(bad, {"spec-guard"})

    def test_module_worktree_unchanged(self):
        """A module worktree keeps the module-session checks, now with role 'dev'."""
        doc = json.loads(self.cli("host-check", "--json", cwd=self.wt["b"]).stdout)
        self.assertEqual(doc["role"], "dev")
        self.assertEqual([c["id"] for c in doc["checks"]], ["store", "registered", "version", "git-writable"])


SANDBOX = "Codex 沙箱不让写 git 目录：请申请在沙箱外运行这条命令"
CODEX_PLUGIN = "Codex 侧的插件安装 module-crew 不读"


class SandboxHintTest(unittest.TestCase):
    """Acceptance 8: a write the Codex sandbox refused says to ask for running outside the sandbox."""

    def setUp(self):
        for key in SESSION_VARS:
            if key in os.environ:
                self.addCleanup(os.environ.__setitem__, key, os.environ.pop(key))

    def codex(self):
        return mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "thread-coord"})

    def test_recognised_texts(self):
        with self.codex():
            for text in ("fatal: Unable to create '/r/.git/index.lock': Operation not permitted",
                         "error: could not lock config file .git/config: Operation not permitted",
                         "fatal: Unable to create '/r/.git/index.lock': Permission denied"):
                with self.subTest(text=text):
                    self.assertEqual(probe.sandbox_hint(text), SANDBOX)
            for text in ("fatal: Unable to create '/r/.git/index.lock': File exists.", "fatal: not a git repository", ""):
                with self.subTest(text=text):
                    self.assertIsNone(probe.sandbox_hint(text))

    def test_only_in_codex(self):
        self.assertIsNone(probe.sandbox_hint("Operation not permitted"))

    def test_git_stderr_carries_hint(self):
        failed = subprocess.CompletedProcess(["git"], 128, "", "fatal: Unable to create 'x/index.lock': Operation not permitted\n")
        with self.codex(), mock.patch("subprocess.run", return_value=failed):
            out = probe._git(Path("."), "commit", "-m", "x")
        self.assertIn("Operation not permitted", out.stderr)
        self.assertIn(SANDBOX, out.stderr)

    def test_store_write_refused(self):
        refused = PermissionError(1, "Operation not permitted", "/r/.git/module-crew/events.jsonl")
        err = io.StringIO()
        with self.codex(), mock.patch.object(cli, "_main", side_effect=refused), redirect_stderr(err):
            self.assertEqual(cli.main(["task", "list"]), 1)
        self.assertIn("Operation not permitted", err.getvalue())
        self.assertIn(SANDBOX, err.getvalue())

    def test_store_write_refused_outside_codex_unchanged(self):
        refused = PermissionError(1, "Operation not permitted")
        with mock.patch.object(cli, "_main", side_effect=refused), self.assertRaises(PermissionError):
            cli.main(["task", "list"])


class CodexPluginHintTest(CodexCoordCase):
    """Acceptance 8: in Codex, a plugin missing from Claude's records says module-crew does not read Codex installs."""

    def drop(self, name):
        self.plugins.entries.pop(f"{name}@m")
        self.plugins.write()

    def reasons(self, *args, **kw):
        doc = json.loads(self.cli("status", "--json", *args, **kw).stdout)
        return {c["id"]: c["reason"] for c in doc["checks"]}

    def test_status(self):
        for name in ("spec-guard", "agent-relay"):
            with self.subTest(name=name):
                self.drop(name)
                self.assertIn(CODEX_PLUGIN, self.reasons()[name])
                self.assertNotIn(CODEX_PLUGIN, self.reasons(codex=None)[name])
                self.plugins.install(name, {"interface": "2.0"} if name == "agent-relay" else spec_guard_interface("1.7"),
                                     map_script=name == "spec-guard")

    def test_host_check(self):
        self.drop("spec-guard")
        bad = {c["id"]: c for c in json.loads(self.cli("host-check", "--json").stdout)["checks"] if not c["ok"]}
        self.assertIn(CODEX_PLUGIN, bad["spec-guard"]["reason"])


class StatusClaudeCoordinatorTest(MergeCase):
    """Acceptance 7, the other half: a Claude coordinator's status is unchanged."""

    def test_host_line_unchanged(self):
        self.assertIn("模块协调：Claude 桌面版；模块会话：Claude 或 Codex 桌面版", self.run_cli("status").stdout)


if __name__ == "__main__":
    unittest.main()
