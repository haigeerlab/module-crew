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


class TakeoverTest(HandoverCase):
    """Acceptance 2."""

    def test_takeover_from_another_directory(self):
        out = hooks.bind(self.db, "shop-coord", "sid-new", self.elsewhere, original="新会话接手模块协调", takeover=True)
        self.assertIn("已接管", out)
        rec = store.get(self.db, "session", "shop-coord")
        self.assertEqual(rec["hostSession"]["sessionId"], "sid-new")
        self.assertEqual([p["sessionId"] for p in rec["previousSessions"]], ["sid-coord"])
        ev = [e for e in store.events(self.db) if e["type"] == "session.taken-over"][-1]
        self.assertEqual((ev["data"]["original"], ev["data"]["oldSessionId"], ev["data"]["newSessionId"]),
                         ("新会话接手模块协调", "sid-coord", "sid-new"))
        self.assertIn("本会话是模块协调（shop-coord）", run("session-start", self.elsewhere, "sid-new"))

    def test_takeover_refusals(self):
        before = list(store.events(self.db))
        with self.assertRaises(hooks.BindRefused):
            hooks.bind(self.db, "shop-coord", "sid-new", self.elsewhere, original="", takeover=True)
        with self.assertRaises(hooks.BindRefused):
            hooks.bind(self.db, "shop-b", "sid-new", self.elsewhere, original="接手 b", takeover=True)
        self.assertEqual(list(store.events(self.db)), before)

    def test_cli(self):
        env = dict(os.environ, CLAUDE_CODE_SESSION_ID="sid-cli")
        r = self.run_cli("bind", "shop-coord", "--takeover", "--original", "接手", cwd=self.elsewhere, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.run_cli("bind", "shop-b", "--takeover", "--original", "接手", cwd=self.elsewhere, env=env)
        self.assertEqual(r.returncode, 3)


class OldSessionTest(HandoverCase):
    """Acceptance 3."""

    def test_old_session_told_it_was_taken_over(self):
        hooks.bind(self.db, "shop-coord", "sid-new", self.elsewhere, original="新会话接手", takeover=True)
        for event in ("session-start", "prompt"):
            with self.subTest(event=event):
                text = run(event, self.repo, "sid-coord")
                self.assertIn("本会话已被接管", text)
                self.assertIn("不要再以 shop-coord 的身份执行 module-crew 写命令", text)
                self.assertNotIn("本会话是模块协调", text)
                self.assertNotIn("提醒：这个项目已有模块协调", text)


if __name__ == "__main__":
    unittest.main()
