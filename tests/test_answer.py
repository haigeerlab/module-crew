import unittest

from helpers import RepoCase, seed_sessions, wait_user

from module_crew import inbox, probe, protocol, store


def files(db):
    return {str(p): p.read_bytes() for p in db.path.rglob("*") if p.is_file() and p.name != ".lock"}


class AnswerTest(RepoCase):
    def setUp(self):
        super().setUp()
        self.db, _ = store.init_store(self.repo)
        seed_sessions(self.db)
        self.n = inbox.add(self.db, wait_user(), "shop-a", 4540).number

    def test_body_matches_render_and_item_closed(self):
        reply = inbox.answer(self.db, self.n, "1 A 就这么办", option="A")
        item = store.get(self.db, "item", str(self.n))
        expected = protocol.render_user_reply(item=self.n, original="1 A 就这么办", answered_at=item["answer"]["answeredAt"],
                                              option_text="A：方案甲", source_relay_id=4540)
        self.assertEqual(store.read_body(self.db, reply.body), expected)
        self.assertEqual((item["state"], item["closedReason"]), ("closed", "answered"))
        self.assertEqual(item["answer"]["original"], "1 A 就这么办")
        self.assertEqual(item["answer"]["body"], reply.body)
        self.assertEqual((reply.to, reply.reply_to), ("shop-a", 4540))
        self.assertTrue(reply.path.is_absolute() and reply.path.exists())

    def test_rejections_leave_store_unchanged(self):
        before = files(self.db)
        for kwargs in (dict(number=99, original="x"), dict(number=self.n, original="x", option="C")):
            with self.subTest(kwargs), self.assertRaises(inbox.AnswerRefused):
                inbox.answer(self.db, **kwargs)
        self.assertEqual(files(self.db), before)
        inbox.answer(self.db, self.n, "好")
        before = files(self.db)
        with self.assertRaises(inbox.AnswerRefused):
            inbox.answer(self.db, self.n, "再答一次")
        self.assertEqual(files(self.db), before)

    def test_cli_with_original_file_keeps_multiline(self):
        original = "先别上线\n  等我看过页面\n\n再说 \"引号\" $HOME `x`"
        f = self.tmp / "orig.txt"
        f.write_text(original, encoding="utf-8")
        r = self.run_cli("answer", str(self.n), "--original-file", str(f))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("收件人：shop-a", r.stdout)
        self.assertIn("replyTo：4540", r.stdout)
        item = store.get(self.db, "item", str(self.n))
        self.assertEqual(item["answer"]["original"], original)
        body = store.read_body(self.db, item["answer"]["body"])
        self.assertEqual(protocol.parse(body).fields["用户原话"], original)
        self.assertEqual(self.run_cli("answer", str(self.n), "--original", "x").returncode, 3)

    def test_status_open_counts_follow(self):
        def open_items():
            return probe.summarize_store(self.repo)[1]["open"]["item"]
        self.assertEqual(open_items(), 1)
        inbox.answer(self.db, self.n, "好")
        self.assertEqual(open_items(), 0)


if __name__ == "__main__":
    unittest.main()
