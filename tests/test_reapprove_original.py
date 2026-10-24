"""T168: re-submitting a returned final acceptance may reuse the original approval only when the product files match;
Codex calls module-crew through the fixed entry's absolute path (T134 finding)."""

import unittest

from helpers import PLUGIN_ROOT

SKILLS = ("skills/crew-coordinator/SKILL.md", "codex-skills/crew-coordinator/SKILL.md")


def read(rel: str) -> str:
    return (PLUGIN_ROOT / rel).read_text(encoding="utf-8")


class ReapproveOriginalTest(unittest.TestCase):
    def test_coordinator_skills_compare_product_files(self):
        for rel in SKILLS:
            with self.subTest(rel):
                text = read(rel)
                for words in ("最终验收被退回后重新交审", "新交审提交与原批准提交按产品文件比对",
                              "产品文件逐个无差异", "沿用原批准原话登记",
                              "沿用原批准 C<号>，依据：产品文件无差异", "比了哪些文件、各自一致",
                              "有任何差异就要用户给新原话",
                              "两个提交之间有变化的文件，去掉内容已与集成分支完全相同的"):
                    self.assertIn(words, text)

    def test_codex_skill_absolute_entry(self):
        text = read("codex-skills/crew-coordinator/SKILL.md")
        for words in ("一律用固定入口的绝对路径", "<项目>/.git/module-crew/bin/module-crew",
                      "相对路径命中不了前缀放行规则"):
            self.assertIn(words, text)


if __name__ == "__main__":
    unittest.main()
