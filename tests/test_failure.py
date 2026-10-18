import unittest

from helpers import MergeCase

from module_crew import failure, hooks, inbox, merge, protocol, review, start, store

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


class SerialTest(FailureCase):
    def test_serial_blocks_new_modules_only(self):
        failure.set_mode(self.db, True, "先不并行了")
        self.assertEqual(store.get(self.db, "config", "main")["mode"], "serial")
        self.assertEqual(store.events(self.db, kind="config")[-1]["data"]["original"], "先不并行了")
        self.assertIn(failure.SERIAL_BLOCKER, start.plan(self.repo).blockers)
        before = store.events(self.db)
        res = start.prepare(self.repo, ["d"], "开 d")
        self.assertEqual(res.code, 3)
        self.assertTrue(any("已退回串行" in line for line in res.lines))
        self.assertEqual(store.events(self.db), before)
        # modules already open keep going
        self.assertEqual(review.add(self.db, self.spec_review("c"), "shop-c", 50).code, 0)
        self.approve_final("b", 51)
        self.assertEqual(merge.run(self.repo, self.check_script()).code, 0)
        failure.set_mode(self.db, False, "恢复")
        self.assertIsNone(store.get(self.db, "config", "main")["mode"])
        self.assertNotIn(failure.SERIAL_BLOCKER, start.plan(self.repo).blockers)
        self.assertEqual(start.prepare(self.repo, ["d"], "开 d").code, 0)

    def test_serial_refusals(self):
        with self.assertRaises(failure.FailureRefused):
            failure.set_mode(self.db, False, "恢复")
        with self.assertRaises(failure.FailureRefused):
            failure.set_mode(self.db, True, " ")
        failure.set_mode(self.db, True, "先不并行了")
        with self.assertRaises(failure.FailureRefused):
            failure.set_mode(self.db, True, "再来")


class IsolationTest(FailureCase):
    def test_suspended_merged_and_returned_do_not_interfere(self):
        res = start.prepare(self.repo, ["d"], "开 d")
        self.assertEqual(res.code, 0, res.lines)
        self.wt["d"] = res.prepared[0]["worktree"]
        failure.suspend(self.db, "b", "等设计稿", "先挂起 b")
        b_before = self.session("shop-b")
        c_ok = self.approve_final("c", 60)
        d_bad = self.approve_final("d", 61, path="fail.flag")
        check = self.check_script(fail_if="fail.flag")

        first = merge.run(self.repo, check)
        self.assertEqual((first.code, first.approval), (0, c_ok))
        kinds = {(x["to"], x["kind"]) for x in first.sends}
        self.assertIn(("shop-c", "wrap-up"), kinds)
        self.assertNotIn(("shop-d", "sync-baseline"), kinds)  # d is still queued (pilot fix C)
        self.assertIn(("shop-b", "sync-baseline"), kinds)       # suspended b is still developing
        for x in first.sends:
            self.assertTrue(protocol.parse(store.read_body(self.db, x["body"])).ok)

        second = merge.run(self.repo, check)
        self.assertEqual((second.code, second.approval), (5, d_bad))
        self.assertEqual([(x["to"], x["kind"]) for x in second.sends], [("shop-d", "returned")])
        self.assertEqual(store.get(self.db, "item", str(c_ok))["closedReason"], "merged")
        self.assertEqual(store.get(self.db, "item", str(d_bad))["closedReason"], "returned")

        self.assertEqual(self.session("shop-b"), b_before)
        self.assertEqual(self.session("shop-d")["status"], "active")
        rows = {r["module"]: r for r in failure.sessions(self.db)}
        self.assertEqual(rows["b"]["suspended"], "等设计稿")
        self.assertEqual(rows["c"]["stage"], hooks.STAGE_MERGED)


class CliTest(FailureCase):
    def test_commands(self):
        import json
        run = lambda *a: self.run_cli(*a, cwd=self.repo)
        out = run("suspend", "b", "--reason", "等设计稿", "--original", "先挂起 b")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(run("suspend", "b", "--reason", "再挂", "--original", "再挂").returncode, 3)
        rows = json.loads(run("sessions", "--json").stdout)
        self.assertEqual({r["module"]: r["suspended"] for r in rows}, {"b": "等设计稿", "c": None})
        self.assertIn("挂起：等设计稿", run("sessions").stdout)
        self.assertEqual(run("resume", "b").returncode, 0)
        self.assertEqual(run("resume", "b").returncode, 3)
        kit = run("resume-kit", "b")
        self.assertEqual(kit.returncode, 0, kit.stderr)
        self.assertIn("shop-b", kit.stdout)
        self.assertEqual(run("resume-kit", "d").returncode, 3)
        self.assertEqual(run("serial", "--original", "先不并行了").returncode, 0)
        self.assertEqual(run("serial", "--original", "再来").returncode, 3)
        self.assertEqual(run("start", "plan").returncode, 3)
        self.assertEqual(run("serial", "--off", "--original", "恢复").returncode, 0)

    def test_no_sessions(self):
        with self.db.transaction(actor="test") as tx:
            for name, rec in tx.records("session").items():
                if rec.get("role") == "dev":
                    tx.put("session", name, {**rec, "status": "retired"}, action="retired")
        out = self.run_cli("sessions", cwd=self.repo)
        self.assertEqual((out.returncode, out.stdout.strip()), (0, "没有在用的模块会话"))


if __name__ == "__main__":
    unittest.main()
