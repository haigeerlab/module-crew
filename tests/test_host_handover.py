"""crew-host-handover: switch the whole crew between Claude Code and Codex in the gap between batches (see the Spec)."""

import json
import os
import re
import unittest
from unittest import mock

from helpers import RepoCase, ReviewCase, StartCase

from module_crew import coordinator, handover, hooks, permissions, store
from test_permissions import PermCase


def coord(**extra):
    return {"role": "coordinator", "host": "claude-desktop", "status": "active", **extra}


def handed(to="codex-desktop", frm="claude-desktop", pending=True):
    return {"from": frm, "to": to, "at": store.now(), "original": "换到 Codex", "pending": pending}


class StoreHostTest(RepoCase):
    """Acceptance 8: the coordinator may be registered on Codex, but only through a handover."""

    def setUp(self):
        super().setUp()
        self.db, _ = store.init_store(self.repo)

    def put(self, key, rec):
        with self.db.transaction(actor="t") as tx:
            tx.put("session", key, rec, action="registered")

    def test_codex_coordinator_with_handover_accepted(self):
        self.put("shop-coord", coord(host="codex-desktop", hostHandover=handed()))
        self.assertEqual(store.get(self.db, "session", "shop-coord")["host"], "codex-desktop")

    def test_codex_coordinator_without_handover_rejected(self):
        with self.assertRaises(store.InvalidSession):
            self.put("shop-coord", coord(host="codex-desktop"))

    def test_handover_must_match_host(self):
        with self.assertRaises(store.InvalidSession):
            self.put("shop-coord", coord(host="codex-desktop", hostHandover=handed(to="claude-desktop")))

    def test_bad_handover_records(self):
        cases = {
            "not a dict": "codex",
            "bad from": {**handed(), "from": "codex-cli"},
            "empty original": {**handed(), "original": " "},
            "pending not bool": {**handed(), "pending": "yes"},
            "at missing": {k: v for k, v in handed().items() if k != "at"},
        }
        for name, rec in cases.items():
            with self.subTest(name):
                with self.assertRaises(store.InvalidSession):
                    self.put("shop-coord", coord(host="codex-desktop", hostHandover=rec))

    def test_claude_coordinator_may_keep_a_finished_handover(self):
        self.put("shop-coord", coord(hostHandover=handed(to="claude-desktop", frm="codex-desktop", pending=False)))
        self.assertFalse(store.get(self.db, "session", "shop-coord")["hostHandover"]["pending"])

    def test_handover_only_on_coordinator(self):
        with self.assertRaises(store.InvalidSession):
            self.put("shop-b", {"role": "dev", "host": "claude-desktop", "status": "active", "module": "b",
                                "worktree": "/tmp/b", "hostHandover": handed()})


class UpStaysClaudeTest(StartCase):
    """Acceptance 8: `coordinator up` still registers Claude, even from a Codex thread."""

    def test_up_from_codex_thread_registers_claude(self):
        with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "thread-1"}):
            code, lines = coordinator.up(self.repo, "shop", "升级", session_id="thread-1")
        self.assertEqual(code, 0, lines)
        rec = store.get(store.open_store(self.repo), "session", "shop-coord")
        self.assertEqual(rec["host"], "claude-desktop")
        self.assertNotIn("hostHandover", rec)


def close_batch(db):
    """Retire the module sessions and close everything open: the gap between two batches."""
    with db.transaction(actor="t") as tx:
        for name, rec in tx.records("session").items():
            if rec.get("role") in ("dev", "task") and rec.get("status") == "active":
                tx.put("session", name, {**rec, "status": "retired"}, action="retired")
        for kind in ("item", "request", "ticket"):
            for key, rec in tx.records(kind).items():
                if rec.get("state") != "closed":
                    tx.put(kind, key, {**rec, "state": "closed"}, action="closed")


class GapCase(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def check(self, to=None):
        return handover.check(self.repo, to)


class ReadinessTest(GapCase):
    """Acceptance 1 (the check): each condition reported on its own, exit 3 until all are met."""

    def ids_failing(self, to=None):
        code, doc, _ = self.check(to)
        return code, {c["id"] for c in doc["checks"] if not c["ok"]}

    def test_sessions_in_use(self):
        code, failing = self.ids_failing()
        self.assertEqual(code, 3)
        self.assertIn("sessions", failing)
        _, _, lines = self.check()
        self.assertTrue(any("shop-b" in l and "模块 b" in l for l in lines), lines)

    def test_ready_when_closed(self):
        close_batch(self.db)
        code, doc, lines = self.check()
        self.assertEqual(code, 0, lines)
        self.assertTrue(doc["ready"])
        self.assertEqual(doc["from"], "claude-desktop")
        self.assertIn("具备换宿主的条件", lines[-1])
        self.assertTrue(any("decision-inbox" in l for l in lines))

    def test_open_ticket_request_item(self):
        close_batch(self.db)
        with mock.patch.object(store, "records", side_effect=_with_extra(store.records, {
                "ticket": {"5": {"state": "open"}}, "request": {"7": {"state": "open"}},
                "item": {"8": {"state": "open", "kind": "review"}, "9": {"state": "open", "kind": "merge-approval"}},
                "task": {"3": {"state": "returned"}}})):
            code, doc, lines = self.check()
        failing = {c["id"]: c["reason"] for c in doc["checks"] if not c["ok"]}
        self.assertEqual(code, 3)
        self.assertIn("W5", failing["pending"])
        self.assertIn("7", failing["pending"])
        self.assertIn("C8", failing["pending"])
        self.assertIn("C9", failing["merge"])
        self.assertIn("T3", failing["tasks"])

    def test_merge_running(self):
        close_batch(self.db)
        with mock.patch("module_crew.mergelock.read", return_value={"approval": 12}):
            code, failing = self.ids_failing()
        self.assertEqual((code, failing), (3, {"merge"}))

    def test_codex_needs_module_b(self):
        close_batch(self.db)
        with mock.patch.object(handover, "codex_coordinator_skill", return_value=self.tmp / "missing.md"):
            code, failing = self.ids_failing("codex")
        self.assertEqual((code, failing), (3, {"codex-coordinator-skill"}))
        skill = self.tmp / "SKILL.md"
        skill.write_text("x", encoding="utf-8")
        with mock.patch.object(handover, "codex_coordinator_skill", return_value=skill):
            self.assertEqual(self.ids_failing("codex"), (0, set()))

    def test_check_is_read_only(self):
        before = (store.records(self.db, "session"), len(store.events(self.db)))
        self.check("claude")
        self.assertEqual((store.records(self.db, "session"), len(store.events(self.db))), before)


def _with_extra(real, extra):
    def records(db, kind):
        return {**real(db, kind), **extra.get(kind, {})}
    return records


class CheckCliTest(GapCase):
    def test_cli_json_and_exit(self):
        close_batch(self.db)
        out = self.run_cli("coordinator", "handover", "--check", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(json.loads(out.stdout)["ready"])

    def test_cli_not_ready(self):
        out = self.run_cli("coordinator", "handover", "--check")
        self.assertEqual(out.returncode, 3, out.stderr)
        self.assertIn("还不具备换宿主的条件", out.stdout)

    def test_check_allowed_from_any_session(self):
        close_batch(self.db)
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")
        out = self.run_cli("coordinator", "handover", "--check", env={**os.environ, "CLAUDE_CODE_SESSION_ID": "sid-other"})
        self.assertEqual(out.returncode, 0, out.stderr)


class HandoverTest(GapCase):
    """Acceptance 1–4: the handover itself."""

    def setUp(self):
        super().setUp()
        close_batch(self.db)
        self.skill = self.tmp / "SKILL.md"
        self.skill.write_text("Codex coordinator", encoding="utf-8")

    def to(self, host, original="换到另一边", sid=None, skill=True):
        path = self.skill if skill else self.tmp / "missing.md"
        with mock.patch.object(handover, "codex_coordinator_skill", return_value=path):
            return handover.handover(self.repo, host, original, sid)

    def snapshot(self):
        return store.records(self.db, "session"), len(store.events(self.db))

    def coord(self):
        return store.get(self.db, "session", "shop-coord")

    def test_refusals_write_nothing(self):
        cases = {"same host": ("claude", "换"), "empty original": ("codex", " "), "no module B": ("codex", "换")}
        for name, (host, original) in cases.items():
            with self.subTest(name):
                before = self.snapshot()
                code, lines = self.to(host, original, skill=name != "no module B")
                self.assertEqual(code, 3, lines)
                self.assertEqual(self.snapshot(), before)
        _, lines = self.to("codex", skill=False)
        self.assertTrue(any("模块 B" in l for l in lines), lines)

    def test_not_ready_writes_nothing(self):
        with self.db.transaction(actor="t") as tx:
            rec = tx.get("session", "shop-b")
            tx.put("session", "shop-b", {**rec, "status": "active"}, action="registered")
        before = self.snapshot()
        code, lines = self.to("codex")
        self.assertEqual(code, 3, lines)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(any("shop-b" in l for l in lines))

    def test_to_codex(self):
        code, lines = self.to("codex", "换到 Codex")
        self.assertEqual(code, 0, lines)
        rec = self.coord()
        self.assertEqual(rec["host"], "codex-desktop")
        self.assertEqual({k: rec["hostHandover"][k] for k in ("from", "to", "original", "pending")},
                         {"from": "claude-desktop", "to": "codex-desktop", "original": "换到 Codex", "pending": True})
        ev = [e for e in store.events(self.db) if e["type"] == "session.coordinator-handover"]
        self.assertEqual(ev[-1]["data"]["original"], "换到 Codex")
        guides = sorted((self.db.path / "handover-guide").glob("*.md"))
        self.assertEqual(len(guides), 1)
        text = guides[0].read_text(encoding="utf-8")
        self.assertIn(str(guides[0]), "\n".join(lines))
        for phrase in ("归档", "takeover:true", 'wake:{app:"codex", sessionId:<CODEX_THREAD_ID>}', "--takeover --original-file",
                       "提权", "信任", "每轮", "不带 takeover", "去哪个会话", "做什么", "做完的样子", "shop-coord"):
            self.assertIn(phrase, text)
        original = re.search(r"--original-file ([^`\s]+)", text).group(1)
        self.assertEqual(open(original, encoding="utf-8").read(), "换到 Codex")

    def test_back_to_claude(self):
        self.assertEqual(self.to("codex")[0], 0)
        code, lines = self.to("claude", "换回 Claude")
        self.assertEqual(code, 0, lines)
        rec = self.coord()
        self.assertEqual((rec["host"], rec["hostHandover"]["from"], rec["hostHandover"]["pending"]),
                         ("claude-desktop", "codex-desktop", True))
        text = "\n".join(lines)
        for phrase in ("确认", "已停", 'wake:"auto"', "takeover:true", "--takeover --original-file", "crew-coordinator"):
            self.assertIn(phrase, text)

    def test_other_session_refused_by_guard(self):
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")
        out = self.run_cli("coordinator", "handover", "--to", "claude", "--original", "换",
                           env={**os.environ, "CLAUDE_CODE_SESSION_ID": "sid-other"})
        self.assertEqual(out.returncode, 7, out.stderr)


class HandoverPermissionsTest(PermCase):
    """Acceptance 2, 3 (rules): the integration checkout's rules follow the coordinator's host, appended only."""

    def to(self, host, original="换"):
        skill = self.tmp / "SKILL.md"
        skill.write_text("x", encoding="utf-8")
        with mock.patch.object(handover, "codex_coordinator_skill", return_value=skill):
            return handover.handover(self.repo, host, original)

    def test_to_codex_writes_codex_rules_and_keeps_claude(self):
        permissions.apply(self.repo, "按清单预配权限")
        claude_file = self.repo / ".claude" / "settings.local.json"
        before = claude_file.read_text(encoding="utf-8")
        close_batch(self.db)
        code, lines = self.to("codex")
        self.assertEqual(code, 0, lines)
        rules = self.repo / ".codex" / "rules" / "module-crew.rules"
        self.assertTrue(rules.is_file())
        self.assertIn('decision = "forbidden"', rules.read_text(encoding="utf-8"))
        self.assertEqual(claude_file.read_text(encoding="utf-8"), before)
        record = store.get(self.db, "config", "main")["permissions"]
        self.assertIn(str(rules), record["codexFiles"])
        self.assertTrue(any("信任" in l for l in lines), lines)
        plan = permissions.plan(self.repo)
        self.assertTrue(any("codex" in str(t.get("host")) and t.get("role") == "integration" for t in plan["targets"]))

    def test_back_to_claude_rules_already_there(self):
        permissions.apply(self.repo, "按清单预配权限")
        close_batch(self.db)
        self.assertEqual(self.to("codex")[0], 0)
        code, lines = self.to("claude")
        self.assertEqual(code, 0, lines)
        self.assertTrue(any("已写权限规则" in l or "权限规则已齐" in l for l in lines), lines)

    def test_not_applied_writes_no_rules(self):
        close_batch(self.db)
        code, lines = self.to("codex")
        self.assertEqual(code, 0, lines)
        self.assertFalse((self.repo / ".codex").exists())

    def test_rule_failure_is_reported_not_rolled_back(self):
        permissions.apply(self.repo, "按清单预配权限")
        close_batch(self.db)
        (self.repo / ".gitignore").write_text(".claude/settings.local.json\n", encoding="utf-8")   # .codex no longer ignored
        code, lines = self.to("codex")
        self.assertEqual(code, 0, lines)
        self.assertEqual(store.get(self.db, "session", "shop-coord")["host"], "codex-desktop")
        self.assertTrue(any("权限规则没写上" in l for l in lines), lines)


if __name__ == "__main__":
    unittest.main()
