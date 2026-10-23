"""crew-host-handover: switch the whole crew between Claude Code and Codex in the gap between batches (see the Spec)."""

import os
import unittest
from unittest import mock

from helpers import RepoCase, StartCase

from module_crew import coordinator, store


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


if __name__ == "__main__":
    unittest.main()
