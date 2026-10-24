"""T170: the Codex crew-dev skill says how to work a reopened module, like the Claude one does."""

import unittest

from helpers import PLUGIN_ROOT


class CodexDevReopenTest(unittest.TestCase):
    def read(self, rel):
        return (PLUGIN_ROOT / rel).read_text(encoding="utf-8")

    def test_codex_crew_dev_describes_reopen(self):
        for rel in ("skills/crew-dev/SKILL.md", "codex-skills/crew-dev/SKILL.md"):
            with self.subTest(rel):
                text = self.read(rel)
                for words in ("**重开修订**", "只做 `tasks/<模块>/todo.md` 里新加的未勾项", "已勾的不要重做",
                              "带后缀的新邮箱名"):
                    self.assertIn(words, text)


if __name__ == "__main__":
    unittest.main()
