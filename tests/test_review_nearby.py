"""crew-review-nearby: review close to the coordinator, decisions for the user (spec/crew-review-nearby.md)."""

import unittest

from module_crew import protocol


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


if __name__ == "__main__":
    unittest.main()
