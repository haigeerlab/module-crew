"""0.10.1: git prints a UTC commit date as ...Z, which Python 3.10's fromisoformat refuses (spec-guard trial, K9F9VF1)."""

import os
import subprocess
import unittest

from helpers import ReviewCase, git

from module_crew import failure, stall, store


def utc_commit(path, name="utc.txt"):
    from datetime import datetime, timezone
    (path / name).write_text("x\n", encoding="utf-8")
    git(path, "add", name)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000")     # after the module started
    env = dict(os.environ, GIT_COMMITTER_DATE=now, GIT_AUTHOR_DATE=now)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "utc"], check=True, env=env)


class UtcCommitTest(ReviewCase):
    def test_git_prints_z(self):
        utc_commit(self.repo)
        self.assertTrue(git(self.repo, "log", "-1", "--format=%cI").strip().endswith("Z"))

    def test_first_parents_reads_utc(self):
        utc_commit(self.repo)
        chain = stall._first_parents(self.repo)
        self.assertEqual(chain[0][1].utcoffset().total_seconds(), 0)

    def test_status_with_utc_commits(self):
        utc_commit(self.repo)
        utc_commit(self.wt["b"], "b-utc.txt")
        rows = failure.sessions(store.open_store(self.repo))
        self.assertTrue(rows)
        out = self.run_cli("status")
        self.assertNotIn("Traceback", out.stderr)
        self.assertIn("会话与待办", out.stdout)
        self.assertIn("模块进度", out.stdout)              # the whole report printed, not cut at the crash


if __name__ == "__main__":
    unittest.main()
