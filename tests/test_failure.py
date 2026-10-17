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


if __name__ == "__main__":
    unittest.main()
