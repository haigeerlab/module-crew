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
        section = text.split("## 同步集成基线", 1)[1].split("\n## ", 1)[0]
        for words in ("git merge", "取集成分支的版本", "--theirs", "评审标记"):
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
        section = text.split("## 等待单", 1)[1].split("\n## ", 1)[0]
        for words in ("【已恢复】", "ticket close", "--reason happened", "--reason user"):
            self.assertIn(words, section)
        merge_section = text.split("## 合并与收尾", 1)[1].split("\n## ", 1)[0]
        self.assertIn("/agent-relay:collaboration", merge_section)
        self.assertIn("不要自己去找或猜", merge_section)
