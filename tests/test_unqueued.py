"""crew-unqueued-commits: commits on the integration branch that did not come through the queue (see the Spec)."""

from __future__ import annotations

import json
import unittest

from helpers import MergeCase, StartCase, git

from module_crew import changes, coordinator, merge, review, store

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


if __name__ == "__main__":
    unittest.main()
