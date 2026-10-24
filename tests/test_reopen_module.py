"""crew-reopen-module: reopen a finished module that spec-guard reopened in place (spec/crew-reopen-module.md)."""

import unittest

from helpers import RepoCase

from module_crew import store


def dev(module, worktree="/tmp/w", status="active", **kw):
    return {"role": "dev", "host": "claude-desktop", "status": status, "module": module, "worktree": worktree, **kw}


class StoreReopenTest(RepoCase):
    def setUp(self):
        super().setUp()
        self.db, _ = store.init_store(self.repo)

    def put(self, key, rec):
        with self.db.transaction(actor="t") as tx:
            tx.put("session", key, rec, action="registered")

    def test_reopen_field_accepted(self):
        self.put("shop-x-r2", dev("x", reopen={"round": 2, "since": 7, "review": {"spec": "approved", "plan": "pending"}}))
        self.assertEqual(store.get(self.db, "session", "shop-x-r2")["reopen"]["since"], 7)

    def test_reopen_field_shape_checked(self):
        bad = [{"round": 1, "since": 7, "review": {"spec": "a", "plan": "b"}},
               {"round": 2, "since": 0, "review": {"spec": "a", "plan": "b"}},
               {"round": 2, "since": 7, "review": {"spec": "a"}},
               {"round": True, "since": 7, "review": {"spec": "a", "plan": "b"}},
               "r2"]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(store.InvalidSession):
                self.put("shop-x-r2", dev("x", reopen=value))

    def test_reopen_only_for_dev(self):
        with self.assertRaises(store.InvalidSession):
            self.put("shop-coord", {"role": "coordinator", "host": "claude-desktop", "status": "active",
                                    "reopen": {"round": 2, "since": 7, "review": {"spec": "a", "plan": "b"}}})

    def test_round_since(self):
        self.put("shop-x", dev("x", status="retired"))
        self.put("shop-y", dev("y"))
        sessions = store.records(self.db, "session")
        self.assertEqual(store.round_since(sessions, "x"), 0)
        self.assertEqual(store.round_since(sessions, "y"), 0)
        self.put("shop-x-r2", dev("x", reopen={"round": 2, "since": 9, "review": {"spec": "approved", "plan": "approved"}}))
        sessions = store.records(self.db, "session")
        self.assertEqual(store.round_since(sessions, "x"), 9)
        self.assertEqual(store.round_since(sessions, "y"), 0)
        self.assertEqual(store.round_since(sessions, "z"), 0)


if __name__ == "__main__":
    unittest.main()
