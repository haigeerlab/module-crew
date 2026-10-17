import ast
import json
import re
import sys
import unittest

from helpers import PLUGIN_ROOT, RepoCase, git, make_worktree

PKG = PLUGIN_ROOT / "module_crew"


class ManifestTest(unittest.TestCase):
    def test_manifest_is_valid_json_named_module_crew(self):
        doc = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(doc["name"], "module-crew")
        self.assertRegex(doc["version"], r"^\d+\.\d+\.\d+$")


class StaticScanTest(unittest.TestCase):
    def _sources(self):
        files = sorted(PKG.glob("*.py"))
        self.assertTrue(files)
        return files

    def test_only_stdlib_imports(self):
        for path in self._sources():
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [node.module]
                else:
                    continue
                for name in names:
                    top = name.split(".")[0]
                    self.assertTrue(top in sys.stdlib_module_names or top == "module_crew",
                                    f"{path.name}: non-stdlib import {name}")

    def test_no_deletion_calls(self):
        for path in self._sources():
            text = path.read_text()
            for word in ("unlink", "rmtree", "truncate", "os.remove", "rmdir"):
                self.assertNotIn(word, text, f"{path.name} uses {word}")


class HelpersTest(RepoCase):
    def test_repo_and_worktree(self):
        wt = make_worktree(self.repo, "wt1")
        self.assertTrue((wt / "README.md").exists())
        self.assertIn("wt1", git(self.repo, "worktree", "list"))

    def test_cli_wrapper_runs(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertIn("用法", result.stderr)


if __name__ == "__main__":
    unittest.main()
