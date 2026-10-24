"""S17: README no longer says the module coordinator can only run in Claude desktop."""

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class ReadmeHostsTest(unittest.TestCase):

    def setUp(self):
        self.text = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_prerequisite_host_row_mentions_handover_to_codex(self):
        row = re.search(r"^\| 宿主 \|(.*)\|$", self.text, re.M).group(1)
        for words in ("coordinator handover", "Codex 桌面版", "同一台 Mac"):
            with self.subTest(words=words):
                self.assertIn(words, row)
        self.assertNotIn("模块协调：Claude 桌面版（Code 标签）；", row)

    def test_opening_line_mentions_codex(self):
        first = next(line for line in self.text.splitlines() if line.startswith("让多个"))
        self.assertIn("Codex", first)

    def test_codex_module_section_not_claude_only(self):
        self.assertNotIn("模块协调仍在 Claude 桌面版", self.text)


if __name__ == "__main__":
    unittest.main()
