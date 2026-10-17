import unittest

from helpers import ReviewCase, git

from module_crew import protocol, review, store


class AnswerTest(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        self.n = review.add(self.db, self.spec_review("b"), "shop-b", 4600).number

    def test_answer_only_replies(self):
        head = git(self.repo, "rev-parse", "HEAD")
        reply = review.answer(self.db, self.n, "第 3 节的接口要改")
        text = store.read_body(self.db, reply.body)
        msg = protocol.parse(text)
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual(msg.fields["用户原话"], "第 3 节的接口要改")
        self.assertEqual((reply.to, reply.reply_to), ("shop-b", 4600))
        rec = store.get(self.db, "item", str(self.n))
        self.assertEqual((rec["state"], rec["closedReason"]), ("closed", "answered"))
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)

    def test_answer_refused(self):
        review.answer(self.db, self.n, "好")
        with self.assertRaises(review.AnswerRefused):
            review.answer(self.db, self.n, "再答")
        with self.assertRaises(review.AnswerRefused):
            review.answer(self.db, 999, "x")


if __name__ == "__main__":
    unittest.main()
