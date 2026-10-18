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
        self.assertIn("C1", r.stdout)
        r = self.run_cli("inbox", "add", str(msg), "--from", "shop-x", "--relay-id", "101")
        self.assertEqual(r.returncode, 3)
        r = self.run_cli("inbox", "add", str(self.tmp / "none.txt"), "--from", "shop-a", "--relay-id", "1")
        self.assertEqual(r.returncode, 2)



class TicketCloseTest(RepoCase):
    def setUp(self):
        super().setUp()
        from module_crew import store
        self.db, _ = store.init_store(self.repo)
        seed_sessions(self.db)
        with self.db.transaction(actor="t") as tx:
            self.n = tx.allocate_number()
            tx.put("ticket", str(self.n), {"state": "open", "from": "shop-a", "relayId": 9, "text": "等", "waitingFor": "x",
                                           "what": "补勾", "closedReason": None, "closedBy": None}, action="opened")

    def test_happened_and_user(self):
        from module_crew import store
        inbox.close_ticket(self.db, self.n, "happened", "已在集成分支补勾 1c34665")
        rec = store.get(self.db, "ticket", str(self.n))
        self.assertEqual((rec["state"], rec["closedReason"]), ("closed", 3))
        self.assertEqual(store.events(self.db, key=str(self.n))[-1]["data"]["note"], "已在集成分支补勾 1c34665")
        with self.db.transaction(actor="t") as tx:
            m = tx.allocate_number()
            tx.put("ticket", str(m), dict(rec, state="open", closedReason=None), action="opened")
        inbox.close_ticket(self.db, m, "user", "关掉 #%d" % m)
        self.assertEqual(store.get(self.db, "ticket", str(m))["closedReason"], 4)

    def test_refusals(self):
        from module_crew import store
        before = store.events(self.db)
        for args in ((999, "happened", "x"), (self.n, "happened", " "), (self.n, "other", "x")):
            with self.assertRaises(inbox.AnswerRefused):
                inbox.close_ticket(self.db, *args)
        self.assertEqual(store.events(self.db), before)
        inbox.close_ticket(self.db, self.n, "user", "关掉")
        with self.assertRaises(inbox.AnswerRefused):
            inbox.close_ticket(self.db, self.n, "user", "再关")

    def test_cli(self):
        out = self.run_cli("ticket", "close", str(self.n), "--reason", "happened", "--original", "已补勾", cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        out = self.run_cli("ticket", "close", str(self.n), "--reason", "happened", "--original", "已补勾", cwd=self.repo)
        self.assertEqual(out.returncode, 3)


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


def wait_session(end="无", who="API", what="Mock 数据"):
    return f"【等待其他会话】\n结束：{end}\n在等谁：{who}\n等什么：{what}\n"


class TicketTest(InboxCase):
    def ticket(self, n):
        return store.get(self.db, "ticket", str(n))

    def test_wait_session_opens_ticket(self):
        out = self.add(wait_session(), relay_id=50)
        self.assertEqual(out.code, 0)
        rec = self.ticket(out.number)
        self.assertEqual((rec["state"], rec["waitingFor"], rec["what"], rec["relayId"]), ("open", "API", "Mock 数据", 50))

    def test_new_wait_replaces_old_reason_2(self):
        first = self.add(wait_session(), relay_id=50).number
        out = self.add(wait_session(end=f"#{first}", who="设计"), relay_id=51)
        self.assertEqual(out.closed, [first])
        self.assertEqual((self.ticket(first)["state"], self.ticket(first)["closedReason"]), ("closed", 2))
        self.assertEqual(self.ticket(first)["closedBy"], 51)

    def test_resumed_closes_by_number_and_relay_id_reason_1(self):
        a = self.add(wait_session(), relay_id=60).number
        b = self.add(wait_session(who="设计", end=f"无"), relay_id=61).number
        out = self.add(f"【已恢复】\n结束：#{a}、#61、#999\n继续\n", relay_id=62)
        self.assertEqual(out.code, 0, out.lines)
        self.assertEqual(sorted(out.closed), sorted([a, b]))
        self.assertEqual(out.unmatched, [999])
        self.assertEqual(self.ticket(a)["closedReason"], 1)
        self.assertEqual(self.ticket(b)["closedReason"], 1)

    def test_other_senders_tickets_untouched(self):
        mine = self.add(wait_session(), relay_id=70).number
        theirs = self.add(wait_session(), sender="shop-b", relay_id=71).number
        out = self.add(f"【已恢复】\n结束：#{theirs}\n", relay_id=72)
        self.assertEqual(out.unmatched, [theirs])
        self.assertEqual(self.ticket(theirs)["state"], "open")
        self.assertEqual(self.ticket(mine)["state"], "open")

    def test_number_and_relay_id_collide_store_number_wins(self):
        first = self.add(wait_session(), relay_id=2).number      # ticket #1, relay id 2
        second = self.add(wait_session(who="设计"), relay_id=1).number  # ticket #2, relay id 1
        out = self.add("【已恢复】\n结束：#1\n", relay_id=3)
        self.assertEqual(out.closed, [first])
        self.assertEqual(self.ticket(second)["state"], "open")


class WithdrawAndRepeatTest(InboxCase):
    def test_withdraw_own_item_only(self):
        mine = self.add(wait_user(decide="一"), relay_id=80).number
        theirs = self.add(wait_user(decide="二", sender="b"), sender="shop-b", relay_id=81).number
        out = self.add(f"【撤回】\n事项：#{mine}\n原因：不用了\n", relay_id=82)
        self.assertEqual(out.closed, [mine])
        self.assertEqual(store.get(self.db, "item", str(mine))["closedReason"], "withdrawn")
        out = self.add(f"【撤回】\n事项：#{theirs}\n", relay_id=83)
        self.assertEqual(out.unmatched, [theirs])
        self.assertEqual(store.get(self.db, "item", str(theirs))["state"], "open")

    def test_same_relay_id_twice_is_recorded_once(self):
        cases = [wait_user(), wait_session(), "【已恢复】\n结束：#2\n", "【撤回】\n事项：#1\n"]  # #1 item, #2 ticket
        for i, text in enumerate(cases):
            with self.subTest(i=i):
                self.add(text, relay_id=900 + i)
                before = files(self.db)
                out = self.add(text, relay_id=900 + i)
                self.assertEqual(out.code, 0)
                self.assertIn("已记过", " ".join(out.lines))
                self.assertEqual(files(self.db), before)
