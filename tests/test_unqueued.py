"""crew-unqueued-commits: commits on the integration branch that did not come through the queue (see the Spec)."""

from __future__ import annotations

import json
import unittest

from helpers import MergeCase, StartCase, git

from module_crew import changes, coordinator, hooks, merge, protocol, review, store, tasks, unqueued

from test_changes import request as change_request   # the function only: its test classes must not be collected twice


def head(repo):
    return git(repo, "rev-parse", "HEAD").strip()


def seen(db):
    return (store.get(db, "config", "main") or {}).get("integrationSeen")


def manual_commit(repo, name="manual.txt", text="x\n"):
    (repo / name).write_text(text, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", f"手动提交 {name}")
    return head(repo)


class SeenTest(MergeCase):
    """Acceptance 1: set at start, moved after each of module-crew's own commits."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def test_set_by_prepare(self):
        self.assertEqual(seen(self.db), head(self.repo))

    def test_set_by_coordinator_up(self):
        other = StartCase("run")
        other.setUp()
        try:
            self.assertEqual(coordinator.up(other.repo, "mall", "升级", session_id="sid")[0], 0)
            self.assertEqual(seen(store.open_store(other.repo)), head(other.repo))
        finally:
            other.doCleanups()

    def test_moved_after_review_approve(self):
        s = review.add(self.db, self.spec_review("b"), "shop-b", 4600).number
        self.assertEqual(review.approve(self.repo, [s], "批准 b 的 Spec").code, 0)
        self.assertEqual(seen(self.db), head(self.repo))

    def test_moved_after_change_land(self):
        n = changes.add(self.db, change_request(["tsconfig.base.json"], stopped="是"), "shop-b", 4700).number
        (self.repo / "tsconfig.base.json").write_text('{"strict": true}\n')
        self.assertEqual(changes.land(self.repo, n).code, 0)
        self.assertEqual(seen(self.db), head(self.repo))

    def test_moved_after_merge_and_tick(self):
        self.approve_final("b", 4800)
        res = merge.run(self.repo, check_command=self.check_script())
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(seen(self.db), head(self.repo))

    def test_not_moved_by_failed_merge(self):
        before = seen(self.db)
        self.approve_final("b", 4801, path="BROKEN")
        res = merge.run(self.repo, check_command=self.check_script(fail_if="BROKEN"))
        self.assertEqual(res.code, 5, res.lines)
        self.assertEqual(seen(self.db), before)


class FindTest(MergeCase):
    """Acceptance 2, 6."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def test_lists_manual_commits(self):
        a = manual_commit(self.repo, "a.txt")
        b = manual_commit(self.repo, "b.txt")
        found = unqueued.find(self.db, self.repo)
        self.assertEqual([c["commit"] for c in found.commits], [b, a])            # newest first
        self.assertEqual(found.commits[0]["subject"], "手动提交 b.txt")
        self.assertEqual(found.commits[0]["author"], "t")
        self.assertTrue(found.commits[0]["at"])
        before = store.events(self.db)
        out = self.run_cli("unqueued")
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn("2 个不经合并队列的提交", out.stdout)
        self.assertIn(b[:7], out.stdout)
        self.assertEqual(len(store.events(self.db)), len(before))
        doc = json.loads(self.run_cli("unqueued", "--json").stdout)
        self.assertEqual(len(doc["commits"]), 2)

    def test_nothing_new(self):
        self.assertEqual(unqueued.find(self.db, self.repo).commits, [])
        self.assertEqual(self.run_cli("unqueued").returncode, 0)

    def test_seen_not_in_history(self):
        manual_commit(self.repo, "a.txt")
        unqueued.mark_integration(self.db, self.repo, "test")
        git(self.repo, "reset", "-q", "--hard", "HEAD~1")
        manual_commit(self.repo, "c.txt")
        found = unqueued.find(self.db, self.repo)
        self.assertTrue(found.not_in_history)
        self.assertEqual(len(found.commits), 1)
        self.assertIn("不在集成分支上", self.run_cli("unqueued").stdout)

    def test_old_project_without_seen(self):
        with self.db.transaction(actor="t") as tx:
            cfg = dict(tx.get("config", "main"))
            cfg.pop("integrationSeen")
            tx.put("config", "main", cfg, action="test")
        manual_commit(self.repo, "a.txt")
        found = unqueued.find(self.db, self.repo)
        self.assertTrue(found.missing_seen)
        self.assertEqual(found.commits, [])
        out = self.run_cli("unqueued")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("记下", out.stdout)
        self.assertEqual(seen(self.db), head(self.repo))


class NotifyTest(MergeCase):
    """Acceptance 3."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")

    def test_notify(self):
        n = tasks.add(self.db, self.repo, "feature", "改文档", "补说明", ["docs/x.md"], "写好", "加说明").number
        d = tasks.dispatch(self.db, self.repo, n)
        hooks.bind(self.db, d.relay, "sid-t", d.worktree)
        top = manual_commit(self.repo, "a.txt")
        sends = unqueued.notify(self.db, self.repo)
        self.assertEqual(sorted(x["to"] for x in sends), sorted(["shop-b", "shop-c", d.relay]))
        task_notice = protocol.parse(open(next(x for x in sends if x["to"] == d.relay)["path"], encoding="utf-8").read())
        self.assertTrue(task_notice.ok, task_notice.problems)
        self.assertEqual(task_notice.contract()["task"], f"T{n}")
        self.assertIn("1 个不经合并队列的提交", open(sends[0]["path"], encoding="utf-8").read())
        self.assertEqual(seen(self.db), top)
        self.assertEqual(self.run_cli("unqueued").returncode, 0)

    def test_cli_notify(self):
        manual_commit(self.repo, "a.txt")
        out = self.run_cli("unqueued", "--notify")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("shop-b", out.stdout)
        self.assertEqual(seen(self.db), head(self.repo))

    def test_skip_rules_match_merge(self):
        self.approve_final("b", 4900)             # b has an open merge approval: no sync notice
        manual_commit(self.repo, "a.txt")
        self.assertEqual([x["to"] for x in unqueued.notify(self.db, self.repo)], ["shop-c"])


if __name__ == "__main__":
    unittest.main()
