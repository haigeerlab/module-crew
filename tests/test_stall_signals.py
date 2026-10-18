"""crew-stall-signals: read-only facts in sessions --json for the decision inbox (spec/crew-stall-signals.md)."""

import shutil
import subprocess
import unittest
from datetime import datetime

from helpers import MergeCase, git

from module_crew import failure, hooks, store


class StallCase(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def rows(self):
        return {r["module"]: r for r in failure.sessions(self.db)}


class CommitFactsTest(StallCase):
    def test_commits_ahead_of_the_integration_branch(self):
        row = self.rows()["b"]
        self.assertEqual(row["commits"]["ahead"], 1)
        self.assertEqual(row["commits"]["last"]["commit"], git(self.wt["b"], "rev-parse", "HEAD").strip())
        self.assertEqual(row["commits"]["last"]["at"], git(self.wt["b"], "log", "-1", "--format=%cI").strip())
        datetime.fromisoformat(row["commits"]["last"]["at"])
        self.assertIsNone(row["commits"]["error"])
        (self.wt["b"] / "x.txt").write_text("x\n")
        git(self.wt["b"], "add", "x.txt")
        git(self.wt["b"], "commit", "-q", "-m", "b: more")
        self.assertEqual(self.rows()["b"]["commits"]["ahead"], 2)

    def test_no_commit_since_start(self):
        git(self.wt["b"], "reset", "-q", "--hard", "main")
        self.assertEqual(self.rows()["b"]["commits"], {"ahead": 0, "last": None, "error": None})

    def test_missing_worktree_only_affects_that_module(self):
        shutil.rmtree(self.wt["c"])
        rows = self.rows()
        self.assertEqual((rows["c"]["commits"]["ahead"], rows["c"]["commits"]["last"]), (None, None))
        self.assertIn("worktree", rows["c"]["commits"]["error"])
        self.assertEqual(rows["b"]["commits"]["ahead"], 1)
        out = self.run_cli("sessions", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_missing_integration_branch(self):
        with self.db.transaction(actor="test") as tx:
            tx.put("config", "main", dict(tx.get("config", "main"), integrationBranch="nope"), action="set")
        commits = self.rows()["b"]["commits"]
        self.assertEqual((commits["ahead"], commits["last"]), (None, None))
        self.assertTrue(commits["error"])


class StartedAtTest(StallCase):
    def test_started_at_is_the_registration_time_and_survives_takeover(self):
        reg = [e for e in store.events(self.db, key="shop-b") if e["type"] == "session.registered"][-1]
        self.assertEqual(self.rows()["b"]["startedAt"], reg["at"])
        hooks.takeover(self.db, "shop-b", "让新会话接管 b")
        self.assertEqual(self.rows()["b"]["startedAt"], reg["at"])


if __name__ == "__main__":
    unittest.main()
