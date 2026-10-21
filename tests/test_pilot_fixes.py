"""crew-pilot-fixes: review originals, approval bookkeeping, own wait records, prompt reminders (spec/crew-pilot-fixes.md)."""

import hashlib
import unittest

from helpers import MergeCase, ReviewCase

from module_crew import inbox, protocol, review, sources, store


def conclusion(verdict="通过", extra="", ref="R-7", node="Spec", module="b"):
    return (f"【审查结论】\n审查编号：{ref}\n节点：{node}\n模块：{module}\n送审方：shop-b\n结论：{verdict}\n"
            f"来自：arch\n要点：接口清楚。\n{extra}")


CHANGES = "须修改：\n1. 错误码表缺两项\n"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ReviewShowTest(MergeCase):
    """Task 3: `review show C<N>` gives the review originals; notices point at it (Spec acceptance 6, 7)."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        sources.add(self.db, "arch", "lead", "登记审查会话", scope=sources.ALL_SCOPE)

    def test_rounds_in_order_with_sha(self):
        n = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        first = conclusion("有须修改项1条", CHANGES, ref="R-7")
        res = review.note(self.db, n, "arch", first)
        [rework] = res.sends
        todo = protocol.parse(store.read_body(self.db, rework["body"]))
        self.assertTrue(todo.ok, todo.problems)
        self.assertIn(f"审查原文：module-crew review show C{n}", todo.fields["要你做什么"])
        second = conclusion("通过，附建议1条", ref="R-8")
        with self.db.transaction(actor="t") as tx:               # a second round on the same item
            rec = tx.get("item", str(n))
            tx.put("item", str(n), dict(rec, reviews=rec["reviews"] + [dict(rec["reviews"][0], ref="R-8", text=second)]),
                   action="review-noted")
        lines = review.show(self.db, n)
        text = "\n".join(lines)
        self.assertLess(text.index("R-7"), text.index("R-8"))
        self.assertIn(f"sha256:{sha(first)}", text)
        self.assertIn(f"sha256:{sha(second)}", text)
        self.assertIn(first.strip(), text)

    def test_no_conclusion_submission_and_bad_number(self):
        n = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        self.assertEqual(review.show(self.db, n), [f"C{n} 还没有审查结论"])
        text = "\n".join(review.show(self.db, n, submission=True))
        self.assertIn("交审原文", text)
        self.assertIn(store.get(self.db, "item", str(n))["text"].strip(), text)
        with self.assertRaises(review.ShowRefused):
            review.show(self.db, 9999)
        approval = self.approve_final("c", 5)
        with self.assertRaises(review.ShowRefused):
            review.show(self.db, approval)                          # a merge approval, not a submission

    def test_start_notice_points_at_reviewed_submissions(self):
        s = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        review.note(self.db, s, "arch", conclusion("通过，附建议1条"))
        p = review.add(self.db, self.plan_review("b"), "shop-b", 2).number
        res = review.approve(self.repo, [s, p], "批")
        [notice] = [x for x in res.sends if x["kind"] == "coordination-notice"]
        msg = protocol.parse(store.read_body(self.db, notice["body"]))
        self.assertTrue(msg.ok, msg.problems)
        self.assertIn(f"审查原文：module-crew review show C{s}", msg.fields["要你做什么"])
        self.assertNotIn(f"review show C{p}", msg.fields["要你做什么"])      # no conclusion on the Plan

    def test_cli(self):
        n = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        review.note(self.db, n, "arch", conclusion())
        out = self.run_cli("review", "show", f"C{n}", cwd=self.wt["b"])
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("R-7", out.stdout)
        self.assertEqual(self.run_cli("review", "show", "C9999").returncode, 3)


class ApprovalBookkeepingTest(MergeCase):
    """Task 4: revoking keeps superseded submissions closed; a resubmission voids the stale approval (acceptance 8, 9)."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def test_x4_sequence(self):
        from module_crew import merge
        p = self.approve_final("b", 1)                              # submission A, approval P
        a = store.get(self.db, "item", str(p))["review"]
        out = review.add(self.db, self.finish("b", "VALUE = 'b2'\n"), "shop-b", 2)   # resubmission B
        self.assertEqual(out.code, 0, out.lines)
        b = out.number
        rec = store.get(self.db, "item", str(p))
        self.assertEqual((rec["state"], rec["closedReason"], rec["supersededBy"]), ("closed", "superseded", b))
        self.assertIn(f"合并批准 C{p} 因重交审 C{b} 作废", "\n".join(out.lines))
        self.assertEqual(merge.queue(self.repo), [])
        with self.assertRaises(merge.AnswerRefused):                # already void: nothing left to revoke
            merge.revoke(self.db, p, "撤回")
        q = merge.approve(self.db, b, "b 验收通过").approval
        # an older approval revoked after a newer submission exists (made by hand: the void path above prevents it)
        with self.db.transaction(actor="t") as tx:
            tx.put("item", str(p), dict(tx.get("item", str(p)), state="open", closedReason=None), action="test-reopen")
        res = merge.revoke(self.db, p, "撤回旧批准")
        self.assertEqual(store.get(self.db, "item", str(a))["state"], "closed")
        self.assertEqual(res.superseded_by, b)
        self.assertEqual(store.get(self.db, "item", str(q))["state"], "open")      # the new approval is untouched

    def test_revoke_without_resubmission_reopens(self):
        from module_crew import merge
        p = self.approve_final("b", 1)
        a = store.get(self.db, "item", str(p))["review"]
        res = merge.revoke(self.db, p, "撤回")
        self.assertIsNone(res.superseded_by)
        self.assertEqual(store.get(self.db, "item", str(a))["state"], "open")

    def test_cli_says_not_reopened(self):
        p = self.approve_final("b", 1)
        b = review.add(self.db, self.finish("b", "VALUE = 'b2'\n"), "shop-b", 2).number
        with self.db.transaction(actor="t") as tx:
            tx.put("item", str(p), dict(tx.get("item", str(p)), state="open", closedReason=None), action="test-reopen")
        out = self.run_cli("merge", "revoke", f"C{p}", "--original", "撤回旧批准")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn(f"已被 C{b} 取代，不重开", out.stdout)


WAIT = "【等待其他会话】\n结束：无\n在等谁：决策收件箱（live-saas-hub）\n等什么：#120 的【用户答复】转达\n"


class OwnWaitTest(ReviewCase):
    """Task 5: the coordinator's own 【等待其他会话】 is recorded and closed when what it waits for is answered (acceptance 10)."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        sources.add(self.db, "live-saas-hub", "hub", "登记收件枢纽")

    def test_add_and_duplicate(self):
        n, again = inbox.add_own_wait(self.db, WAIT, "live-saas-hub", 8738, "#120")
        self.assertFalse(again)
        rec = store.get(self.db, "ticket", str(n))
        self.assertEqual((rec["state"], rec["own"], rec["to"], rec["about"], rec["relayId"]),
                         ("open", True, "live-saas-hub", "#120", 8738))
        self.assertEqual(inbox.add_own_wait(self.db, WAIT, "live-saas-hub", 8738, "#120"), (n, True))
        self.assertEqual([k for k, _ in inbox.own_waits(self.db)], [n])
        for bad in (("【已恢复】\n结束：#1\n好了\n", "#120"), (WAIT, "120"), (WAIT, "W3")):
            with self.subTest(bad), self.assertRaises(inbox.AnswerRefused):
                inbox.add_own_wait(self.db, bad[0], "live-saas-hub", 9000, bad[1])

    def test_hub_answer_relay_resumes_own_wait(self):
        from test_sources import hub_reply
        n, _ = inbox.add_own_wait(self.db, WAIT, "live-saas-hub", 8738, "#120")
        s = review.add(self.db, self.spec_review("b"), "shop-b", 4001).number
        text = hub_reply(120, "批准")
        with store.approval_source(sources.check(self.db, "live-saas-hub", 120, 6100, text, sender="live-saas-hub").source):
            res = review.approve(self.repo, [s], "批准")
        self.assertEqual(res.code, 0, res.lines)
        resumed = [protocol.parse(x["path"].read_text(encoding="utf-8")) for x in res.sends if x["kind"] == "resumed"]
        self.assertIn((8738,), [m.end.items for m in resumed])
        self.assertTrue(all(m.ok for m in resumed))
        self.assertEqual(store.get(self.db, "ticket", str(n))["state"], "closed")
        self.assertEqual(inbox.own_waits(self.db), [])

    def test_crew_item_answer_and_cli(self):
        from helpers import wait_user
        item = inbox.add(self.db, wait_user(), "shop-b", 5001).number
        msg = self.tmp / "wait.txt"
        msg.write_text(WAIT.replace("#120 的", f"C{item} 的"), encoding="utf-8")
        out = self.run_cli("wait", "add", "--file", str(msg), "--to", "live-saas-hub", "--relay-id", "8800",
                           "--about", f"C{item}")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("W", out.stdout)
        self.assertIn("模块协调自开的等待记录：W", self.run_cli("sessions").stdout)
        done = self.run_cli("answer", f"C{item}", "--original", "先做 b")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("发送 【已恢复】 → live-saas-hub", done.stdout)
        line = next(x for x in done.stdout.splitlines() if "发送 【已恢复】" in x)
        body = line.split("正文文件：", 1)[1].strip()
        self.assertIn("结束：#8800", open(body, encoding="utf-8").read())
        self.assertEqual(inbox.own_waits(self.db), [])


class OwnWaitOnReviewNumberTest(MergeCase):
    """0.9.1 (rehearsal W257): a wait on C<N> closes when review approve / merge approve answers that C<N>."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        sources.add(self.db, "live-saas-hub", "hub", "登记收件枢纽")

    def wait_on(self, n, relay):
        return inbox.add_own_wait(self.db, WAIT.replace("#120 的", f"C{n} 的"), "di-p0-owner", relay, f"C{n}")[0]

    def test_hub_approval_closes_wait_on_review_number(self):
        from test_sources import hub_reply
        s = review.add(self.db, self.spec_review("b"), "shop-b", 4001).number
        w = self.wait_on(s, 9876)
        text = hub_reply(84, "84 A")
        with store.approval_source(sources.check(self.db, "live-saas-hub", 84, 6100, text, sender="live-saas-hub").source):
            res = review.approve(self.repo, [s], "84 A")
        self.assertEqual(res.code, 0, res.lines)
        mine = [x for x in res.sends if x.get("wait") == w]
        self.assertEqual([x["to"] for x in mine], ["di-p0-owner"])
        self.assertIn("结束：#9876", mine[0]["path"].read_text(encoding="utf-8"))
        self.assertEqual(store.get(self.db, "ticket", str(w))["state"], "closed")

    def test_self_approval_closes_wait_and_cli_says_so(self):
        s = review.add(self.db, self.spec_review("b"), "shop-b", 4001).number
        w = self.wait_on(s, 9877)
        out = self.run_cli("review", "approve", f"C{s}", "--original", "批准 b 的 Spec")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn(f"你开的等待记录 W{w} 等的事已发生：发送 【已恢复】 → di-p0-owner", out.stdout)
        self.assertEqual(inbox.own_waits(self.db), [])

    def test_merge_approve_closes_wait_on_final_review(self):
        n = review.add(self.db, self.finish("b"), "shop-b", 4800).number
        w = self.wait_on(n, 9878)
        out = self.run_cli("merge", "approve", f"C{n}", "--original", "b 验收通过")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn(f"你开的等待记录 W{w} 等的事已发生", out.stdout)
        self.assertEqual(inbox.own_waits(self.db), [])


class PromptReminderTest(MergeCase):
    """Task 6: commands that send to a module session end with a reminder to check for a permission prompt (acceptance 11)."""

    REMIND = "发完核对"

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        sources.add(self.db, "arch", "lead", "登记审查会话", scope=sources.ALL_SCOPE)

    def reminder(self, out) -> str:
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        lines = [x for x in out.stdout.splitlines() if self.REMIND in x]
        self.assertEqual(len(lines), 1, out.stdout)
        self.assertIn("去会话操作", lines[0])
        return lines[0]

    def test_start_rework_revoke_and_answer(self):
        s = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        p = review.add(self.db, self.plan_review("b"), "shop-b", 2).number
        self.assertIn("shop-b", self.reminder(self.run_cli("review", "approve", f"C{s}", f"C{p}", "--original", "批")))
        c = review.add(self.db, self.spec_review("c"), "shop-c", 3).number
        note = self.tmp / "note.txt"
        note.write_text(conclusion("有须修改项1条", CHANGES, module="c"), encoding="utf-8")
        self.assertIn("shop-c", self.reminder(self.run_cli("review", "note", f"C{c}", "--from", "arch", "--file", str(note))))
        approval = self.approve_final("b", 9)
        self.assertIn("shop-b", self.reminder(self.run_cli("merge", "revoke", f"C{approval}", "--original", "撤回")))
        from helpers import wait_user
        item = inbox.add(self.db, wait_user(), "shop-c", 5001).number
        self.assertIn("shop-c", self.reminder(self.run_cli("answer", f"C{item}", "--original", "先做 b")))

    def test_no_reminder_without_module_recipient(self):
        out = self.run_cli("review", "show", "C1")
        self.assertNotIn(self.REMIND, out.stdout)
        msg = self.tmp / "wait.txt"
        msg.write_text(WAIT, encoding="utf-8")
        out = self.run_cli("wait", "add", "--file", str(msg), "--to", "live-saas-hub", "--relay-id", "1", "--about", "#5")
        self.assertNotIn(self.REMIND, out.stdout)


if __name__ == "__main__":
    unittest.main()
