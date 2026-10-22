"""crew-session-handover: identity by session id, one-step takeover, write-command session guard (see the Spec)."""

import json
import os
import unittest

from helpers import MergeCase, make_worktree

from module_crew import hooks, store


def run(event, cwd, sid=None, **extra):
    payload = {"cwd": str(cwd), **({"session_id": sid} if sid else {}), **extra}
    out = hooks.run_hook(event, json.dumps(payload))
    return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""


class HandoverCase(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")
        self.elsewhere = make_worktree(self.repo, "elsewhere")


class IdentityBySessionTest(HandoverCase):
    """Acceptance 1."""

    def test_coordinator_in_another_directory(self):
        for source in ("startup", "compact", "clear"):
            with self.subTest(source=source):
                text = run("session-start", self.elsewhere, "sid-coord", source=source)
                self.assertIn("本会话是模块协调（shop-coord）", text)
                self.assertIn("module-crew 命令入口：", text)
                self.assertIn(f"本会话在 {os.path.realpath(self.elsewhere)}", text)
                self.assertIn(f"shop-coord 登记的目录是 {os.path.realpath(self.repo)}", text)
        self.assertIn("module-crew：模块协调", run("prompt", self.elsewhere, "sid-coord"))

    def test_home_directory_has_no_extra_line(self):
        text = run("session-start", self.repo, "sid-coord")
        self.assertIn("本会话是模块协调（shop-coord）", text)
        self.assertNotIn("登记的目录是", text)

    def test_module_session_in_another_directory(self):
        hooks.bind(self.db, "shop-b", "sid-b", self.wt["b"])
        text = run("session-start", self.elsewhere, "sid-b")
        self.assertIn("模块 b 的模块会话", text)
        self.assertIn("module-crew 命令入口：", text)
        self.assertIn("shop-b 登记的目录是", text)
        self.assertIn("你是 b 的模块会话", run("prompt", self.elsewhere, "sid-b"))

    def test_unregistered_session_unchanged(self):
        text = run("session-start", self.elsewhere, "sid-other")
        self.assertIn("提醒：这个项目已有模块协调", text)
        self.assertNotIn("本会话是模块协调", text)
        self.assertEqual(run("prompt", self.elsewhere, "sid-other"), "")


if __name__ == "__main__":
    unittest.main()
