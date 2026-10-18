import unittest

from helpers import RepoCase

from module_crew import store


def coord(status="active"):
    return {"role": "coordinator", "host": "claude-desktop", "status": status}


def dev(module="crew-store", worktree="/tmp/wt-a", status="active"):
    return {"role": "dev", "host": "claude-desktop", "status": status, "module": module, "worktree": worktree}


class SessionTest(RepoCase):
    def setUp(self):
        super().setUp()
        self.db, _ = store.init_store(self.repo)
        self.put("shop-coord", coord())
        self.put("shop-crew-store", dev())

    def put(self, key, rec):
        with self.db.transaction(actor="shop-coord") as tx:
            tx.put("session", key, rec, action="registered")

    def assert_rejected(self, key, rec):
        before = store.records(self.db, "session")
        with self.assertRaises(store.InvalidSession):
            self.put(key, rec)
        self.assertEqual(store.records(self.db, "session"), before)

    def test_rejections(self):
        cases = {
            "second active coordinator": ("shop-coord2", coord()),
            "second active dev same module": ("shop-crew-store-2", dev(worktree="/tmp/wt-b")),
            "dev without module": ("x", {**dev(), "module": ""}),
            "dev without worktree": ("x", {k: v for k, v in dev(module="m2").items() if k != "worktree"}),
            "relative worktree": ("x", dev(module="m2", worktree="wt")),
            "hub role": ("x", {**coord(), "role": "hub"}),
            "codex coordinator": ("shop-coord2", {**coord(), "host": "codex-desktop"}),   # Codex module sessions are allowed (crew-codex-host)
            "bad status": ("x", {**dev(module="m2"), "status": "paused"}),
        }
        for name, (key, rec) in cases.items():
            with self.subTest(name):
                self.assert_rejected(key, rec)

    def test_retire_then_replace(self):
        self.put("shop-crew-store", dev(status="retired"))
        self.put("shop-crew-store-2", dev(worktree="/tmp/wt-a"))
        sessions = store.records(self.db, "session")
        self.assertEqual(sessions["shop-crew-store"]["status"], "retired")
        self.assertEqual(sessions["shop-crew-store-2"]["status"], "active")
        self.assertEqual(len(store.events(self.db, key="shop-crew-store", kind="session")), 2)

    def test_other_modules_and_retired_coordinator(self):
        self.put("shop-crew-protocol", dev(module="crew-protocol", worktree="/tmp/wt-p"))
        self.put("shop-coord", coord(status="retired"))
        self.put("shop-coord-2", coord())
        self.assertEqual(len(store.records(self.db, "session")), 4)


if __name__ == "__main__":
    unittest.main()
