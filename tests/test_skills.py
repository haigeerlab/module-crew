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

    def test_dev_rules(self):
        _, text = read("crew-dev")
        for words in ("protocol check", "【等待其他会话】", "【交审】", "最终验收", "收到用户对 #N 的答复：『原话』",
                      "【公共变更请求】", "不是批准", "不要抄进 worktree 的 CLAUDE.md"):
            self.assertIn(words, text)


if __name__ == "__main__":
    unittest.main()
