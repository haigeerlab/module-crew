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


class WaitUserTest(InboxCase):
    def item(self, n):
        return store.get(self.db, "item", str(n))

    def test_recorded_with_details(self):
        out = self.add(wait_user(decide="先做哪个"), relay_id=4540)
        self.assertEqual((out.code, out.number), (0, 1))
        rec = self.item(1)
        self.assertEqual(rec["state"], "open")
        self.assertEqual(rec["from"], "shop-a")
        self.assertEqual(rec["relayId"], 4540)
        self.assertEqual(rec["recommended"], "A")
        self.assertTrue(rec["fullyStopped"])
        self.assertEqual([o["letter"] for o in rec["options"]], ["A", "B"])
        self.assertIn("要你决定：先做哪个", rec["text"])

    def test_default_supersede_only_same_sender(self):
        self.add(wait_user(decide="一"), relay_id=1)
        self.add(wait_user(decide="别人的", sender="b"), sender="shop-b", relay_id=2)
        out = self.add(wait_user(decide="二"), relay_id=3)
        self.assertEqual(out.closed, [1])
        self.assertEqual(self.item(1)["state"], "closed")
        self.assertEqual(self.item(1)["closedReason"], "superseded")
        self.assertEqual(self.item(2)["state"], "open")
        self.assertIn("#1 已被新事项自动取代；确实要两项都答，请写【与 #1 并行】重发", out.tell_sender)

    def test_parallel_marker_keeps_old(self):
        self.add(wait_user(decide="一"), relay_id=1)
        out = self.add(wait_user(decide="二", marker="【与 #1 并行】\n"), relay_id=2)
        self.assertEqual(out.closed, [])
        self.assertEqual(self.item(1)["state"], "open")

    def test_explicit_supersede_only_that_one(self):
        self.add(wait_user(decide="一"), relay_id=1)
        self.add(wait_user(decide="二", marker="【与 #1 并行】\n"), relay_id=2)
        out = self.add(wait_user(decide="三", marker="【取代 #2】\n"), relay_id=3)
        self.assertEqual(out.closed, [2])
        self.assertEqual(self.item(1)["state"], "open")

    def test_supersede_by_relay_id(self):
        self.add(wait_user(decide="一"), relay_id=4540)
        out = self.add(wait_user(decide="二", marker="【取代 #4540】\n"), relay_id=4541)
        self.assertEqual(out.closed, [1])

    def test_multiline_and_single_do_not_supersede_each_other(self):
        scope = "适用会话：a、b\n各线范围：\n- a：前端\n- b：后端\n"
        self.add(wait_user(decide="单线"), relay_id=1)
        out = self.add(wait_user(decide="多线", scope=scope), relay_id=2)
        self.assertEqual(out.code, 0, out.lines)
        self.assertEqual(out.closed, [])
        self.assertTrue(self.item(2)["multiline"])
