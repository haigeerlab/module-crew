"""crew-stage-c-fixes: fewer re-asks and prompts after rehearsal stage C (spec/crew-stage-c-fixes.md)."""

import unittest

from helpers import MergeCase, git

from module_crew import changes, merge, review, store


def change_request(files, sender="b"):
    lines = "\n".join(files)
    return (f"【公共变更请求】\n结束：无\n来自：{sender}\n文件：\n{lines}\n改什么：改配置\n为什么：模块需要\n"
            "是否完全停住：否\n")


class SyncSkipTest(MergeCase):
    """Task 1 (MC-10): a module waiting on its final acceptance gets no sync notice (Spec acceptance 1)."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        self.check = self.check_script()

    def test_summary_scenario(self):
        b_final = review.add(self.db, self.finish("b"), "shop-b", 1).number      # b waits on its final acceptance
        self.approve_final("c", 2)
        res = merge.run(self.repo, self.check)                                    # c merges first
        self.assertEqual(res.code, 0, res.lines)
        self.assertNotIn("shop-b", {x["to"] for x in res.sends if x["kind"] == "sync-baseline"})
        # b's head did not move, so its approval still merges: the user is asked once
        merge.approve(self.db, b_final, "b 验收通过")
        again = merge.run(self.repo, self.check)
        self.assertEqual(again.code, 0, again.lines)

    def test_change_land_skips_but_answers_requester(self):
        review.add(self.db, self.finish("b"), "shop-b", 1)                        # b waits on its final acceptance
        n = changes.add(self.db, change_request(["tsconfig.base.json"], "c"), "shop-c", 4700).number
        (self.repo / "tsconfig.base.json").write_text('{"strict": true}\n')
        res = changes.land(self.repo, n)
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual({x["to"] for x in res.sends}, {"shop-c"})
        # the requester is answered even while its own final acceptance is open
        review.add(self.db, self.finish("c", "VALUE = 'c2'\n"), "shop-c", 3)
        m = changes.add(self.db, change_request(["other.json"], "c"), "shop-c", 4701).number
        (self.repo / "other.json").write_text("{}\n")
        self.assertEqual({x["to"] for x in changes.land(self.repo, m).sends}, {"shop-c"})

    def test_change_land_skips_approved_and_merged(self):
        # 0.9.3 (review finding 8): change land used to skip only open final reviews and suspended modules
        self.approve_final("b", 1)                                               # b approved, waiting in the queue
        n = changes.add(self.db, change_request(["tsconfig.base.json"], "c"), "shop-c", 4700).number
        (self.repo / "tsconfig.base.json").write_text('{"strict": true}\n')
        res = changes.land(self.repo, n)
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual({x["to"] for x in res.sends}, {"shop-c"})
        self.assertEqual(merge.run(self.repo, self.check).code, 0)              # b merges: its head did not move
        m = changes.add(self.db, change_request(["other.json"], "c"), "shop-c", 4701).number
        (self.repo / "other.json").write_text("{}\n")
        self.assertEqual({x["to"] for x in changes.land(self.repo, m).sends}, {"shop-c"})   # merged b: nothing

    def test_one_rule_for_both(self):
        self.approve_final("b", 1)
        with self.db.transaction(actor="t") as tx:
            self.assertEqual(merge.no_sync(tx), {"b"})


class ApprovalSupersedeTest(MergeCase):
    """Task 2 (MC-11): a new merge approval replaces the module's older open one (Spec acceptance 2, 3)."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def open_approval(self, module, n):
        with self.db.transaction(actor="t") as tx:     # an old approval still open (written by an older version)
            tx.put("item", str(n), dict(tx.get("item", str(n)), state="open", closedReason=None), action="t")

    def test_new_approval_replaces_old(self):
        old = self.approve_final("b", 1)
        c_old = self.approve_final("c", 2)
        newer = review.add(self.db, self.finish("b", "VALUE = 'b2'\n"), "shop-b", 3).number   # voids `old` (0.6.0)
        self.open_approval("b", old)
        res = merge.approve(self.db, newer, "b 验收通过")
        rec = store.get(self.db, "item", str(old))
        self.assertEqual((rec["state"], rec["closedReason"], rec["supersededBy"]), ("closed", "superseded", res.approval))
        self.assertEqual(res.superseded, [old])
        self.assertEqual(store.get(self.db, "item", str(c_old))["state"], "open")      # other modules untouched
        queued = [(r["module"], n) for n, r in merge.queue(self.repo)]
        self.assertEqual(sorted(queued), sorted([("b", res.approval), ("c", c_old)]))

    def test_cli_says_replaced(self):
        old = self.approve_final("b", 1)
        newer = review.add(self.db, self.finish("b", "VALUE = 'b2'\n"), "shop-b", 3).number
        self.open_approval("b", old)
        out = self.run_cli("merge", "approve", f"C{newer}", "--original", "b 验收通过")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn(f"合并批准 C{old} 被", out.stdout)


if __name__ == "__main__":
    unittest.main()
