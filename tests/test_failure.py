import re
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
            failure.resume(self.db, "b", "恢复 b")
        failure.suspend(self.db, "b", "等设计稿", "先挂起 b")
        with self.assertRaises(failure.FailureRefused):
            failure.resume(self.db, "b", " ")                      # pilot round 2, problem M
        failure.resume(self.db, "b", "恢复 b")
        self.assertIsNone(self.session("shop-b")["suspended"])
        self.assertEqual(start.plan(self.repo).slots, 1)
        last = store.events(self.db, key="shop-b")[-1]
        self.assertEqual((last["type"], last["data"]["original"]), ("session.resumed", "恢复 b"))

    def notice(self, x):
        msg = protocol.parse(store.read_body(self.db, x["body"]))
        self.assertTrue(msg.ok, msg.problems)
        return msg

    def test_suspend_and_resume_notices(self):
        out = failure.suspend(self.db, "b", "等设计稿", "先挂起 b")
        self.assertEqual(out.name, "shop-b")
        [note] = out.sends
        self.assertEqual((note["to"], note["kind"]), ("shop-b", "suspend"))
        msg = self.notice(note)
        approval = int(re.findall(r"C(\d+)", msg.fields["依据"])[0])   # crew numbers are C<N>
        self.assertEqual((msg.contract()["notice"]["kind"], msg.fields["原因"]), ("suspend", "等设计稿"))
        self.assertIn("spec-guard", msg.fields["要你做什么"])
        rec = store.get(self.db, "item", str(approval))
        self.assertEqual((rec["kind"], rec["answer"]["original"]), ("suspend", "先挂起 b"))
        out = failure.resume(self.db, "b", "设计稿到了，恢复 b")
        [note] = out.sends
        msg = self.notice(note)
        refs = [int(x) for x in re.findall(r"C(\d+)", msg.fields["依据"])]
        self.assertEqual((msg.contract()["notice"]["kind"], refs[1]), ("resume", approval))
        self.assertEqual(store.get(self.db, "item", str(refs[0]))["answer"]["original"], "设计稿到了，恢复 b")
        self.assertNotIn("集成分支在挂起期间", msg.fields["要你做什么"])   # nothing merged meanwhile

    def test_resume_sends_sync_when_baseline_moved(self):
        failure.suspend(self.db, "b", "等设计稿", "先挂起 b")
        n = self.approve_final("c", 70)
        res = merge.run(self.repo, self.check_script())
        self.assertEqual(res.code, 0, res.lines)
        self.assertNotIn("shop-b", [x["to"] for x in res.sends])       # suspended: no "continue" (problem L)
        [note] = failure.resume(self.db, "b", "恢复 b").sends
        todo = self.notice(note).fields["要你做什么"]
        self.assertIn(f"C{n}", todo)
        self.assertIn("先跑 `module-crew sync`", todo)

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
        self.assertEqual(rows["b"]["stageText"], hooks.STAGE_WRITE)
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

    def test_kit_after_final_review(self):
        n = review.add(self.db, self.finish("b"), "shop-b", 4800).number
        text = store.read_body(self.db, failure.resume_kit(self.db, "b").body)
        self.assertIn(f"最终验收已交审（交审事项 C{n}）", text)
        self.assertNotIn("刚压缩过", text)
        row = {r["module"]: r for r in failure.sessions(self.db)}["b"]
        self.assertEqual(row["stage"], "build")                        # export enum unchanged

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
        self.assertNotIn(("shop-b", "sync-baseline"), kinds)    # suspended b gets it on resume (problem L)
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
        self.assertEqual(rows["c"]["stageText"], hooks.STAGE_MERGED)


class CliTest(FailureCase):
    def test_commands(self):
        import json
        run = lambda *a: self.run_cli(*a, cwd=self.repo)
        out = run("suspend", "b", "--reason", "等设计稿", "--original", "先挂起 b")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(run("suspend", "b", "--reason", "再挂", "--original", "再挂").returncode, 3)
        rows = json.loads(run("sessions", "--json").stdout)["sessions"]
        self.assertEqual({r["module"]: r["suspended"] for r in rows}, {"b": "等设计稿", "c": None})
        self.assertIn("挂起：等设计稿", run("sessions").stdout)
        self.assertEqual(run("resume", "b").returncode, 2)               # the user's words are required
        out = run("resume", "b", "--original", "恢复 b")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("发送 【协调通知】 → shop-b", out.stdout)
        self.assertEqual(run("resume", "b", "--original", "再恢复").returncode, 3)
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
