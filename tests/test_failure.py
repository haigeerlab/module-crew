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

    def test_amend_reason(self):
        failure.suspend(self.db, "b", "等设计稿", "先挂起 b")
        mark = self.session("shop-b")["suspended"]
        out = failure.amend_reason(self.db, "b", "等接口文档", "原因改成等接口文档")
        rec = self.session("shop-b")
        self.assertEqual(rec["suspended"]["reason"], "等接口文档")
        self.assertEqual((rec["suspended"]["at"], rec["suspended"]["approval"]), (mark["at"], mark["approval"]))
        self.assertEqual(start.plan(self.repo).slots, 2)                  # still suspended
        last = store.events(self.db, key="shop-b")[-1]
        self.assertEqual((last["type"], last["data"]["from"]), ("session.suspend-amended", "等设计稿"))
        [note] = out.sends
        self.assertEqual((note["to"], note["kind"]), ("shop-b", "suspend"))
        msg = self.notice(note)
        self.assertEqual((msg.contract()["notice"]["kind"], msg.fields["原因"]), ("suspend", "等接口文档"))
        self.assertIn("挂起原因已更新", msg.fields["要你做什么"])
        refs = [int(x) for x in re.findall(r"C(\d+)", msg.fields["依据"])]
        self.assertEqual(refs[1], mark["approval"])
        rec = store.get(self.db, "item", str(refs[0]))
        self.assertEqual((rec["kind"], rec["answer"]["original"]), ("suspend-reason", "原因改成等接口文档"))
        # resume still lists what landed since the suspension, not since the amendment
        res = failure.resume(self.db, "b", "恢复 b")
        self.assertIn(f"挂起依据 C{mark['approval']}", self.notice(res.sends[0]).fields["依据"])

    def test_amend_reason_refusals(self):
        before = store.events(self.db)
        with self.assertRaises(failure.FailureRefused) as cm:
            failure.amend_reason(self.db, "b", "等接口文档", "改原因")
        self.assertIn("没有挂起", str(cm.exception))
        self.assertEqual(store.events(self.db), before)
        failure.suspend(self.db, "b", "等设计稿", "先挂起 b")
        before = store.events(self.db)
        for args in (("b", "等接口文档", " "), ("b", " ", "改原因"), ("d", "等接口文档", "改原因")):
            with self.assertRaises(failure.FailureRefused):
                failure.amend_reason(self.db, *args)
        self.assertEqual(store.events(self.db), before)

    def test_amend_reason_cli(self):
        from module_crew import sources
        failure.suspend(self.db, "b", "等设计稿", "先挂起 b")
        out = self.run_cli("suspend", "c", "--amend-reason", "等接口文档", "--original", "改原因", cwd=self.repo)
        self.assertEqual(out.returncode, 3, out.stderr)                   # c is not suspended
        self.assertIn("没有挂起", out.stderr)
        out = self.run_cli("suspend", "b", "--amend-reason", "等接口文档", cwd=self.repo)
        self.assertEqual(out.returncode, 2)                               # no user's words
        out = self.run_cli("suspend", "b", "--reason", "x", "--amend-reason", "y", "--original", "改", cwd=self.repo)
        self.assertEqual(out.returncode, 2)                               # one or the other
        sources.add(self.db, "live-saas-hub", "hub", "登记收件枢纽")
        msg = self.tmp / "hub.txt"
        msg.write_text(protocol.render_user_reply(120, "原因改成等接口文档", "2026-10-18T12:00:00+08:00", source_relay_id=6100),
                       encoding="utf-8")
        out = self.run_cli("suspend", "b", "--amend-reason", "等接口文档", "--source", "live-saas-hub", "--source-item", "120",
                           "--source-relay-id", "6100", "--source-from", "live-saas-hub", "--original-file", str(msg),
                           cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("已改挂起原因", out.stdout)
        rec = self.session("shop-b")
        self.assertEqual(rec["suspended"]["reason"], "等接口文档")
        self.assertEqual(store.events(self.db, key="shop-b")[-1]["data"]["source"]["item"], 120)

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

    def merge_light_task(self, task: int, commit: str) -> int:
        """A light task's merge approval merged meanwhile: its number sits in `task`, `module` is None (S82)."""
        with self.db.transaction(actor="coordinator") as tx:
            n = tx.allocate_number()
            tx.put("item", str(n), {"state": "closed", "kind": "merge-approval", "module": None, "task": task,
                                    "mergeCommit": commit}, action="merged", data={"commit": commit})
        return n

    def test_resume_names_merged_light_task(self):
        failure.suspend(self.db, "b", "等设计稿", "先挂起 b")
        n = self.merge_light_task(782, "abcdef1234")
        [note] = failure.resume(self.db, "b", "恢复 b").sends
        todo = self.notice(note).fields["要你做什么"]
        self.assertIn(f"轻任务 T782（合并批准事项 C{n}，abcdef1）", todo)
        self.assertNotIn("None", todo)

    def test_resume_no_sync(self):
        failure.suspend(self.db, "b", "等设计稿", "先挂起 b")
        n = self.merge_light_task(782, "abcdef1234")
        [note] = failure.resume(self.db, "b", "恢复 b，不合 main", no_sync=True).sends
        todo = self.notice(note).fields["要你做什么"]
        self.assertIn(f"轻任务 T782（合并批准事项 C{n}，abcdef1）", todo)
        self.assertIn("按用户批准不同步", todo)
        self.assertNotIn("module-crew sync", todo)
        self.assertNotIn("完整检查", todo)
        self.assertIn(failure.RESUME_TODO, todo)

    def test_resume_no_sync_needs_original(self):
        failure.suspend(self.db, "b", "等设计稿", "先挂起 b")
        with self.assertRaises(failure.FailureRefused):
            failure.resume(self.db, "b", " ", no_sync=True)

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
        run("suspend", "b", "--reason", "等设计稿", "--original", "再挂起 b")
        out = run("resume", "b", "--no-sync", "--original", "恢复 b，不合 main")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("已取消挂起：shop-b", out.stdout)
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


class DoneSessionsTest(FailureCase):
    """S67 (T563): status puts merged-but-not-taken-back sessions on one line of their own."""

    def section(self):
        out = self.run_cli("status", cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = out.stdout.splitlines()
        start = lines.index("会话与待办")
        end = next(i for i in range(start + 1, len(lines)) if not lines[i].startswith("  "))
        return lines[start + 1:end]

    def test_merged_module_listed_apart(self):
        self.approve_final("b", 1)
        self.assertEqual(merge.run(self.repo, check_command="python3 -c pass").code, 0)
        rows = self.section()
        self.assertIn("  已做完待收回：shop-b（b）（merge cleanup 收回）", rows)
        self.assertFalse(any(r.startswith("  shop-b") for r in rows), rows)
        self.assertTrue(any(r.startswith("  shop-c（dev，c）") for r in rows), rows)

    def test_finished_task_listed_apart(self):
        from test_light_task import new_task, register_task
        done, working = new_task(self.db, self.repo), new_task(self.db, self.repo, expect=("docs/u.md",))
        with self.db.transaction(actor="t") as tx:
            tx.put("task", str(done), dict(tx.get("task", str(done)), state="merged"), action="merged")
        register_task(self.db, done, "/nowhere/a")
        register_task(self.db, working, "/nowhere/b")
        rows = self.section()
        self.assertIn(f"  已做完待收回：shop-t{done}（T{done}）（merge cleanup 收回）", rows)
        self.assertTrue(any(r.startswith(f"  shop-t{working}（task）") for r in rows), rows)

    def test_nothing_done(self):
        self.assertFalse(any("已做完待收回" in r for r in self.section()))


if __name__ == "__main__":
    unittest.main()
