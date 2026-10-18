"""crew-codex-host: module sessions in Codex desktop (coordinator stays in Claude desktop)."""

import unittest

from helpers import RepoCase

from module_crew import store


class HostRegistryTest(RepoCase):
    def setUp(self):
        super().setUp()
        self.db, _ = store.init_store(self.repo)

    def put(self, key, rec):
        with self.db.transaction(actor="t") as tx:
            tx.put("session", key, rec, action="registered")

    def test_codex_module_session_accepted(self):
        self.put("shop-coord", {"role": "coordinator", "host": "claude-desktop", "status": "active"})
        self.put("shop-b", {"role": "dev", "host": "codex-desktop", "status": "active", "module": "b", "worktree": "/tmp/b"})
        self.assertEqual(store.get(self.db, "session", "shop-b")["host"], "codex-desktop")

    def test_coordinator_must_be_claude(self):
        with self.assertRaises(store.InvalidSession):
            self.put("shop-coord", {"role": "coordinator", "host": "codex-desktop", "status": "active"})
        with self.assertRaises(store.InvalidSession):
            self.put("shop-b", {"role": "dev", "host": "codex-cli", "status": "active", "module": "b", "worktree": "/tmp/b"})


if __name__ == "__main__":
    unittest.main()
