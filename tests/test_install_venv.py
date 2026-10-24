"""T135 (from T62's review): a project with only requirements*.txt got `.venv/bin/pip install -r ...` as its first
step, but a new worktree has no .venv, so the command could not run. The kickoff now creates the venv first, and
that one exact command is allowed on both hosts (never `python3 *`)."""

import fnmatch
import shutil
import tempfile
import unittest
from pathlib import Path

from module_crew import permissions, start

VENV = "python3 -m venv .venv"


class InstallVenvTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="crew-test-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "requirements.txt").write_text("x\n", encoding="utf-8")

    def test_requirements_without_venv_creates_it_first(self):
        self.assertEqual(start.install_commands(self.root), [VENV, ".venv/bin/pip install -r requirements.txt"])

    def test_existing_venv_is_not_created_again(self):
        (self.root / ".venv").mkdir()
        self.assertEqual(start.install_commands(self.root), [".venv/bin/pip install -r requirements.txt"])

    def test_uv_lock_needs_no_venv_step(self):
        (self.root / "uv.lock").write_text("x\n", encoding="utf-8")
        self.assertEqual(start.install_commands(self.root), ["uv sync"])

    def test_venv_command_allowed_exactly_on_both_hosts(self):
        self.assertTrue(any(fnmatch.fnmatchcase(VENV, pat) for pat in permissions.LOCKFILE_CLAUDE))
        self.assertIn(VENV, permissions.LOCKFILE_CODEX)
        for wider in ("python3 -m venv /tmp/x", "python3 -c pass", "python3 -m pip install x"):
            with self.subTest(cmd=wider):
                self.assertFalse(any(fnmatch.fnmatchcase(wider, pat) for pat in permissions.LOCKFILE_CLAUDE))
                self.assertFalse(any(wider == pre or wider.startswith(pre + " ")
                                     for pre in permissions.LOCKFILE_CODEX))


if __name__ == "__main__":
    unittest.main()
