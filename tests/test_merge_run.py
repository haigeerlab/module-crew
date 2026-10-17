import unittest

from helpers import START_MAP, MergeCase, git

from module_crew import merge, protocol, review, store


class ApproveQueueTest(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def test_approve_records_and_replies(self):
        n = review.add(self.db, self.finish("b"), "shop-b", 4800).number
        res = merge.approve(self.db, n, "b 验收通过")
        rec = store.get(self.db, "item", str(res.approval))
        self.assertEqual((rec["kind"], rec["state"], rec["module"], rec["review"]), ("merge-approval", "open", "b", n))
        self.assertEqual(rec["commit"], git(self.wt["b"], "rev-parse", "HEAD").strip())
        self.assertEqual(rec["answer"]["original"], "b 验收通过")
        self.assertEqual(store.get(self.db, "item", str(n))["closedReason"], "answered")
        reply = protocol.parse(store.read_body(self.db, res.reply.body))
        self.assertTrue(reply.ok)
        self.assertEqual(res.reply.reply_to, 4800)

    def test_approve_refusals(self):
        spec = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        with self.assertRaises(merge.AnswerRefused):
            merge.approve(self.db, spec, "批")
        n = review.add(self.db, self.finish("b"), "shop-b", 2).number
        merge.approve(self.db, n, "批")
        with self.assertRaises(merge.AnswerRefused):
            merge.approve(self.db, n, "再批")

    def test_queue_in_build_order(self):
        self.approve_final("c", 10)
        self.approve_final("b", 11)
        self.assertEqual([r["module"] for _, r in merge.queue(self.repo)], ["b", "c"])
