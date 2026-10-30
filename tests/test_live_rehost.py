"""crew-live-rehost: move an unfinished batch from Codex to Claude Code in one step (see the Spec)."""

import unittest

from helpers import RepoCase

from module_crew import store


def rehost(**extra):
    return {"from": "codex-desktop", "at": store.now(), "original": "迁到 Claude，旧会话已停，确认码 ABC234", "batch": 7, **extra}


def dev_rehost(**extra):
    return rehost(**{"snapshot": {"head": "a" * 40, "dirty": [" M a.py", "?? b.txt"]}, "inventory": "pending", **extra})


class StoreRehostTest(RepoCase):
    """Task 1: the store accepts the rehost record and previousSessions reasons, and rejects bad ones."""

    def setUp(self):
        super().setUp()
        self.db, _ = store.init_store(self.repo)
        self.wt = str(self.repo.parent / "wt-a")

    def put(self, key, rec):
        with self.db.transaction(actor="t") as tx:
            tx.put("session", key, rec, action="registered")

    def dev(self, **extra):
        return {"role": "dev", "host": "claude-desktop", "status": "active", "module": "a", "worktree": self.wt, **extra}

    def coord(self, **extra):
        return {"role": "coordinator", "host": "claude-desktop", "status": "active", **extra}

    def test_dev_with_rehost_accepted(self):
        self.put("shop-a", self.dev(rehost=dev_rehost()))
        self.assertEqual(store.get(self.db, "session", "shop-a")["rehost"]["inventory"], "pending")

    def test_coordinator_rehost_without_snapshot_accepted(self):
        self.put("shop-coord", self.coord(rehost=rehost()))
        self.assertEqual(store.get(self.db, "session", "shop-coord")["rehost"]["batch"], 7)

    def test_previous_session_reason_accepted(self):
        prev = [{"sessionId": "old-codex", "at": store.now(), "reason": "rehost"}]
        self.put("shop-a", self.dev(previousSessions=prev))
        self.assertEqual(store.get(self.db, "session", "shop-a")["previousSessions"][0]["reason"], "rehost")

    def test_bad_rehost_records(self):
        cases = {
            "not a dict": ("dev", "codex"),
            "from claude": ("dev", dev_rehost(**{"from": "claude-desktop"})),
            "empty original": ("dev", dev_rehost(original=" ")),
            "batch zero": ("dev", dev_rehost(batch=0)),
            "at missing": ("dev", {k: v for k, v in dev_rehost().items() if k != "at"}),
            "dev without snapshot": ("dev", rehost(inventory="pending")),
            "dirty not list": ("dev", dev_rehost(snapshot={"head": "x", "dirty": "M a"})),
            "bad inventory": ("dev", dev_rehost(inventory="done")),
            "coordinator with inventory": ("coordinator", rehost(inventory="pending")),
        }
        for name, (role, rec) in cases.items():
            with self.subTest(name):
                with self.assertRaises(store.InvalidSession):
                    self.put("x", self.dev(rehost=rec) if role == "dev" else self.coord(rehost=rec))

    def test_bad_previous_reason(self):
        with self.assertRaises(store.InvalidSession):
            self.put("shop-a", self.dev(previousSessions=[{"sessionId": "s", "at": store.now(), "reason": ""}]))


if __name__ == "__main__":
    unittest.main()
