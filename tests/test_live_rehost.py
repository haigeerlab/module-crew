"""crew-live-rehost: move an unfinished batch from Codex to Claude Code in one step (see the Spec)."""

import json
import os
import unittest
from unittest import mock

from helpers import RepoCase, ReviewCase, git

from module_crew import hooks, mergelock, rehost as rh, store


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


def as_caller(claude=None, codex=None):
    """Patch the environment so the code sees a Claude session, a Codex thread, or a terminal."""
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")}
    if claude:
        env["CLAUDE_CODE_SESSION_ID"] = claude
    if codex:
        env["CODEX_THREAD_ID"] = codex
    return mock.patch.dict(os.environ, env, clear=True)


def to_codex(db):
    """The crew as LIVE-SAAS has it: coordinator and module sessions all on Codex, each bound to a Codex thread."""
    sessions = store.records(db, "session")
    with db.transaction(actor="t") as tx:
        for name, rec in sessions.items():
            if rec.get("status") != "active":
                continue
            new = {**rec, "host": "codex-desktop", "hostSession": {"sessionId": f"codex-{name}", "boundAt": store.now()}}
            if rec.get("role") == "coordinator":
                new["hostHandover"] = {"from": "claude-desktop", "to": "codex-desktop", "at": store.now(),
                                       "original": "换到 Codex", "pending": False}
            tx.put("session", name, new, action="registered")


class RehostCase(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        to_codex(self.db)

    def check(self, sid=None, cwd=None, **who):
        with as_caller(**who):
            return rh.check(self.repo, cwd or self.repo, sid)


class CheckTest(RehostCase):
    """Task 2 (acceptance 1, 2): the blocking list and the confirmation code."""

    def ids(self, doc):
        return {c["id"]: c["ok"] for c in doc["checks"]}

    def test_ready_gives_code_and_sessions(self):
        (self.wt["b"] / "new.txt").write_text("x", encoding="utf-8")
        code, doc, lines = self.check(claude="sid-new")
        self.assertEqual(code, 0, lines)
        self.assertRegex(doc["code"], r"^[A-Z2-9]{6}$")
        self.assertIn(f"确认码：{doc['code']}", lines)
        row = next(r for r in doc["sessions"] if r["module"] == "b")
        self.assertEqual(row["dirty"], ["?? new.txt"])
        self.assertTrue(row["head"])
        self.assertIn("?? new.txt", "\n".join(lines))
        json.dumps(doc)

    def test_terminal_also_ready(self):
        self.assertEqual(self.check()[0], 0)

    def test_each_blocker(self):
        def coord_claude():
            rec = store.get(self.db, "session", "shop-coord")
            with self.db.transaction(actor="t") as tx:
                tx.put("session", "shop-coord", {k: v for k, v in rec.items() if k != "hostHandover"} | {"host": "claude-desktop"},
                       action="registered")

        def dev_claude():
            rec = store.get(self.db, "session", "shop-b")
            with self.db.transaction(actor="t") as tx:
                tx.put("session", "shop-b", {**rec, "host": "claude-desktop"}, action="registered")

        def offload_running():
            with self.db.transaction(actor="t") as tx:
                tx.put("offload", "b", {"module": "b", "state": "running"}, action="assigned")

        cases = {
            "coordinator-host": (coord_claude, {}),
            "all-codex": (dev_claude, {}),
            "offload": (offload_running, {}),
            "caller": (None, {"codex": "codex-x"}),
            "cwd": (None, {"cwd": self.wt["b"]}),
        }
        for cid, (setup, kw) in cases.items():
            with self.subTest(cid):
                db_before = store.records(self.db, "session")
                if setup:
                    setup()
                cwd = kw.pop("cwd", None)
                code, doc, lines = self.check(cwd=cwd, **kw)
                self.assertEqual(code, 3, lines)
                self.assertIsNone(doc["code"])
                self.assertFalse(self.ids(doc)[cid], doc["checks"])
                with self.db.transaction(actor="t") as tx:     # undo the setup for the next case
                    for n, r in db_before.items():
                        tx.put("session", n, r, action="registered")
                    if cid == "offload":
                        tx.put("offload", "b", {"module": "b", "state": "idle"}, action="assigned")

    def test_bound_caller_refused(self):
        code, doc, _ = self.check(sid="codex-shop-b", claude="codex-shop-b")
        self.assertEqual(code, 3)
        self.assertFalse(self.ids(doc)["caller"])

    def test_merge_lock_blocks(self):
        with mock.patch.object(mergelock, "read", return_value={"running": True, "approval": 9}):
            code, doc, lines = self.check(claude="sid-new")
        self.assertEqual(code, 3)
        self.assertIn("C9", "\n".join(lines))

    def test_spec_guard_missing_blocks(self):
        self.plugins.entries.pop("spec-guard@m")
        self.plugins.write()
        code, doc, _ = self.check(claude="sid-new")
        self.assertEqual(code, 3)
        self.assertFalse(self.ids(doc)["spec-guard"])

    def test_code_stable_then_changes(self):
        first = self.check(claude="sid-new")[1]["code"]
        self.assertEqual(self.check(claude="sid-new")[1]["code"], first)
        (self.wt["c"] / "x.py").write_text("1", encoding="utf-8")
        second = self.check(claude="sid-new")[1]["code"]
        self.assertNotEqual(second, first)
        git(self.wt["c"], "add", "-A")
        git(self.wt["c"], "commit", "-q", "-m", "x")
        third = self.check(claude="sid-new")[1]["code"]
        self.assertNotIn(third, (first, second))
        rec = store.get(self.db, "session", "shop-c")
        with self.db.transaction(actor="t") as tx:
            tx.put("session", "shop-c", {**rec, "hostSession": {"sessionId": "codex-other", "boundAt": store.now()}},
                   action="registered")
        self.assertNotIn(self.check(claude="sid-new")[1]["code"], (first, second, third))

    def test_check_cli_is_read_only_for_any_session(self):
        before = (store.records(self.db, "session"), len(store.events(self.db)))
        env = {k: v for k, v in os.environ.items() if k != "CODEX_THREAD_ID"}
        out = self.run_cli("coordinator", "rehost", "--check", "--json", env={**env, "CLAUDE_CODE_SESSION_ID": "sid-new"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(json.loads(out.stdout)["ready"])
        self.assertEqual((store.records(self.db, "session"), len(store.events(self.db))), before)


if __name__ == "__main__":
    unittest.main()
