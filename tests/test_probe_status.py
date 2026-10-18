import json
import os
import unittest

from helpers import ProbeCase, spec_guard_interface

from module_crew import probe, store


def tree(*roots):
    out = {}
    for root in roots:
        for p in root.rglob("*"):
            if p.is_file():
                out[str(p)] = p.stat().st_mtime_ns
    return out


class StatusCase(ProbeCase):
    def setUp(self):
        super().setUp()
        self.plugins.install("agent-relay", {"interface": "2.0"})
        os.environ["FAKE_MAP_MODE"] = "on"
        self.plugins.install("spec-guard", spec_guard_interface("1.1"), map_script=True)

    def seed_store(self):
        db, _ = store.init_store(self.repo)
        with db.transaction(actor="coord") as tx:
            tx.put("session", "shop-coord", {"role": "coordinator", "host": "claude-desktop", "status": "active"},
                   action="registered")
            tx.put("session", "shop-a", {"role": "dev", "host": "claude-desktop", "status": "retired",
                                         "module": "a", "worktree": "/tmp/a"}, action="registered")
            tx.put("item", "1", {"state": "open"}, action="created")
            tx.put("item", "2", {"state": "closed"}, action="closed")
            tx.put("ticket", "3", {}, action="opened")
        return db


class ReportTest(StatusCase):
    def test_no_store_is_warning_only(self):
        report = probe.run(self.repo)
        self.assertEqual(report.checks["store"].state, "warning")
        self.assertIsNone(report.store)
        self.assertFalse(report.blocked, {k: c.reason for k, c in report.checks.items() if c.state == "blocker"})

    def test_store_summary(self):
        self.seed_store()
        report = probe.run(self.repo)
        self.assertEqual(report.checks["store"].state, "ok")
        self.assertEqual([s["name"] for s in report.store["sessions"]], ["shop-coord"])
        self.assertEqual(report.store["open"], {"item": 1, "request": 0, "ticket": 1})

    def test_check_ids_fixed(self):
        report = probe.run(self.repo)
        self.assertEqual(list(report.checks), ["git", "agent-relay", "spec-guard", "spec-guard-planning",
                                               "baseline", "store"])

    def test_run_is_read_only(self):
        db = self.seed_store()
        (db.path / "state" / "item.json").rename(db.path / "moved")  # a lagging snapshot must not be rewritten
        before = tree(self.repo, db.path)
        probe.run(self.repo)
        self.run_cli("status")
        self.run_cli("status", "--json")
        self.assertEqual(tree(self.repo, db.path), before)


class CliTest(StatusCase):
    def test_human_output(self):
        self.seed_store()
        r = self.run_cli("status")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for words in ("spec-guard-planning", "shop-coord", "事项 1", "等待单 1", "模块 1/3", "spec-guard 进行中：b",
                      "模块会话：Claude 或 Codex 桌面版"):
            self.assertIn(words, r.stdout)

    def test_json_output(self):
        r = self.run_cli("status", "--json")
        doc = json.loads(r.stdout)
        self.assertEqual(doc["schemaVersion"], 1)
        self.assertFalse(doc["blocked"])
        self.assertEqual([c["id"] for c in doc["checks"]][0], "git")
        self.assertEqual(doc["map"], {"done": 1, "total": 3, "activeModule": "b", "inProgress": ["b"]})

    def test_blocker_exit_3(self):
        (self.repo / "dirty.txt").write_text("x")
        r = self.run_cli("status")
        self.assertEqual(r.returncode, 3)
        self.assertIn("集成基线不干净", r.stdout)

    def test_outside_repo_exit_2(self):
        outside = self.tmp / "plain"
        outside.mkdir()
        self.assertEqual(self.run_cli("status", cwd=outside).returncode, 2)


if __name__ == "__main__":
    unittest.main()
