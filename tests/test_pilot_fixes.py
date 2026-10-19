"""crew-pilot-fixes: review originals, approval bookkeeping, own wait records, prompt reminders (spec/crew-pilot-fixes.md)."""

import hashlib
import unittest

from helpers import MergeCase

from module_crew import protocol, review, sources, store


def conclusion(verdict="通过", extra="", ref="R-7", node="Spec", module="b"):
    return (f"【审查结论】\n审查编号：{ref}\n节点：{node}\n模块：{module}\n送审方：shop-b\n结论：{verdict}\n"
            f"来自：arch\n要点：接口清楚。\n{extra}")


CHANGES = "须修改：\n1. 错误码表缺两项\n"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ReviewShowTest(MergeCase):
    """Task 3: `review show C<N>` gives the review originals; notices point at it (Spec acceptance 6, 7)."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        sources.add(self.db, "arch", "lead", "登记审查会话")

    def test_rounds_in_order_with_sha(self):
        n = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        first = conclusion("有须修改项1条", CHANGES, ref="R-7")
        res = review.note(self.db, n, "arch", first)
        [rework] = res.sends
        todo = protocol.parse(store.read_body(self.db, rework["body"]))
        self.assertTrue(todo.ok, todo.problems)
        self.assertIn(f"审查原文：module-crew review show C{n}", todo.fields["要你做什么"])
        second = conclusion("通过，附建议1条", ref="R-8")
        with self.db.transaction(actor="t") as tx:               # a second round on the same item
            rec = tx.get("item", str(n))
            tx.put("item", str(n), dict(rec, reviews=rec["reviews"] + [dict(rec["reviews"][0], ref="R-8", text=second)]),
                   action="review-noted")
        lines = review.show(self.db, n)
        text = "\n".join(lines)
        self.assertLess(text.index("R-7"), text.index("R-8"))
        self.assertIn(f"sha256:{sha(first)}", text)
        self.assertIn(f"sha256:{sha(second)}", text)
        self.assertIn(first.strip(), text)

    def test_no_conclusion_submission_and_bad_number(self):
        n = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        self.assertEqual(review.show(self.db, n), [f"C{n} 还没有审查结论"])
        text = "\n".join(review.show(self.db, n, submission=True))
        self.assertIn("交审原文", text)
        self.assertIn(store.get(self.db, "item", str(n))["text"].strip(), text)
        with self.assertRaises(review.ShowRefused):
            review.show(self.db, 9999)
        approval = self.approve_final("c", 5)
        with self.assertRaises(review.ShowRefused):
            review.show(self.db, approval)                          # a merge approval, not a submission

    def test_start_notice_points_at_reviewed_submissions(self):
        s = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        review.note(self.db, s, "arch", conclusion("通过，附建议1条"))
        p = review.add(self.db, self.plan_review("b"), "shop-b", 2).number
        res = review.approve(self.repo, [s, p], "批")
        [notice] = [x for x in res.sends if x["kind"] == "coordination-notice"]
        msg = protocol.parse(store.read_body(self.db, notice["body"]))
        self.assertTrue(msg.ok, msg.problems)
        self.assertIn(f"审查原文：module-crew review show C{s}", msg.fields["要你做什么"])
        self.assertNotIn(f"review show C{p}", msg.fields["要你做什么"])      # no conclusion on the Plan

    def test_cli(self):
        n = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        review.note(self.db, n, "arch", conclusion())
        out = self.run_cli("review", "show", f"C{n}", cwd=self.wt["b"])
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("R-7", out.stdout)
        self.assertEqual(self.run_cli("review", "show", "C9999").returncode, 3)


if __name__ == "__main__":
    unittest.main()
