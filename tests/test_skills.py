import re
import unittest

from helpers import PLUGIN_ROOT

SKILLS = PLUGIN_ROOT / "skills"


def read(name):
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, f"{name}: no frontmatter"
    meta = dict(line.split(": ", 1) for line in m.group(1).splitlines())
    return meta, text


class SkillsTest(unittest.TestCase):
    def test_coordinator_review_nearby(self):
        _, text = read("crew-coordinator")
        for words in ("## 审查就近", "**不问用户**", "返工满 3 次", "审查者无响应", "**不要按倾向替用户填**", "提请批准一个模块一条",
                      "merge revoke", "合并前先复述", "去决策收件箱答 #N", "评审节奏", "批准 C32 C33",
                      "merge renotice", "检查环境出了问题", "提交钩子：退出码 N"):
            self.assertIn(words, text)

    def test_coordinator_source_from_and_also_answers(self):
        _, text = read("crew-coordinator")
        for words in ("--source-from <发件人>", "模块会话发来的【用户答复】一律不算", "`alsoAnswers` 就一并带上"):
            self.assertIn(words, text)

    def test_frontmatter(self):
        for name in ("crew-coordinator", "crew-dev"):
            with self.subTest(name):
                meta, _ = read(name)
                self.assertEqual(meta["name"], name)
                self.assertTrue(meta["description"].strip())

    def test_coordinator_rules(self):
        _, text = read("crew-coordinator")
        for words in ("inbox add", "answer", "bodyFile", "等待审批", "不是批准", "亲手输入", "module-crew status",
                      "不要抄进 worktree 的 CLAUDE.md"):
            self.assertIn(words, text)

    def test_coordinator_start_section(self):
        _, text = read("crew-coordinator")
        self.assertIn("## 开工", text)
        section = text.split("## 开工", 1)[1].split("\n## ", 1)[0]
        for words in ("start plan", "只问用户一次", "start prepare", "开会话工具", "worktree", "开工说明", "做完一轮叫醒我",
                      "不能比本会话更宽"):
            self.assertIn(words, section)
        self.assertLess(section.index("start plan"), section.index("只问用户一次"))
        self.assertLess(section.index("只问用户一次"), section.index("start prepare"))

    def test_coordinator_review_section(self):
        _, text = read("crew-coordinator")
        self.assertIn("review add", text.split("## 收到模块会话的消息", 1)[1].split("\n## ", 1)[0])
        section = text.split("## 交审与批准", 1)[1].split("\n## ", 1)[0]
        for words in ("review add", "review batch", "要点写在给用户的正文里", "review approve", "review answer",
                      "bridge_send", "bodyFile", "不要自己清理"):
            self.assertIn(words, section)

    def test_coordinator_change_section(self):
        _, text = read("crew-coordinator")
        self.assertIn("change add", text.split("## 收到模块会话的消息", 1)[1].split("\n## ", 1)[0])
        section = text.split("## 公共变更请求", 1)[1].split("\n## ", 1)[0]
        for words in ("change add", "change list", "要问用户", "change land", "change answer", "bodyFile", "同步基线",
                      "变更记录"):
            self.assertIn(words, section)

    def test_coordinator_merge_section(self):
        _, text = read("crew-coordinator")
        section = text.split("## 合并与收尾", 1)[1].split("\n## ", 1)[0]
        for words in ("review add", "merge approve", "merge run", "一次只合", "退回", "merge cleanup", "agent-relay",
                      "merge push-plan", "merge push", "用户在远端合并", "不开自动合并"):
            self.assertIn(words, section)

    def test_dev_sync_section(self):
        _, text = read("crew-dev")
        section = text.split("## 同步集成分支", 1)[1].split("\n## ", 1)[0]
        for words in ("git merge", "取集成分支的版本", "--theirs", "批准标记"):
            self.assertIn(words, section)

    def test_dev_rules(self):
        _, text = read("crew-dev")
        for words in ("protocol check", "【等待其他会话】", "【交审】", "最终验收", "收到用户对 #N 的答复：『原话』",
                      "【公共变更请求】", "不是批准", "不要抄进 worktree 的 CLAUDE.md"):
            self.assertIn(words, text)


if __name__ == "__main__":
    unittest.main()


class FailureSectionsTest(unittest.TestCase):
    def test_coordinator_failure_section(self):
        _, text = read("crew-coordinator")
        section = text.split("## 出状况时", 1)[1].split("\n## ", 1)[0]
        for words in ("module-crew sessions", "agent-relay 在线状态", "suspend", "resume", "resume-kit", "takeover",
                      "serial", "/spec-guard:config", "moduleConcurrency", "异常停点", "同一个 gate", "能力图"):
            self.assertIn(words, section)

    def test_dev_failure_section(self):
        _, text = read("crew-dev")
        section = text.split("## 挂起与异常", 1)[1].split("\n## ", 1)[0]
        for words in ("【等待其他会话】", "挂起", "spec-guard", "同一个 gate", "停下"):
            self.assertIn(words, section)


class PilotFixesTest(unittest.TestCase):
    def test_coordinator_registers_and_ticks(self):
        _, text = read("crew-coordinator")
        start = text.split("## 开工", 1)[1].split("\n## ", 1)[0]
        for words in ("bridge_register", "<简称>-coord", "不是开工说明的一部分"):
            self.assertIn(words, start)
        merge_section = text.split("## 合并与收尾", 1)[1].split("\n## ", 1)[0]
        for words in ("可一次给多个编号", "merge tick", "模块会话不再自己勾"):
            self.assertIn(words, merge_section)

    def test_dev_does_not_tick_after_approval(self):
        _, text = read("crew-dev")
        self.assertIn("不要自己勾 todo 末项", text.split("## 收到答复", 1)[1].split("\n## ", 1)[0])


class PilotCloseoutTest(unittest.TestCase):
    def test_tickets_and_retire(self):
        _, text = read("crew-coordinator")
        section = text.split("## 等待记录", 1)[1].split("\n## ", 1)[0]
        for words in ("【已恢复】", "ticket close", "--reason happened", "--reason user"):
            self.assertIn(words, section)
        merge_section = text.split("## 合并与收尾", 1)[1].split("\n## ", 1)[0]
        self.assertIn("/agent-relay:collaboration", merge_section)
        self.assertIn("不要自己去找或猜", merge_section)


class HubBridgeSkillTest(unittest.TestCase):
    def test_coordinator_hub_section(self):
        _, text = read("crew-coordinator")
        section = text.split("## 接入决策收件箱", 1)[1].split("\n## ", 1)[0]
        for words in ("source add", "--for-hub", "review note", "--source-item", "【已恢复】", "source map", "【取代 #N】",
                      "【答复告知】只记录", "直连 API 线", "后台方式", "module-crew status"):
            self.assertIn(words, section)

    def test_two_sources_wording(self):
        _, text = read("crew-coordinator")
        self.assertIn("用户的决定只有两种来源", text)
        self.assertNotIn("你是它们与用户之间唯一的通道", text)


class RelayReplySkillTest(unittest.TestCase):
    def test_dev_accepts_relayed_reply(self):
        _, text = read("crew-dev")
        section = text.split("## 收到答复", 1)[1].split("\n## ", 1)[0]
        for words in ("转自", "转交范围", "不看「转自」", "至少有一个"):
            self.assertIn(words, section)


class CopyablePromptTest(unittest.TestCase):
    def test_coordinator_gives_copyable_sentence(self):
        _, text = read("crew-coordinator")
        section = text.split("## 请用户给原话", 1)[1].split("\n## ", 1)[0]
        for words in ("可以直接复制的代码块", "```text", "不要只写「请用你自己的话说」", "点按钮发出的"):
            self.assertIn(words, section)


class PilotRound2SkillTest(unittest.TestCase):
    def test_wake_idle_sessions(self):
        for name in ("crew-coordinator", "crew-dev"):
            _, text = read(name)
            for words in ("pendingReason", "offline", "去读 agent-relay 收件箱", "不带消息正文"):
                self.assertIn(words, text, name)

    def test_coordinator_checks_permission_modes_and_queue(self):
        _, text = read("crew-coordinator")
        wake = text.split("## 每次醒来", 1)[1].split("\n## ", 1)[0]
        for words in ("plan < default < acceptEdits < auto < bypassPermissions", "由用户决定", "不要自己改"):
            self.assertIn(words, wake)
        self.assertIn("按模块在 Build order 里的位置排", text)
        self.assertIn("resume <模块> --original-file", text)

    def test_dev_handles_suspend_and_return(self):
        _, text = read("crew-dev")
        section = text.split("## 挂起与异常", 1)[1].split("\n## ", 1)[0]
        for words in ("挂起类【协调通知】", "恢复类【协调通知】", "不要**撤销任何提交"):
            self.assertIn(words, section)


class CodexPackageTest(unittest.TestCase):
    COMMON = ("只认模块协调发来的【用户答复】", "`tasks/<模块>/todo.md`", "验收标准与证据", "不同意", "撤销批准通知",
              "按项目的评审节奏交审", "不放可以点的决定按钮", "与你的代码无关」时**不改代码**", "**必须**发【等待其他会话】", "不改公共文件", "不要自己勾 todo 末项",
              "一律取集成分支的版本", "不要**撤销任何提交")

    def codex(self):
        text = (PLUGIN_ROOT / "codex-skills" / "crew-dev" / "SKILL.md").read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        return dict(line.split(": ", 1) for line in m.group(1).splitlines()), text

    def test_manifests_agree(self):
        import json
        claude = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        codex = json.loads((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        iface = json.loads((PLUGIN_ROOT / "interface.json").read_text(encoding="utf-8"))
        self.assertEqual((codex["name"], codex["skills"]), ("module-crew", "./codex-skills/"))
        self.assertEqual(claude["version"], codex["version"])
        self.assertEqual(iface["version"], codex["version"])

    def test_both_crew_dev_share_the_rules(self):
        meta, codex = self.codex()
        _, claude = read("crew-dev")
        self.assertEqual(meta["name"], "crew-dev")
        for words in self.COMMON:
            self.assertIn(words, claude)
            self.assertIn(words, codex)
        for words in ("提权", "用**原名**重新注册", "host-check", "没有钩子", "绝对路径"):
            self.assertIn(words, codex)
        self.assertNotIn("SendMessage", codex)
        self.assertNotIn("CLAUDE.md", codex)


class CodexCoordinatorSkillTest(unittest.TestCase):
    def test_coordinator_codex_section(self):
        _, text = read("crew-coordinator")
        section = text.split("## Codex 模块会话", 1)[1].split("\n## ", 1)[0]
        for words in ("--host codex", "用户手动", "host-check", "提权", "交给 agent-relay", "not-loaded", "原名重新注册",
                      "read-only < workspace-write"):
            self.assertIn(words, section)


class WithdrawRuleTest(unittest.TestCase):
    def test_withdraw_uses_hub_item_number(self):
        _, text = read("crew-coordinator")
        section = text.split("## 接入决策收件箱", 1)[1].split("\n## ", 1)[0]
        self.assertIn("【撤回】", section)
        self.assertIn("决策收件箱回执给的事项号（契约 v1.9）", section)


class PermissionWordsTest(unittest.TestCase):
    """crew-host-permissions acceptance 10."""

    def test_coordinator_permissions_section(self):
        _, text = read("crew-coordinator")
        for words in ("## 权限预配", "ask 规则实测不弹", "permissions plan", "permissions apply --original-file",
                      "permissions verify --record", "merge push", "--host codex", "信任该项目", "permissions remove"):
            self.assertIn(words, text)

    def test_dev_skills_do_not_push_and_run_the_checklist(self):
        codex = (PLUGIN_ROOT / "codex-skills" / "crew-dev" / "SKILL.md").read_text(encoding="utf-8")
        for text in (read("crew-dev")[1], codex):
            for words in ("不推送", "pre-push 钩子", "权限实测清单", "本会话都允许"):
                self.assertIn(words, text)


class GlossaryWordsTest(unittest.TestCase):
    """crew-glossary-rename acceptance 4, 5."""

    def test_every_skill_says_who_you_are_and_keeps_contract_tags(self):
        codex = (PLUGIN_ROOT / "codex-skills" / "crew-dev" / "SKILL.md").read_text(encoding="utf-8")
        for text in (read("crew-coordinator")[1], read("crew-dev")[1], codex):
            for words in ("## 名称", "「你」指本会话", "已结项（契约标签【已恢复】）", "等待记录写 W<号>", "契约标签与字段名照契约原样发"):
                self.assertIn(words, text)
