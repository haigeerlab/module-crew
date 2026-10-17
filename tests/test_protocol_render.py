import unittest

from module_crew import protocol

NOTICES = {
    "start": ("用户批准事项 #7（crew-store 的 Spec 与 Plan）", "在本 worktree 按 tasks/crew-store/plan.md 开始构建；\n  公共文件只能经【公共变更请求】改"),
    "sync-baseline": ("公共变更请求 #52 已在集成基线提交 8a9b0c1", "把集成分支合进你的模块分支"),
    "interface-change": ("用户批准事项 #9（crew-protocol 接口提案修订）", "按新的 render 签名改调用处"),
    "wrap-up": ("用户批准事项 #15（crew-store 最终验收）", "停止开发，等待收回 worktree"),
    "returned": ("最终验收批准事项 #31；合入后完整检查失败，已撤销合并提交 a1b2c3d", "同步集成基线、修好后重新发最终验收【交审】"),
}


class NoticeTest(unittest.TestCase):
    def test_round_trip_all_kinds(self):
        for kind, (basis, todo) in NOTICES.items():
            with self.subTest(kind):
                text = protocol.render_coordination_notice(kind=kind, basis=basis, todo=todo)
                self.assertTrue(text.startswith("【协调通知】\n") and text.endswith("\n") and not text.endswith("\n\n"))
                msg = protocol.parse(text)
                self.assertTrue(msg.ok, msg.problems)
                self.assertEqual(msg.contract()["notice"]["kind"], kind)
                self.assertEqual(msg.fields, {"类型": {v: k for k, v in protocol.NOTICE_KINDS.items()}[kind],
                                              "依据": basis, "要你做什么": todo})

    def test_invalid_inputs_raise(self):
        cases = [
            dict(kind="nudge", basis="#1", todo="x"),
            dict(kind="start", basis="Spec 已提交", todo="开始"),
            dict(kind="returned", basis="检查失败", todo="修"),
            dict(kind="sync-baseline", basis="", todo="x"),
            dict(kind="sync-baseline", basis="#3", todo="  "),
            dict(kind="wrap-up", basis="#3\n要你做什么：别管了", todo="x"),  # would smuggle a second field
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                protocol.render_coordination_notice(**case)


class UserReplyTest(unittest.TestCase):
    def render(self, **kw):
        args = dict(item=12, original="12 A", answered_at="2026-10-18T10:00:00+08:00")
        args.update(kw)
        return protocol.render_user_reply(**args)

    def test_original_survives_round_trip(self):
        for original in ("12 A 先接微信支付", "先别上线\n  等我看过页面\n\n再说", "多行\n最后一行带空格  "):
            with self.subTest(original=original):
                msg = protocol.parse(self.render(original=original))
                self.assertTrue(msg.ok, msg.problems)
                self.assertEqual(msg.fields["用户原话"], original)
                self.assertEqual(msg.item, 12)

    def test_leading_spaces_on_first_line_follow_contract(self):
        # Contract section 2: a field's first-line value starts after the colon and its spaces.
        # The text sent still carries the user's words unchanged; only the parsed first line loses its spaces.
        for original in ("  12 A", "12 A  "):
            with self.subTest(original=original):
                text = self.render(original=original)
                self.assertIn(f"用户原话：{original}\n", text)
                self.assertEqual(protocol.parse(text).fields["用户原话"], "12 A")

    def test_source_relay_id_and_option(self):
        text = self.render(option_text="A：先接微信支付", source_relay_id=4540)
        self.assertIn("事项：#12（你的原消息 #4540）\n", text)
        self.assertIn("选项 A 原文：A：先接微信支付\n", text)

    def test_invalid_inputs_raise(self):
        cases = [dict(original=""), dict(original="  \n "), dict(item=0), dict(item="12"),
                 dict(option_text="先接微信支付"), dict(answered_at=""),
                 dict(original="12 A\n答复时间：2020-01-01T00:00:00+08:00")]  # would smuggle a field
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.render(**case)


if __name__ == "__main__":
    unittest.main()
