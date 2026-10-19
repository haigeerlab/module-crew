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


if __name__ == "__main__":
    unittest.main()
