"""S24 (LIVE-SAAS, T88): host-check false alarms in a light task's worktree and after the installed version moved on."""

from __future__ import annotations

import unittest

from helpers import ReviewCase, make_worktree
from test_light_task import new_task, register_task

from module_crew import hooks, hostcheck, store


def check(rep, cid):
    return next(c for c in rep.checks if c["id"] == cid)


class S24Case(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")
        self.n = new_task(self.db, self.repo, kind="bug")
        self.wt = make_worktree(self.repo, f"task-t{self.n}")
        self.name = register_task(self.db, self.n, self.wt)

    def set_recorded(self, version):
        with self.db.transaction(actor="t") as tx:
            tx.put("config", "main", dict(tx.get("config", "main"), pluginVersion=version), action="set")


class TaskWorktreeTest(S24Case):
    def test_registered_task_session_passes(self):
        rep = hostcheck.run(self.wt)
        self.assertEqual(rep.role, "task")
        reg = check(rep, "registered")
        self.assertTrue(reg["ok"], reg)
        self.assertIn(f"轻任务 T{self.n}", reg["reason"])
        self.assertIn(self.name, reg["reason"])
        self.assertEqual(rep.host, "claude-desktop")
        self.assertEqual({c["id"] for c in rep.checks} >= {"version", "git-writable", "commit-hooks"}, True)
        self.assertEqual(rep.code, 0, [c for c in rep.checks if not c["ok"]])


class VersionAgainstFixedEntryTest(S24Case):
    def test_old_record_but_entry_runs_same_version(self):
        self.plugins.install("module-crew", {"version": hostcheck.plugin_version()})
        self.set_recorded("0.0.1")
        ver = check(hostcheck.run(self.wt), "version")
        self.assertTrue(ver["ok"], ver)
        self.assertIn("固定入口", ver["reason"])

    def test_entry_runs_other_version(self):
        self.plugins.install("module-crew", {"version": "9.8.7"})
        self.set_recorded(hostcheck.plugin_version())
        ver = check(hostcheck.run(self.wt), "version")
        self.assertFalse(ver["ok"], ver)
        self.assertIn("9.8.7", ver["reason"])

    def test_no_install_falls_back_to_recorded(self):
        self.set_recorded("0.0.1")                  # the fake plugin records have no module-crew
        self.assertFalse(check(hostcheck.run(self.wt), "version")["ok"])
        self.set_recorded(hostcheck.plugin_version())
        self.assertTrue(check(hostcheck.run(self.wt), "version")["ok"])


if __name__ == "__main__":
    unittest.main()
