import unittest

from helpers import MergeCase

from module_crew import failure, hooks, inbox, start, store

from helpers import wait_user


class FailureCase(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def session(self, name):
        return store.get(self.db, "session", name)


class SuspendTest(FailureCase):
    def test_suspend_frees_a_slot(self):
        self.assertEqual(start.plan(self.repo).slots, 1)
        failure.suspend(self.db, "b", "等设计稿", "先挂起 b")
        rec = self.session("shop-b")
        self.assertEqual(rec["status"], "active")
        self.assertEqual((rec["suspended"]["reason"], rec["suspended"]["original"]), ("等设计稿", "先挂起 b"))
        self.assertTrue(rec["suspended"]["at"])
        self.assertEqual(start.plan(self.repo).slots, 2)
        self.assertEqual(store.events(self.db, key="shop-b")[-1]["type"], "session.suspended")

    def test_suspend_refusals(self):
        failure.suspend(self.db, "b", "等设计稿", "先挂起 b")
        before = store.events(self.db)
        for args in (("b", "再挂", "再挂"), ("d", "没开", "挂 d"), ("c", "原话空", " "), ("c", "", "没原因")):
            with self.assertRaises(failure.FailureRefused):
                failure.suspend(self.db, *args)
        self.assertEqual(store.events(self.db), before)

    def test_resume(self):
        with self.assertRaises(failure.FailureRefused):
            failure.resume(self.db, "b")
        failure.suspend(self.db, "b", "等设计稿", "先挂起 b")
        failure.resume(self.db, "b")
        self.assertIsNone(self.session("shop-b")["suspended"])
        self.assertEqual(start.plan(self.repo).slots, 1)
        self.assertEqual(store.events(self.db, key="shop-b")[-1]["type"], "session.resumed")

    def test_suspended_session_keeps_its_identity(self):
        failure.suspend(self.db, "b", "等设计稿", "先挂起 b")
        role = hooks.detect(self.wt["b"])
        self.assertEqual((role.kind, role.module), ("dev", "b"))
        self.assertEqual(inbox.add(self.db, wait_user(sender="shop-b"), "shop-b", 900).code, 0)

    def test_validate_counts_only_unsuspended(self):
        reasons, _, _ = start.validate(self.repo, ["d", "e"], "开 d", None, None)
        self.assertTrue(any("空位只有 1 个" in r for r in reasons))
        failure.suspend(self.db, "b", "等设计稿", "先挂起 b")
        reasons, _, _ = start.validate(self.repo, ["d"], "开 d", None, None)
        self.assertEqual(reasons, [])


class SessionsTest(FailureCase):
    def open_ticket(self, sender):
        with self.db.transaction(actor="test") as tx:
            n = tx.allocate_number()
            tx.put("ticket", str(n), {"state": "open", "from": sender, "relayId": 1, "text": "等", "waitingFor": "x",
                                      "what": "接口", "closedReason": None, "closedBy": None}, action="opened")
        return n

    def test_lists_facts_without_verdicts(self):
        failure.suspend(self.db, "b", "等设计稿", "先挂起 b")
        t = self.open_ticket("shop-c")
        item = inbox.add(self.db, wait_user(sender="shop-c"), "shop-c", 901).number
        rows = {r["module"]: r for r in failure.sessions(self.db)}
        self.assertEqual(set(rows), {"b", "c"})
        self.assertEqual(rows["b"]["suspended"], "等设计稿")
        self.assertIsNone(rows["c"]["suspended"])
        self.assertEqual(rows["c"]["openTickets"], [t])
        self.assertIn(item, rows["c"]["openItems"])
        self.assertEqual(rows["b"]["openTickets"], [])
        self.assertEqual(rows["b"]["stage"], hooks.STAGE_WRITE)
        self.assertTrue(rows["b"]["lastActivity"] and rows["c"]["ago"].endswith("前"))
        text = "\n".join(failure.render_sessions(failure.sessions(self.db)))
        for word in ("停下", "卡住", "超时", "异常"):
            self.assertNotIn(word, text)
        self.assertIn("等设计稿", text)

    def test_last_activity_is_per_session(self):
        before = {r["module"]: r["lastActivity"] for r in failure.sessions(self.db)}
        import time; time.sleep(1.1)
        inbox.add(self.db, wait_user(sender="shop-c"), "shop-c", 902)
        after = {r["module"]: r["lastActivity"] for r in failure.sessions(self.db)}
        self.assertEqual(after["b"], before["b"])
        self.assertNotEqual(after["c"], before["c"])

    def test_ago_text(self):
        from datetime import datetime, timedelta
        now = datetime.now().astimezone()
        for delta, want in ((timedelta(minutes=5), "5 分钟前"), (timedelta(hours=3), "3 小时前"), (timedelta(days=2), "2 天前")):
            self.assertEqual(failure._ago((now - delta).isoformat(timespec="seconds"), now), want)


class ResumeKitTest(FailureCase):
    def test_kit_body(self):
        kit = failure.resume_kit(self.db, "b")
        self.assertEqual((kit.name, kit.module, kit.worktree), ("shop-b", "b", str(self.wt["b"])))
        text = store.read_body(self.db, kit.body)
        for want in ("模块：b", "shop-b", str(self.wt["b"]), hooks.STAGE_WRITE, "以状态库为准",
                     "module-crew takeover shop-b", "bridge_register"):
            self.assertIn(want, text)
        self.assertTrue(kit.path.endswith(f"bodies/{kit.body}.txt"))

    def test_kit_refused_without_session(self):
        with self.assertRaises(failure.FailureRefused):
            failure.resume_kit(self.db, "d")


if __name__ == "__main__":
    unittest.main()
