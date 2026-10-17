import unittest

from helpers import RepoCase, seed_sessions, wait_user

from module_crew import inbox, store


def files(db):
    return {str(p): p.read_bytes() for p in db.path.rglob("*") if p.is_file() and p.name != ".lock"}


class InboxCase(RepoCase):
    def setUp(self):
        super().setUp()
        self.db, _ = store.init_store(self.repo)
        seed_sessions(self.db)

    def add(self, text, sender="shop-a", relay_id=100):
        return inbox.add(self.db, text, sender, relay_id)


class RejectTest(InboxCase):
    def assert_rejected(self, text, sender="shop-a", words=None):
        before = files(self.db)
        out = self.add(text, sender)
        self.assertEqual(out.code, 3)
        if words:
            self.assertIn(words, " ".join(out.lines))
        self.assertEqual(files(self.db), before)

    def test_invalid_message(self):
        self.assert_rejected("【等待其他会话】\n结束：无\n在等谁：API\n", words="missing-field:等什么")

    def test_unknown_message(self):
        self.assert_rejected("【催办】\n快点\n", words="unknown-kind")

    def test_unregistered_retired_or_coordinator_sender(self):
        for sender in ("shop-x", "shop-old", "shop-coord"):
            with self.subTest(sender):
                self.assert_rejected(wait_user(), sender=sender, words="登记")

    def test_review_request_and_shared_change_not_recorded_here(self):
        ok = "【交审】\n结束：无\n模块：a\n节点：Spec\n文件：\nspec/a.md sha256:3f2a9c1e7b4d\n要点：\n- 一\n- 二\n"
        before = files(self.db)
        self.assertEqual(self.add(ok).code, 4)
        self.assertEqual(files(self.db), before)
        self.assert_rejected(ok.replace("节点：Spec", "节点：需求"), words="bad-node")


class CliTest(InboxCase):
    def test_cli_exit_codes(self):
        msg = self.tmp / "m.txt"
        msg.write_text(wait_user(), encoding="utf-8")
        r = self.run_cli("inbox", "add", str(msg), "--from", "shop-a", "--relay-id", "100")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("#1", r.stdout)
        r = self.run_cli("inbox", "add", str(msg), "--from", "shop-x", "--relay-id", "101")
        self.assertEqual(r.returncode, 3)
        r = self.run_cli("inbox", "add", str(self.tmp / "none.txt"), "--from", "shop-a", "--relay-id", "1")
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
