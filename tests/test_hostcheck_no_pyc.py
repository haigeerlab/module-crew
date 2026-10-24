"""T167: reading the store's fixed entry must not leave a bytecode cache in the store (in a Codex sandbox that is .git)."""

from __future__ import annotations

import os
import sys
import unittest

from test_hostcheck_s24 import S24Case

from module_crew import hostcheck


class NoBytecodeTest(S24Case):
    def setUp(self):
        super().setUp()
        # Behave like a shell without PYTHONDONTWRITEBYTECODE, whatever the runner was started with.
        saved_env = os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
        saved_flag = sys.dont_write_bytecode
        sys.dont_write_bytecode = False

        def restore():
            sys.dont_write_bytecode = saved_flag
            if saved_env is not None:
                os.environ["PYTHONDONTWRITEBYTECODE"] = saved_env
        self.addCleanup(restore)
        self.plugins.install("module-crew", {"version": hostcheck.plugin_version()})

    def snapshot(self):
        return {str(p): p.read_bytes() for p in self.db.path.rglob("*") if p.is_file() and p.name != ".lock"}

    def test_entry_version_writes_no_pyc(self):
        before = self.snapshot()
        self.assertEqual(hostcheck.entry_version(self.db), hostcheck.plugin_version())
        self.assertEqual(sorted(self.snapshot()), sorted(before))
        self.assertEqual(list(self.db.path.rglob("__pycache__")), [])
        self.assertFalse(sys.dont_write_bytecode)

    def test_host_check_leaves_store_unchanged(self):
        before = self.snapshot()
        hostcheck.run(self.wt)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
