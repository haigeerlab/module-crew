"""crew-host-handover: switch the whole crew between Claude Code and Codex in the gap between batches (see the Spec)."""

import json
import os
import unittest
from unittest import mock

from helpers import RepoCase, ReviewCase, StartCase

from module_crew import coordinator, handover, hooks, store


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


if __name__ == "__main__":
    unittest.main()
