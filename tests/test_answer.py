import unittest

from helpers import RepoCase, ReviewCase, seed_sessions, wait_user

from module_crew import inbox, probe, protocol, review, store


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
                                              option_text="A：方案甲", source_relay_id=4540, crew=True)
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


class AnswerNewTest(RepoCase):
    """S79: the user approved directly, no 【等待用户】 was ever recorded (answer --new)."""

    def setUp(self):
        super().setUp()
        self.db, _ = store.init_store(self.repo)
        seed_sessions(self.db)
        self.orig = self.tmp / "orig.txt"
        self.orig.write_text("同意方案甲，按 answer --new 做", encoding="utf-8")

    def test_creates_closed_item_and_reply_passes_protocol_check(self):
        r = self.run_cli("answer", "--new", "--to", "shop-a", "--about", "批准方案甲", "--original-file", str(self.orig))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("收件人：shop-a", r.stdout)
        self.assertNotIn("replyTo", r.stdout)
        (key, item), = [(k, v) for k, v in store.records(self.db, "item").items() if v.get("kind") == "direct-answer"]
        self.assertEqual((item["state"], item["closedReason"], item["to"], item["about"]),
                         ("closed", "answered", "shop-a", "批准方案甲"))
        self.assertEqual(item["answer"]["original"], "同意方案甲，按 answer --new 做")
        body = store.read_body(self.db, item["answer"]["body"])
        msg = protocol.parse(body)
        self.assertTrue(msg.ok, msg.problems)
        self.assertIn(f"事项：C{key}", body)
        self.assertIn(f"已建已结事项 C{key}（批准方案甲）", r.stdout)
        self.assertEqual(msg.fields["答复时间"], item["answer"]["answeredAt"])
        path = next(line.split("：", 1)[1] for line in r.stdout.splitlines() if line.startswith("正文文件："))
        check = self.run_cli("protocol", "check", path)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_refusals_exit_3_and_leave_store_unchanged(self):
        before = files(self.db)
        empty = self.tmp / "empty.txt"
        empty.write_text("  \n", encoding="utf-8")
        for to, f in (("shop-a", empty), ("shop-old", self.orig), ("nobody", self.orig)):
            with self.subTest(to=to, f=f.name):
                r = self.run_cli("answer", "--new", "--to", to, "--about", "x", "--original-file", str(f))
                self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        r = self.run_cli("answer", "--new", "--to", "shop-a", "--about", " ", "--original-file", str(self.orig))
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(files(self.db), before)

    def test_new_and_number_are_exclusive(self):
        self.assertEqual(self.run_cli("answer", "5", "--new", "--to", "shop-a", "--about", "x",
                                      "--original", "好").returncode, 2)
        self.assertEqual(self.run_cli("answer", "--original", "好").returncode, 2)
        self.assertEqual(self.run_cli("answer", "--new", "--about", "x", "--original", "好").returncode, 2)


if __name__ == "__main__":
    unittest.main()


class AnswerReviewRefusedTest(ReviewCase):
    """S81: a 【交审】 item must go through review approve / review answer, or no approval is recorded."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def test_answer_on_review_item_exits_3_and_store_unchanged(self):
        n = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        before = files(self.db)
        r = self.run_cli("answer", str(n), "--original", "批准")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn(f"review approve C{n}", r.stderr)
        self.assertIn(f"review answer C{n}", r.stderr)
        self.assertEqual(files(self.db), before)
        self.assertEqual(store.get(self.db, "item", str(n))["state"], "open")
