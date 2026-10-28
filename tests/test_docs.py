"""Public docs stay consistent with the code (crew-docs decision 7)."""

import json
import re
import subprocess
import sys
import unittest

from module_crew import handover

ROOT = handover.PLUGIN_ROOT
PUBLIC = ("README.md", "README.en.md", "docs/guide.md", "docs/commands.md", "docs/architecture.md",
          "CONTRIBUTING.md", "SECURITY.md")
LINK = re.compile(r"\]\(([^)\s]+)\)")


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def command_groups():
    out = subprocess.run([str(ROOT / "bin" / "module-crew"), "--help"], capture_output=True, text=True, timeout=60,
                         check=True).stdout
    return re.search(r"\{([a-z,-]+)\}", out).group(1).split(",")


class CommandsTest(unittest.TestCase):
    def test_every_group_has_a_section(self):
        headings = [line for line in read("docs/commands.md").splitlines() if line.startswith("#")]
        groups = command_groups()
        self.assertGreater(len(groups), 20)
        for group in groups:
            with self.subTest(group=group):
                self.assertTrue(any(f"`{group}`" in line for line in headings), group)


class LinksTest(unittest.TestCase):
    def test_readmes_link_each_other(self):
        self.assertIn("](README.en.md)", read("README.md"))
        self.assertIn("](README.md)", read("README.en.md"))

    def test_relative_links_resolve(self):
        for rel in PUBLIC:
            base = (ROOT / rel).parent
            for target in LINK.findall(read(rel)):
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                with self.subTest(file=rel, target=target):
                    self.assertFalse(target.startswith("../") and not (base / target).resolve().is_relative_to(ROOT),
                                     "points outside the repository")
                    self.assertTrue((base / target.split("#")[0]).exists())

    def test_no_outside_or_local_paths(self):
        for rel in PUBLIC:
            text = read(rel)
            with self.subTest(file=rel):
                self.assertFalse("/Users/" in text, "local absolute path")
                if rel.count("/") == 0:
                    self.assertFalse("](../" in text, "link outside the repository")


class ReadmeTest(unittest.TestCase):
    def test_no_per_version_sections(self):
        for rel in ("README.md", "README.en.md"):
            with self.subTest(file=rel):
                self.assertIsNone(re.search(r"^#+ .*\d+\.\d+\.\d+", read(rel), re.M))

    def test_version_line_matches_plugin(self):
        version = json.loads(read(".claude-plugin/plugin.json"))["version"]
        self.assertIn(f"版本 {version}", read("README.md"))
        self.assertIn(f"Version {version}", read("README.en.md"))


if __name__ == "__main__":
    unittest.main()
