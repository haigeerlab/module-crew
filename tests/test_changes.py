import unittest

from helpers import ReviewCase, git

from module_crew import changes, protocol, store


def request(files, what="改配置", why="模块需要", stopped="否", end="无"):
    lines = "\n".join(files)
    return (f"【公共变更请求】\n结束：{end}\n来自：b\n文件：\n{lines}\n改什么：{what}\n为什么：{why}\n"
            f"是否完全停住：{stopped}\n")


def files(db):
    return {str(p): p.read_bytes() for p in db.path.rglob("*") if p.is_file() and p.name != ".lock"}


class AddTest(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def test_recorded_with_ticket_when_stopped(self):
        out = changes.add(self.db, request(["tsconfig.base.json"], stopped="是"), "shop-b", 4700)
        self.assertEqual(out.code, 0, out.lines)
        rec = store.get(self.db, "request", str(out.number))
        self.assertEqual((rec["state"], rec["files"], rec["fullyStopped"]), ("open", ["tsconfig.base.json"], True))
        ticket = store.get(self.db, "ticket", str(rec["ticket"]))
        self.assertEqual((ticket["from"], ticket["waitingFor"], ticket["state"]), ("shop-b", "shop-coord", "open"))

    def test_not_stopped_no_ticket(self):
        out = changes.add(self.db, request(["a.txt"]), "shop-b", 1)
        self.assertIsNone(store.get(self.db, "request", str(out.number))["ticket"])
        self.assertEqual(store.records(self.db, "ticket"), {})

    def test_rejections_and_repeat(self):
        before = files(self.db)
        for text, sender in ((request(["a"]), "shop-x"), (request(["a"]).replace("为什么：模块需要\n", ""), "shop-b")):
            with self.subTest(sender=sender):
                self.assertEqual(changes.add(self.db, text, sender, 5).code, 3)
        self.assertEqual(files(self.db), before)
        changes.add(self.db, request(["a"]), "shop-b", 6)
        before = files(self.db)
        again = changes.add(self.db, request(["a"]), "shop-b", 6)
        self.assertIn("已记过", " ".join(again.lines))
        self.assertEqual(files(self.db), before)

    def test_hints(self):
        cases = {"package.json": ["dependency"], ".github/workflows/ci.yml": ["ci"],
                 "db/Migrations/001.sql": ["migration"], "README.md": []}
        for path, hints in cases.items():
            with self.subTest(path):
                self.assertEqual(changes.hints_for([path], {}), hints)
        a = changes.add(self.db, request(["tsconfig.base.json"]), "shop-b", 10).number
        out = changes.add(self.db, request(["tsconfig.base.json", "x.txt"]), "shop-c", 11)
        self.assertIn(f"conflict:{a}", store.get(self.db, "request", str(out.number))["hints"])
        self.assertIn(f"conflict:{out.number}", store.get(self.db, "request", str(a))["hints"])
        self.assertIn("要问用户", " ".join(out.lines))

    def test_pending_in_order(self):
        self.assertEqual(changes.pending(self.db), [])
        a = changes.add(self.db, request(["a"]), "shop-b", 1).number
        b = changes.add(self.db, request(["b"]), "shop-c", 2).number
        self.assertEqual([n for n, _ in changes.pending(self.db)], [a, b])


class AnswerTest(ReviewCase):
    def test_declined(self):
        db = store.open_store(self.repo)
        n = changes.add(db, request(["package.json"], stopped="是"), "shop-b", 4700).number
        head = git(self.repo, "rev-parse", "HEAD")
        reply = changes.answer(db, n, "不加这个依赖")
        msg = protocol.parse(store.read_body(db, reply.body))
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual((reply.to, reply.reply_to), ("shop-b", 4700))
        rec = store.get(db, "request", str(n))
        self.assertEqual((rec["state"], rec["closedReason"]), ("closed", "declined"))
        ticket = store.get(db, "ticket", str(rec["ticket"]))
        self.assertEqual((ticket["state"], ticket["closedReason"]), ("closed", 3))
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)
        with self.assertRaises(changes.AnswerRefused):
            changes.answer(db, n, "再答")


if __name__ == "__main__":
    unittest.main()
