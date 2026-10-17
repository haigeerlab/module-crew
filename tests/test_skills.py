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

    def test_dev_rules(self):
        _, text = read("crew-dev")
        for words in ("protocol check", "【等待其他会话】", "【交审】", "最终验收", "收到用户对 #N 的答复：『原话』",
                      "【公共变更请求】", "不是批准", "不要抄进 worktree 的 CLAUDE.md"):
            self.assertIn(words, text)


if __name__ == "__main__":
    unittest.main()
