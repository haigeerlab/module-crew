"""crew-hub-bridge outputs: review lines, the 【等待用户】 for the hub, the read-only sessions export."""

import unittest

from helpers import ReviewCase

from module_crew import protocol, review, sources, store


def conclusion(module="b", node="Spec", verdict="通过", ref="R-1"):
    return (f"【审查结论】\n审查编号：{ref}\n节点：{node}\n模块：{module}\n送审方：前端\n结论：{verdict}\n"
            "来自：live-saas-arch-review\n要点：接口清楚。\n")


class HubCase(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        sources.add(self.db, "live-saas-arch-review", "lead", "登记审查会话")
        self.spec = review.add(self.db, self.spec_review("b"), "shop-b", 4001).number
        self.plan = review.add(self.db, self.plan_review("b"), "shop-b", 4002).number


class NoteTest(HubCase):
    def test_note_shows_in_batch(self):
        review.note(self.db, self.spec, "live-saas-arch-review", conclusion())
        items = {i["number"]: i for i in review.batch(self.repo)["items"]}
        self.assertEqual(review._review_text(items[self.spec]), "live-saas-arch-review 通过")
        self.assertEqual(review._review_text(items[self.plan]), "未审查")
        out = self.run_cli("review", "batch", cwd=self.repo).stdout
        self.assertIn("审查：live-saas-arch-review 通过", out)
        self.assertIn("审查：未审查", out)

    def test_note_refused(self):
        before = store.events(self.db)
        for args in ((self.spec, "someone", conclusion()),                       # not a registered reviewer
                     (self.spec, "live-saas-arch-review", "随便写写"),            # not a conclusion
                     (self.spec, "live-saas-arch-review", conclusion(module="c")),  # other module
                     (self.spec, "live-saas-arch-review", conclusion(node="Plan")),  # other node
                     (999, "live-saas-arch-review", conclusion())):
            with self.assertRaises(review.NoteRefused):
                review.note(self.db, *args)
        self.assertEqual(store.events(self.db), before)

    def test_approval_not_blocked_without_review(self):
        self.assertEqual(review.approve(self.repo, [self.spec, self.plan], "批准").code, 0)


class ForHubTest(HubCase):
    def test_wait_user_for_hub(self):
        review.note(self.db, self.spec, "live-saas-arch-review", conclusion())
        n, path, text = review.for_hub(self.repo)
        msg = protocol.parse(path.read_text(encoding="utf-8"))
        self.assertEqual((msg.kind, msg.ok), ("wait-user", True), msg.problems)
        for want in (f"#{self.spec}", f"#{self.plan}", "b 的 Spec", "b 的 Plan", "审查：live-saas-arch-review 通过",
                     "审查：未审查", "架构审查：进行中，请勿先批", "推荐 A：全部批准", "B：只批准部分", "C：都退回修改"):
            self.assertIn(want, text)
        self.assertEqual(store.read_body(self.db, n), text)

    def test_all_reviewed_and_parallel(self):
        review.note(self.db, self.spec, "live-saas-arch-review", conclusion(verdict="通过，附建议2条"))
        review.note(self.db, self.plan, "live-saas-arch-review", conclusion(node="Plan"))
        _, _, text = review.for_hub(self.repo, parallel_with=118)
        msg = protocol.parse(text)
        self.assertTrue(msg.ok, msg.problems)
        self.assertIn(("parallel", 118), msg.markers)
        self.assertIn("架构审查：通过，附建议2条", text)

    def test_cli(self):
        out = self.run_cli("review", "batch", "--for-hub", "--parallel-with", "7", cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("【与 #7 并行】", out.stdout)
        self.assertIn("正文文件", out.stdout)


if __name__ == "__main__":
    unittest.main()
