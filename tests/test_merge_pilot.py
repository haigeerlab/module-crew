"""Fixes from the stage-7 pilot (docs/pilot-report.md): sync recipients, final-acceptance tick, multi approve."""

import unittest

from helpers import MergeCase, git

from module_crew import merge, review, start, store


def todo(wt, m, *items):
    path = wt / "tasks" / m / "todo.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# Todo: {m}\n\n" + "".join(f"- [{'x' if done else ' '}] {text}\n" for done, text in items),
                    encoding="utf-8")


class PilotCase(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        self.check = self.check_script(fail_if="fail.flag")

    def open_d(self):
        res = start.prepare(self.repo, ["d"], "开 d")
        assert res.code == 0, res.lines
        self.wt["d"] = res.prepared[0]["worktree"]

    def main_todo(self, m):
        return (self.repo / "tasks" / m / "todo.md").read_text(encoding="utf-8")


class SyncRecipientsTest(PilotCase):
    def test_skip_queued_and_merged_modules(self):
        self.open_d()
        self.approve_final("b", 1)
        self.approve_final("c", 2)
        first = merge.run(self.repo, self.check)
        self.assertEqual(first.code, 0, first.lines)
        sync = {x["to"] for x in first.sends if x["kind"] == "sync-baseline"}
        self.assertEqual(sync, {"shop-d"})
        second = merge.run(self.repo, self.check)
        self.assertEqual(second.code, 0, second.lines)
        sync = {x["to"] for x in second.sends if x["kind"] == "sync-baseline"}
        self.assertEqual(sync, {"shop-d"})


class TickTest(PilotCase):
    def test_single_unchecked_item_is_ticked_on_integration(self):
        todo(self.wt["b"], "b", (True, "Task 1"), (False, "最终验收（gate）"))
        self.approve_final("b", 1)
        res = merge.run(self.repo, self.check)
        self.assertEqual(res.code, 0, res.lines)
        self.assertIn("- [x] 最终验收（gate）", self.main_todo("b"))
        self.assertIn("勾选 b 的最终验收", git(self.repo, "log", "-1", "--format=%s"))
        self.assertEqual(git(self.repo, "rev-parse", "HEAD^").strip(), res.merge_commit)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_nothing_or_several_unchecked(self):
        todo(self.wt["b"], "b", (True, "Task 1"), (True, "最终验收"))
        todo(self.wt["c"], "c", (False, "Task 1"), (False, "最终验收"))
        self.approve_final("b", 1)
        self.approve_final("c", 2)
        res = merge.run(self.repo, self.check)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), res.merge_commit)
        res = merge.run(self.repo, self.check)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), res.merge_commit)
        self.assertTrue(any("2 个未勾项" in line for line in res.lines), res.lines)
        self.assertNotIn("- [x] 最终验收", self.main_todo("c"))

    def test_no_tick_when_returned(self):
        todo(self.wt["b"], "b", (False, "最终验收"))
        self.approve_final("b", 1, path="fail.flag")
        res = merge.run(self.repo, self.check)
        self.assertEqual(res.code, 5)
        self.assertNotIn("勾选", git(self.repo, "log", "-3", "--format=%s"))


class TickCommandTest(PilotCase):
    def test_tick_after_old_merge(self):
        todo(self.wt["b"], "b", (False, "最终验收"))
        self.approve_final("b", 1)
        n = merge.queue(self.repo)[0][0]
        # simulate a merge made before this fix: merge by hand, close the approval as merged
        git(self.repo, "merge", "-q", "--no-ff", "--no-edit", "b")
        with self.db.transaction(actor="t") as tx:
            tx.put("item", str(n), dict(tx.get("item", str(n)), state="closed", closedReason="merged"), action="merged")
        with self.assertRaises(merge.AnswerRefused):
            merge.tick(self.repo, "b", " ")
        with self.assertRaises(merge.AnswerRefused):
            merge.tick(self.repo, "c", "补勾 c")
        line = merge.tick(self.repo, "b", "补勾 b")
        self.assertIn("勾选 b", line)
        self.assertIn("- [x] 最终验收", self.main_todo("b"))
        self.assertEqual(store.events(self.db, key=str(n))[-1]["type"], "item.ticked")
        with self.assertRaises(merge.AnswerRefused):
            merge.tick(self.repo, "b", "再补一次")

    def test_cli(self):
        out = self.run_cli("merge", "tick", "b", "--original", "补勾", cwd=self.repo)
        self.assertEqual(out.returncode, 3)


class MultiApproveTest(PilotCase):
    def test_two_numbers(self):
        b = review.add(self.db, self.finish("b"), "shop-b", 10).number
        c = review.add(self.db, self.finish("c"), "shop-c", 11).number
        res = merge.approve_many(self.db, [b, c], "都批准")
        self.assertEqual([r.reply.to for r in res], ["shop-b", "shop-c"])
        self.assertEqual(len(merge.queue(self.repo)), 2)

    def test_one_bad_writes_nothing(self):
        b = review.add(self.db, self.finish("b"), "shop-b", 10).number
        before = store.events(self.db)
        with self.assertRaises(merge.AnswerRefused):
            merge.approve_many(self.db, [b, 999], "都批准")
        self.assertEqual(store.events(self.db), before)

    def test_cli_accepts_several(self):
        b = review.add(self.db, self.finish("b"), "shop-b", 10).number
        c = review.add(self.db, self.finish("c"), "shop-c", 11).number
        out = self.run_cli("merge", "approve", str(b), str(c), "--original", "都批准", cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.count("收件人："), 2)


class BatchOutputTest(PilotCase):
    def test_says_none_explicitly(self):
        review.add(self.db, self.spec_review("b"), "shop-b", 30)
        out = self.run_cli("review", "batch", cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("依赖：全部就绪", out.stdout)
        self.assertIn("并行边界重叠：无", out.stdout)


if __name__ == "__main__":
    unittest.main()
