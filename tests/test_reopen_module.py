"""crew-reopen-module: reopen a finished module that spec-guard reopened in place (spec/crew-reopen-module.md)."""

import copy
import json
import unittest

from helpers import START_MAP, RepoCase, StartCase, git

from module_crew import start, store


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


def reopened_map(review=("approved", "approved"), **over):
    """START_MAP where the finished module `a` was reopened in place by spec-guard."""
    doc = copy.deepcopy(START_MAP)
    a = doc["modules"][0]
    a.update({"status": "in_progress", "worktree": None, "progress": {"done": 3, "total": 4},
              "firstTickAt": "2026-10-01T10:00:00+08:00", "review": {"spec": review[0], "plan": review[1]}})
    a.update(over)
    return doc


class ReopenCase(StartCase):
    """`a` was built and merged by an earlier round: retired session shop-a, a merged merge approval, branch a."""

    def setUp(self):
        super().setUp()
        self.set_map(reopened_map())
        git(self.repo, "branch", "a")
        (self.repo / "more.txt").write_text("y\n")
        git(self.repo, "add", "more.txt")
        git(self.repo, "commit", "-q", "-m", "later")
        self.db, _ = store.init_store(self.repo)
        with self.db.transaction(actor="t") as tx:
            tx.put("session", "shop-a", dev("a", str(self.tmp / "repo-crew" / "a"), status="retired"), action="registered")
            n = tx.allocate_number()
            tx.put("item", str(n), {"state": "closed", "kind": "merge-approval", "module": "a", "closedReason": "merged",
                                    "from": "shop-a", "relayId": None}, action="merged")

    def snapshot(self):
        files = {str(p): p.read_bytes() for p in self.repo.rglob("*") if p.is_file() and ".git/index" not in str(p)}
        return (files, git(self.repo, "branch", "--list", "-v"), git(self.repo, "worktree", "list"),
                sorted(str(p) for p in self.tmp.iterdir()))

    def refused(self, words, modules=("a",)):
        before = self.snapshot()
        res = start.prepare(self.repo, list(modules), "重开 a", short="shop")
        self.assertEqual(res.code, 3, res.lines)
        self.assertIn(words, " ".join(res.lines))
        self.assertEqual(self.snapshot(), before)
        return res


class ValidateReopenTest(ReopenCase):
    def test_old_branch_not_ancestor(self):
        sha = git(self.repo, "commit-tree", "HEAD^{tree}", "-p", "a", "-m", "side").strip()
        git(self.repo, "update-ref", "refs/heads/a", sha)
        self.refused("1 个提交没合进集成分支")

    def test_old_branch_checked_out(self):
        git(self.repo, "worktree", "add", "-q", str(self.tmp / "elsewhere"), "a")
        self.refused("正被别的 worktree 检出")

    def test_criteria(self):
        cases = [({"status": "done"}, "不是 in_progress"), ({"worktree": "/x/a"}, "已被 checkout"),
                 ({"progress": {"done": 4, "total": 4}}, "没有未勾的项"), ({"firstTickAt": None}, "以前没勾过")]
        for over, words in cases:
            with self.subTest(words):
                self.set_map(reopened_map(**over))
                self.refused(words)

    def test_old_session_still_in_use(self):
        with self.db.transaction(actor="t") as tx:
            tx.put("session", "shop-a", dev("a", str(self.tmp / "repo-crew" / "a")), action="registered")
        self.refused("旧会话 shop-a 还在用，先 merge cleanup a")


class PrepareReopenTest(ReopenCase):
    def test_fast_forward_and_register(self):
        res = start.prepare(self.repo, ["a"], "重开 a", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        main = git(self.repo, "rev-parse", "main").strip()
        self.assertEqual(git(self.repo, "rev-parse", "a").strip(), main)
        wt = self.tmp / "repo-crew" / "a"
        self.assertEqual(git(wt, "rev-parse", "--abbrev-ref", "HEAD").strip(), "a")
        rec = store.get(self.db, "session", "shop-a-r2")
        self.assertEqual(rec["reopen"], {"round": 2, "since": res.approval, "review": {"spec": "approved", "plan": "approved"}})
        self.assertEqual(rec["worktree"], str(wt))
        self.assertEqual(store.get(self.db, "item", str(res.approval))["reopened"], ["a"])
        text = " ".join(res.lines)
        self.assertIn("按重开处理（第 2 轮）", text)
        self.assertIn("旧分支已快进", text)
        self.assertEqual(res.prepared[0]["reopen"], {"round": 2, "branch": "fast-forward"})

    def test_no_old_branch_created(self):
        git(self.repo, "branch", "-D", "a")
        res = start.prepare(self.repo, ["a"], "重开 a", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        self.assertIn("从集成分支新切", " ".join(res.lines))
        self.assertEqual(res.prepared[0]["reopen"]["branch"], "created")

    def test_third_round_and_first_without_records(self):
        with self.db.transaction(actor="t") as tx:
            tx.put("session", "shop-a-r2", dev("a", "/tmp/r2", status="retired"), action="registered")
        res = start.prepare(self.repo, ["a"], "重开 a", short="shop")
        self.assertEqual(res.prepared[0]["relayName"], "shop-a-r3")

    def test_new_and_reopened_together(self):
        res = start.prepare(self.repo, ["a", "b"], "重开 a，开 b", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        b = store.get(self.db, "session", "shop-b")
        self.assertNotIn("reopen", b)
        self.assertNotIn("reopen", res.prepared[1])
        self.assertEqual(store.get(self.db, "item", str(res.approval))["reopened"], ["a"])
        self.assertNotIn("重开修订", store.read_body(self.db, res.prepared[1]["kickoff"]))

    def test_json_output(self):
        out = self.run_cli("start", "prepare", "a", "--original", "重开 a", "--project-short", "shop", "--json")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        doc = json.loads(out.stdout)
        self.assertEqual(doc["prepared"][0]["reopen"], {"round": 2, "branch": "fast-forward"})


class FreshStoreRoundTest(StartCase):
    def test_round_two_without_records(self):
        self.set_map(reopened_map())
        res = start.prepare(self.repo, ["a"], "重开 a", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(res.prepared[0]["relayName"], "shop-a-r2")


if __name__ == "__main__":
    unittest.main()
