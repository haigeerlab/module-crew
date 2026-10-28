"""crew-final-accept-split: accepting a final acceptance without authorizing the merge (spec/crew-final-accept-split.md)."""

import unittest

from helpers import MergeCase, git

from module_crew import merge, protocol, review, store


class AcceptCase(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def final(self, m: str, rid: int) -> int:
        out = review.add(self.db, self.finish(m), f"shop-{m}", rid)
        assert out.code == 0, out.lines
        return out.number


class AcceptTest(AcceptCase):
    """AC1, AC3."""

    def test_accept_keeps_item_open_and_unqueued(self):
        n = self.final("b", 4800)
        head = git(self.repo, "rev-parse", "HEAD").strip()
        res = merge.accept(self.db, n, "有限验收通过，暂不合并")
        rec = store.get(self.db, "item", str(n))
        self.assertEqual(rec["state"], "accepted")
        self.assertEqual(rec["acceptance"]["original"], "有限验收通过，暂不合并")
        self.assertEqual(merge.queue(self.repo), [])
        self.assertFalse(any(v.get("kind") == "merge-approval" for v in store.records(self.db, "item").values()))
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), head)
        reply = protocol.parse(store.read_body(self.db, res.body))
        self.assertTrue(reply.ok, reply.problems)
        self.assertEqual(reply.kind, "user-reply")
        self.assertEqual(res.reply_to, 4800)
        self.assertEqual(rec["acceptance"]["body"], res.body)

    def test_refusals_write_nothing(self):
        spec = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        with self.assertRaises(merge.AnswerRefused):
            merge.accept(self.db, spec, "验收")
        n = self.final("b", 2)
        merge.accept(self.db, n, "验收")
        with self.assertRaises(merge.AnswerRefused) as cm:
            merge.accept(self.db, n, "再验收")
        self.assertIn("merge approve", str(cm.exception))
        c = self.final("c", 3)
        merge.approve(self.db, c, "批")
        with self.assertRaises(merge.AnswerRefused):          # closed
            merge.accept(self.db, c, "验收")

    def test_many_all_or_nothing(self):
        b = self.final("b", 1)
        spec = review.add(self.db, self.spec_review("c"), "shop-c", 2).number
        with self.assertRaises(merge.AnswerRefused):
            merge.accept_many(self.db, [b, spec], "验收")
        self.assertEqual(store.get(self.db, "item", str(b))["state"], "open")

    def test_unanswered_question_refused(self):
        n = self.final("b", 1)
        with self.db.transaction(actor="t") as tx:            # a timed-out review asks the user D1
            tx.put("item", str(n), dict(tx.get("item", str(n)), sentAt="2026-01-01T00:00:00+08:00"), action="aged")
        out = self.run_cli("merge", "accept", f"C{n}", "--original", "只验收", cwd=self.repo)
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn("没答全", out.stdout)
        self.assertEqual(store.get(self.db, "item", str(n))["state"], "open")
        out = self.run_cli("merge", "accept", f"C{n}", "--original", f"只验收；C{n}-1 A", cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(store.get(self.db, "item", str(n))["state"], "accepted")

    def test_cli(self):
        n = self.final("b", 1)
        out = self.run_cli("merge", "accept", f"C{n}", "--original", "只验收不合并", cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn(f"C{n} 已接受验收，暂不合并", out.stdout)
        self.assertIn("收件人：shop-b", out.stdout)
        self.assertEqual(store.get(self.db, "item", str(n))["state"], "accepted")
        again = self.run_cli("merge", "accept", f"C{n}", "--original", "再验收", cwd=self.repo)
        self.assertEqual(again.returncode, 3)


if __name__ == "__main__":
    unittest.main()
