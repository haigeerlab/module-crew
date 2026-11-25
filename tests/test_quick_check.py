"""scripts/quick_check.py picks only the tests touched by a branch, and falls back to the full check (T652)."""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import PLUGIN_ROOT

_spec = importlib.util.spec_from_file_location("quick_check", PLUGIN_ROOT / "scripts" / "quick_check.py")
qc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qc)

TESTS = {
    "test_alpha.py": "from module_crew import alpha, store\n",
    "test_beta.py": "from module_crew import (\n    beta,\n)\n",
    "test_patch.py": "mock.patch('module_crew.alpha.run')\n",
    "test_other.py": "from module_crew import store\n",
    "test_docs.py": "", "test_skills.py": "", "test_glossary.py": "",
}


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True).stdout


class RepoCase(unittest.TestCase):
    """A throwaway repo shaped like this one: module_crew/, tests/, docs/, branch task/x off main."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "t")
        for rel, text in {**{f"tests/{k}": v for k, v in TESTS.items()},
                          "module_crew/alpha.py": "", "module_crew/beta.py": "", "module_crew/gamma.py": "",
                          "docs/guide.md": "", "README.md": "", "spec/m.md": "", "bin/x": ""}.items():
            self.write(rel, text)
        self.commit("base")
        git(self.root, "checkout", "-q", "-b", "task/x")

    def write(self, rel, text="changed\n"):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def commit(self, msg="c"):
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", msg)

    def plan(self):
        return qc.plan(self.root)


class SelectTest(RepoCase):
    def test_one_module_runs_only_tests_referencing_it(self):
        self.write("module_crew/alpha.py", "x = 1\n")
        self.commit()
        args, lines = self.plan()
        self.assertEqual(args, ["-m", "unittest", "test_alpha", "test_glossary", "test_patch"])
        self.assertIn("main", lines[0])
        self.assertTrue(any("test_alpha" in l and "module_crew/alpha.py" in l for l in lines))

    def test_parenthesised_import_counts(self):
        self.write("module_crew/beta.py", "x = 1\n")
        self.commit()
        self.assertEqual(self.plan()[0], ["-m", "unittest", "test_beta", "test_glossary"])

    def test_changed_test_file_runs_itself(self):
        self.write("tests/test_other.py", "from module_crew import store\n# more\n")
        self.commit()
        args, lines = self.plan()
        self.assertEqual(args, ["-m", "unittest", "test_other"])
        self.assertTrue(any("改了测试文件 tests/test_other.py" in l for l in lines))

    def test_uncommitted_and_untracked_changes_count(self):
        self.write("tests/test_other.py", "# edited\n")
        self.write("tests/test_new.py", "")
        self.assertEqual(self.plan()[0], ["-m", "unittest", "test_new", "test_other"])

    def test_docs_run_doc_tests(self):
        self.write("docs/guide.md")
        self.write("README.md")
        self.commit()
        args, lines = self.plan()
        self.assertEqual(args, ["-m", "unittest", "test_docs", "test_glossary", "test_skills"])
        self.assertIn("  test_docs：文档类改动 README.md 等 2 个文件", lines)

    def test_spec_and_tasks_are_skipped(self):
        self.write("spec/m.md")
        self.write("tests/test_other.py", "# edited\n")
        self.commit()
        args, lines = self.plan()
        self.assertEqual(args, ["-m", "unittest", "test_other"])
        self.assertTrue(any("跳过 1 个" in l for l in lines))

    def test_unmapped_file_falls_back(self):
        self.write("module_crew/alpha.py", "x = 1\n")
        self.write("bin/x")
        self.commit()
        args, lines = self.plan()
        self.assertEqual(args, qc.FULL)
        self.assertIn("bin/x 对不上号", lines[0])

    def test_unreferenced_module_falls_back(self):
        self.write("module_crew/gamma.py", "x = 1\n")
        self.commit()
        args, lines = self.plan()
        self.assertEqual(args, qc.FULL)
        self.assertIn("没有测试文件引用 module_crew/gamma.py", lines[0])

    def test_deleted_file_falls_back(self):
        git(self.root, "rm", "-q", "module_crew/alpha.py")
        self.commit()
        self.assertEqual(self.plan()[0], qc.FULL)

    def test_no_change_falls_back(self):
        args, lines = self.plan()
        self.assertEqual(args, qc.FULL)
        self.assertIn("没有改动", lines[0])

    def test_only_skipped_files_fall_back(self):
        self.write("spec/m.md")
        self.commit()
        self.assertEqual(self.plan()[0], qc.FULL)

    def test_missing_integration_branch_falls_back(self):
        git(self.root, "branch", "-q", "-m", "main", "trunk")
        self.write("tests/test_other.py", "# edited\n")
        self.commit()
        args, lines = self.plan()
        self.assertEqual(args, qc.FULL)
        self.assertIn("merge-base", lines[0])

    def test_reads_integration_branch_from_store(self):
        git(self.root, "branch", "-q", "-m", "main", "trunk")
        self.write("tests/test_other.py", "# edited\n")
        self.commit()
        orig = qc.integration_branch
        qc.integration_branch = lambda root: "trunk"
        self.addCleanup(setattr, qc, "integration_branch", orig)
        args, lines = self.plan()
        self.assertEqual(args, ["-m", "unittest", "test_other"])
        self.assertIn("trunk", lines[0])

    def test_store_branch_is_read_or_defaults_to_main(self):
        self.assertEqual(qc.integration_branch(self.root), "main")   # no store in the throwaway repo


class RunTest(RepoCase):
    def test_runs_without_arguments_and_keeps_unittest_exit_code(self):
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "quick_check.py").write_text(
            (PLUGIN_ROOT / "scripts" / "quick_check.py").read_text(encoding="utf-8"), encoding="utf-8")
        self.write("module_crew/__init__.py", "")
        self.write("tests/helpers.py", "")
        self.commit("script")
        git(self.root, "branch", "-q", "-f", "main")
        self.write("tests/test_other.py", "import unittest\nfrom helpers import *\n"
                                          "class T(unittest.TestCase):\n    def test_x(self):\n        self.fail()\n")
        self.commit()
        env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}   # CI writes bytecode (T760)
        done = subprocess.run([sys.executable, "scripts/quick_check.py"], cwd=self.root, capture_output=True,
                              text=True, timeout=120, env=env)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("test_other：改了测试文件", done.stdout)
        self.assertIn("FAILED", done.stderr)
        self.write("tests/test_other.py", "import unittest\nclass T(unittest.TestCase):\n    def test_x(self):\n"
                                          "        pass\n")
        done = subprocess.run([sys.executable, "scripts/quick_check.py"], cwd=self.root, capture_output=True,
                              text=True, timeout=120, env=env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
