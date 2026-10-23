import unittest

from helpers import PLUGIN_ROOT

SKILL_FILES = (
    PLUGIN_ROOT / "skills" / "crew-coordinator" / "SKILL.md",
    PLUGIN_ROOT / "codex-skills" / "crew-coordinator" / "SKILL.md",
)

# S25：LIVE-SAAS 后台 C3 被 commitlint 拒后，协调把提交信息包装成推荐回复，
# 用户照贴后手工 git commit 绕开了 review approve。
RULES = (
    "批准一律走 `review approve`",
    "失败就停下，把输出原样报给用户，不手工补提交",
    "不在集成 checkout 手工提交 Spec、Plan 或批准标记",
    "不把提交信息或命令包装成给用户的「推荐回复」",
)


class CoordinatorNoManualCommitTest(unittest.TestCase):
    def test_both_skills_forbid_manual_commit(self):
        for path in SKILL_FILES:
            text = path.read_text(encoding="utf-8")
            section = text.split("module-crew review approve <交审事项编号>", 1)[1].split("\n## ", 1)[0]
            for words in RULES:
                with self.subTest(path=path.parent.parent.name, words=words):
                    self.assertIn(words, section)


if __name__ == "__main__":
    unittest.main()
