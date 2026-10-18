"""crew-review-nearby: review close to the coordinator, decisions for the user (spec/crew-review-nearby.md)."""

import unittest
from datetime import datetime, timedelta

from helpers import MergeCase, ReviewCase, git, review_text

from module_crew import protocol, review, sources, store


def conclusion(verdict="通过", extra="", ref="R-7", node="Spec", module="b"):
    return (f"【审查结论】\n审查编号：{ref}\n节点：{node}\n模块：{module}\n送审方：shop-b\n结论：{verdict}\n"
            f"来自：arch\n要点：接口清楚。\n{extra}")


CHANGES = "须修改：\n1. 错误码表缺两项\n2. 超时没写\n"
DECISIONS = ("待用户决定：\nD1：alpha 首字母要不要大写？\n  A. 大写\n  B. 保持小写\n  倾向：B（与现有命名一致）\n"
             "D2：要不要支持空字符串？\n  A. 支持\n  B. 报错\n  倾向：A\n")


class ConclusionParseTest(unittest.TestCase):
    """Task 1: 【审查结论】 is judged now (contract v1.9 forms plus the v2.0 draft fields)."""

    def test_forms(self):
        for verdict, code, advice in (("通过", "passed", None), ("通过，附建议2条", "passed-with-advice", 2)):
            with self.subTest(verdict):
                msg = protocol.parse(conclusion(verdict))
                self.assertTrue(msg.ok, msg.problems)
                c = msg.contract()["conclusion"]
                self.assertEqual((c["ref"], c["node"], c["verdict"], c["adviceCount"], c["module"]),
                                 ("R-7", "spec", code, advice, "b"))

    def test_changes_required_with_count(self):
        msg = protocol.parse(conclusion("有须修改项2条", CHANGES))
        self.assertTrue(msg.ok, msg.problems)
        c = msg.contract()["conclusion"]
        self.assertEqual((c["verdict"], c["changeCount"], c["changes"]),
                         ("changes-required", 2, ["错误码表缺两项", "超时没写"]))

    def test_changes_problems(self):
        self.assertIn("missing-field:须修改", protocol.parse(conclusion("有须修改项2条")).problems)
        self.assertIn("change-count-mismatch", protocol.parse(conclusion("有须修改项3条", CHANGES)).problems)
        bare = protocol.parse(conclusion("有须修改项", CHANGES))   # v1.9 wording still valid
        self.assertTrue(bare.ok, bare.problems)
        self.assertIn("change-count-missing", bare.hints)

    def test_bad_verdict_and_node(self):
        self.assertIn("bad-verdict", protocol.parse(conclusion("差不多")).problems)
        self.assertIn("bad-node", protocol.parse(conclusion(node="需求")).problems)
        self.assertIsNone(protocol.parse(conclusion("差不多")).contract()["conclusion"])

    def test_decisions(self):
        msg = protocol.parse(conclusion("通过", DECISIONS))
        self.assertTrue(msg.ok, msg.problems)
        d = msg.contract()["conclusion"]["decisions"]
        self.assertEqual([x["id"] for x in d], ["D1", "D2"])
        self.assertEqual(d[0]["question"], "alpha 首字母要不要大写？")
        self.assertEqual(d[0]["options"], [{"letter": "A", "text": "大写"}, {"letter": "B", "text": "保持小写"}])
        self.assertEqual(d[0]["lean"], "B")
        bad = "待用户决定：\nD1：要不要？\n  A. 要\n  倾向：A\n"           # only one option
        self.assertIn("bad-decision-item", protocol.parse(conclusion("通过", bad)).problems)
        no_lean = "待用户决定：\nD1：要不要？\n  A. 要\n  B. 不要\n"
        self.assertIn("bad-decision-item", protocol.parse(conclusion("通过", no_lean)).problems)


class SplitTest(unittest.TestCase):
    def test_sections(self):
        two = conclusion("通过") + "\n" + conclusion("有须修改项2条", CHANGES, ref="R-8", node="Plan")
        parts = protocol.split_sections(two)
        self.assertEqual(len(parts), 2)
        self.assertEqual([protocol.parse(p).contract()["conclusion"]["ref"] for p in parts], ["R-7", "R-8"])
        self.assertEqual(protocol.split_sections(conclusion()), [conclusion()])


class DisagreeTest(unittest.TestCase):
    def review(self, extra=""):
        return ("【交审】\n结束：无\n模块：b\n节点：Spec\n文件：\nspec/b.md sha256:0123456789abcdef\n"
                f"要点：\n- 做：页面\n- 不做：后台\n{extra}")

    def test_disagree_field(self):
        msg = protocol.parse(self.review("不同意：R-7：错误码表已在接口提案里定，不该在 Spec 里重复\n"))
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual(msg.contract()["submission"]["disagree"],
                         {"ref": "R-7", "reason": "错误码表已在接口提案里定，不该在 Spec 里重复"})
        self.assertIn("bad-disagree", protocol.parse(self.review("不同意：就是不同意\n")).problems)
        self.assertNotIn("disagree", protocol.parse(self.review()).contract()["submission"])


class NoticeTest(unittest.TestCase):
    def test_rework(self):
        text = protocol.render_coordination_notice("rework", "审查 R-7（交审 C15）", "1. 补错误码\n2. 写超时", round=2)
        msg = protocol.parse(text)
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual((msg.contract()["notice"]["kind"], msg.contract()["notice"]["round"]), ("rework", 2))
        self.assertIn("missing-review-ref",
                      protocol.parse("【协调通知】\n类型：返工\n依据：交审 C15\n轮次：1\n要你做什么：改\n").problems)
        self.assertIn("bad-round",
                      protocol.parse("【协调通知】\n类型：返工\n依据：审查 R-7\n轮次：零\n要你做什么：改\n").problems)
        with self.assertRaises(ValueError):
            protocol.render_coordination_notice("rework", "审查 R-7", "改")          # round is required

    def test_revoke_and_crew_refs(self):
        msg = protocol.parse(protocol.render_coordination_notice(
            "revoke", "C40（用户撤回答复 C52）", "停在当前停点，等新的答复"))
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual(msg.contract()["notice"]["kind"], "revoke")
        # single use: the start notice cites the coordinator's local approval C40
        start = protocol.parse("【协调通知】\n类型：开工\n依据：C40（用户在协调会话批准；交审 C15）\n要你做什么：开始构建\n")
        self.assertTrue(start.ok, start.problems)
        self.assertEqual(start.contract()["notice"]["refs"], [])     # refs keeps hub numbers only
        self.assertIn("missing-approval-ref",
                      protocol.parse("【协调通知】\n类型：开工\n依据：交审\n要你做什么：开始\n").problems)

    def test_user_reply_crew_item(self):
        msg = protocol.parse("【用户答复】\n事项：C20（你的原消息 #4001）\n用户原话：A\n答复时间：2026-10-19T10:00:00+08:00\n")
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual(msg.item, 20)


class NearbyCase(ReviewCase):
    """b and c opened; a reviewer `arch` registered as a lead source (registration_lead=False skips it)."""
    with_lead = True

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        if self.with_lead:
            sources.add(self.db, "arch", "lead", "登记审查会话")

    def state(self, n, minutes=0):
        rec = store.get(self.db, "item", str(n))
        now = datetime.fromisoformat(rec["sentAt"]) + timedelta(minutes=minutes) if rec.get("sentAt") else None
        return review.review_state(self.db, n, now=now)


class ForwardTest(NearbyCase):
    """Task 3: 送审 and the review state of a submission."""

    def test_forward_to_reviewer(self):
        text = self.spec_review("b")
        out = review.add(self.db, text, "shop-b", 4001)
        self.assertEqual(out.code, 0, out.lines)
        [send] = out.sends
        self.assertEqual((send["kind"], send["to"], send["replyTo"]), ("review-forward", "arch", None))
        self.assertEqual(send["path"].read_text(encoding="utf-8"), text)         # the 【交审】 unchanged
        self.assertTrue(store.get(self.db, "item", str(out.number))["sentAt"])
        self.assertEqual(self.state(out.number), "reviewing")
        self.assertEqual(self.state(out.number, minutes=16), "timeout")          # 15 minutes without a conclusion
        cli = self.run_cli("review", "add", str(self.write(self.plan_review("b"))), "--from", "shop-b", "--relay-id", "4002",
                           cwd=self.repo)
        self.assertIn("发送 【交审】 → arch（送审），正文文件：", cli.stdout)

    def write(self, text):
        f = self.tmp / f"msg-{len(list(self.tmp.iterdir()))}.txt"
        f.write_text(text, encoding="utf-8")
        return f

    def test_disagree(self):
        first = review.add(self.db, self.spec_review("b"), "shop-b", 4001).number
        same = self.spec_review("b").replace("要点：", "不同意：R-7：错误码已在接口提案里定\n要点：")
        out = review.add(self.db, same, "shop-b", 4002)
        self.assertEqual(out.code, 0, out.lines)
        self.assertEqual(out.closed, [first])
        self.assertEqual(out.sends, [])                                            # not sent back to the reviewer
        self.assertEqual(self.state(out.number), "decide")
        self.assertEqual(store.get(self.db, "item", str(out.number))["disagree"]["ref"], "R-7")
        spec = self.wt["b"] / "spec" / "b.md"
        spec.write_text(spec.read_text() + "改了\n")
        git(self.wt["b"], "commit", "-qam", "change")
        changed = self.spec_review("b").replace("要点：", "不同意：R-7：理由\n要点：")
        bad = review.add(self.db, changed, "shop-b", 4003)
        self.assertEqual(bad.code, 3)
        self.assertIn("上一版", " ".join(bad.lines))

    def test_disagree_needs_previous(self):
        text = self.spec_review("b").replace("要点：", "不同意：R-7：理由\n要点：")
        self.assertEqual(review.add(self.db, text, "shop-b", 4001).code, 3)


class NoteTest(NearbyCase):
    """Task 4: conclusions drive rework close to the coordinator; several sections in one message."""

    def submit(self, node="Spec", relay=None):
        text = self.spec_review("b") if node == "Spec" else self.plan_review("b")
        self.relay = getattr(self, "relay", 5000) + 1
        return review.add(self.db, text, "shop-b", relay or self.relay).number

    def test_rework_loop(self):
        head = git(self.repo, "rev-parse", "HEAD")
        n = self.submit()
        res = review.note(self.db, n, "arch", conclusion("有须修改项2条", CHANGES))
        [send] = res.sends
        self.assertEqual((send["kind"], send["to"]), ("rework", "shop-b"))
        msg = protocol.parse(send["path"].read_text(encoding="utf-8"))
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual(msg.contract()["notice"]["round"], 1)
        self.assertIn("R-7", msg.fields["依据"])
        self.assertIn(f"C{n}", msg.fields["依据"])
        self.assertIn("错误码表缺两项", msg.fields["要你做什么"])
        self.assertIn("超时没写", msg.fields["要你做什么"])
        self.assertEqual(self.state(n), "rework")
        self.assertEqual(store.get(self.db, "item", str(n))["state"], "open")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)               # nothing pushed forward
        again = self.submit()
        self.assertEqual(self.state(again), "reviewing")
        self.assertEqual(review._rounds(self.db, "b", "spec"), 1)
        self.assertFalse(review.note(self.db, again, "arch", conclusion("通过")).sends)
        self.assertEqual(self.state(again), "passed")

    def test_limit_three(self):
        n = self.submit()
        for i in range(3):
            self.assertEqual(len(review.note(self.db, n, "arch", conclusion("有须修改项2条", CHANGES)).sends), 1)
            n = self.submit()
        res = review.note(self.db, n, "arch", conclusion("有须修改项2条", CHANGES))
        self.assertEqual(res.sends, [])
        self.assertTrue(store.get(self.db, "item", str(n))["overLimit"])
        self.assertEqual(self.state(n), "decide")
        self.assertIn("已满 3 次", " ".join(res.lines))

    def test_decisions_recorded(self):
        n = self.submit()
        review.note(self.db, n, "arch", conclusion("通过", DECISIONS))
        self.assertEqual(self.state(n), "decide")
        self.assertEqual([d["id"] for d in store.get(self.db, "item", str(n))["reviews"][-1]["decisions"]], ["D1", "D2"])

    def test_multi_sections(self):
        spec, plan = self.submit(), self.submit("Plan")
        two = conclusion("通过") + "\n" + conclusion("有须修改项2条", CHANGES, ref="R-8", node="Plan")
        res = review.note(self.db, None, "arch", two)
        self.assertEqual([r["ref"] for r in res.rows], ["R-7", "R-8"])
        self.assertEqual((self.state(spec), self.state(plan)), ("passed", "rework"))
        before = store.events(self.db)
        bad = conclusion("通过") + "\n" + conclusion("差不多", ref="R-9", node="Plan")
        with self.assertRaises(review.NoteRefused) as ctx:
            review.note(self.db, None, "arch", bad)
        self.assertIn("第 2 段", str(ctx.exception))
        self.assertEqual(store.events(self.db), before)

    def test_then_batch(self):
        spec, plan = self.submit(), self.submit("Plan")
        f = self.tmp / "c1.txt"
        f.write_text(conclusion("通过"), encoding="utf-8")
        out = self.run_cli("review", "note", f"C{spec}", "--from", "arch", "--file", str(f), "--then-batch", "--for-hub",
                           cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn(f"还在等：C{plan}", out.stdout)
        self.assertNotIn("正文文件", out.stdout)
        f.write_text(conclusion("通过", node="Plan", ref="R-8"), encoding="utf-8")
        out = self.run_cli("review", "note", f"C{plan}", "--from", "arch", "--file", str(f), "--then-batch", "--for-hub",
                           cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("正文文件", out.stdout)


class BatchTest(NearbyCase):
    """Task 5: what goes into the batch for the user, and how the body reads."""
    submit = NoteTest.submit

    def body(self):
        made = review.for_hub(self.repo)
        self.assertIsNotNone(made)
        msg = protocol.parse(made[2])
        self.assertTrue(msg.ok, msg.problems)
        return made[2], msg

    def test_only_ready_reviews(self):
        spec, plan = self.submit(), self.submit("Plan")
        review.note(self.db, spec, "arch", conclusion("通过"))
        text, msg = self.body()
        self.assertIn(f"C{spec}", msg.fields["要你决定"])
        self.assertNotIn(f"C{plan}", msg.fields["要你决定"])                       # still under review
        review.note(self.db, plan, "arch", conclusion("有须修改项2条", CHANGES, node="Plan", ref="R-8"))
        self.assertNotIn(f"C{plan}", self.body()[1].fields["要你决定"])          # in rework

    def test_rounds_line_and_summary(self):
        n = self.submit()
        review.note(self.db, n, "arch", conclusion("有须修改项2条", CHANGES))
        n = self.submit()
        review.note(self.db, n, "arch", conclusion("通过"))
        text, msg = self.body()
        self.assertIn("经 1 轮审查修改：错误码表缺两项", text)
        points = msg.fields["要点"].split("\n\n")[0].splitlines()
        self.assertLessEqual(len(points), 5)
        self.assertEqual(points[0], "- b：Spec（审查通过，经 1 轮修改）")
        self.assertEqual(points[-1], "- 待你决定的问题：无")

    def test_decisions_in_body(self):
        n = self.submit()
        review.note(self.db, n, "arch", conclusion("通过", DECISIONS))
        text, msg = self.body()
        self.assertIn("D1：alpha 首字母要不要大写？", msg.fields["要你决定"])
        self.assertIn("倾向：B", msg.fields["要你决定"])
        self.assertEqual(msg.fields["你该回"].strip(), "A 全部批准；D1 选 B；D2 选 A")
        self.assertIn("- 待你决定的问题：2 个（D1、D2）", text)
        rec = [v for v in store.records(self.db, "item").values() if v.get("kind") == "hub-batch"][-1]
        self.assertEqual(rec["decisions"]["D2"]["review"], n)

    def test_timeout_and_disagree_questions(self):
        n = self.submit()
        with self.db.transaction(actor="t") as tx:
            rec = tx.get("item", str(n))
            tx.put("item", str(n), dict(rec, sentAt="2026-01-01T00:00:00+08:00"), action="aged")
        text, msg = self.body()
        self.assertIn("未审查（审查者无响应）", text)
        self.assertIn("不等审查直接批", msg.fields["要你决定"])
        review.note(self.db, n, "arch", conclusion("有须修改项2条", CHANGES))
        same = self.spec_review("b").replace("要点：", "不同意：R-7：错误码已在接口提案里定\n要点：")
        review.add(self.db, same, "shop-b", 6001)
        text, msg = self.body()
        self.assertIn("按模块现版本批准", msg.fields["要你决定"])
        self.assertIn("错误码已在接口提案里定", msg.fields["要你决定"])

    def test_points_list_not_cut_silently(self):
        long = self.plan_review("b").replace("要点：\n- 做：页面与接口\n- 不做：后台",
                                              "要点：\n假设：\n1. 一\n2. 二\n3. 三\n4. 四\n5. 五")
        n = review.add(self.db, long, "shop-b", 7001).number
        review.note(self.db, n, "arch", conclusion("通过", node="Plan"))
        text, _ = self.body()
        self.assertIn("…（共 5 条，回『详情』看全文）", text)
        out = self.run_cli("review", "batch", cwd=self.repo).stdout
        self.assertIn("5. 五", out)                                                 # the coordinator sees everything


class FinalOptionsTest(MergeCase):
    def test_final_consequence_and_chinese_node(self):
        db = store.open_store(self.repo)
        review.add(db, self.finish("b"), "shop-b", 8001)
        text = review.for_hub(self.repo)[2]
        self.assertIn("合并进集成分支", text)
        self.assertIn("b 的 最终验收", text)
        self.assertNotIn("final", text)


class NoReviewerTest(NearbyCase):
    with_lead = False

    def test_no_forward_state_none(self):
        out = review.add(self.db, self.spec_review("b"), "shop-b", 4001)
        self.assertEqual((out.sends, review.review_state(self.db, out.number)), ([], "none"))


if __name__ == "__main__":
    unittest.main()
