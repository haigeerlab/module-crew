"""crew-coordinator-switch: per-session coordinator switch (see spec/crew-coordinator-switch.md)."""

from __future__ import annotations

import json
import os
import unittest

from helpers import ProbeCase, StartCase, git, spec_guard_interface

from module_crew import coordinator, probe, start, store


class EnabledCheckTest(ProbeCase):
    """Acceptance 2 (part): a project that never ran setup-convention is a blocker."""

    def setUp(self):
        super().setUp()
        self.plugins.install("agent-relay", {"interface": "2.0"})
        self.plugins.install("spec-guard", spec_guard_interface("1.7"), map_script=True)

    def test_enabled_when_config_present(self):
        report = probe.run(self.repo)
        self.assertEqual(report.checks["spec-guard-enabled"].state, "ok")

    def test_blocker_without_config(self):
        git(self.repo, "rm", "-q", ".agent/config.json")
        git(self.repo, "commit", "-q", "-m", "drop")
        check = probe.run(self.repo).checks["spec-guard-enabled"]
        self.assertEqual(check.state, "blocker")
        self.assertIn("setup-convention", check.fix)

    def test_no_capability_map_has_code(self):
        os.environ["FAKE_MAP_MODE"] = "exit3"
        check = probe.run(self.repo).checks["spec-guard"]
        self.assertEqual((check.state, check.code), ("blocker", "no-capability-map"))


class UpTest(StartCase):
    """Acceptance 1, 2, 3, 10."""

    def up(self, sid="sid-1", short="shop", original="把本会话升级为协调会话"):
        return coordinator.up(self.repo, short, original, session_id=sid)

    def test_up_registers_and_binds(self):
        code, lines = self.up()
        self.assertEqual(code, 0, lines)
        db = store.open_store(self.repo)
        rec = store.get(db, "session", "shop-coord")
        self.assertEqual((rec["role"], rec["status"], rec["hostSession"]["sessionId"]), ("coordinator", "active", "sid-1"))
        self.assertEqual(store.get(db, "config", "main")["maxModules"], 2)
        ev = [e for e in store.events(db) if e["type"] == "session.coordinator-up"]
        self.assertEqual(ev[-1]["data"]["original"], "把本会话升级为协调会话")
        self.assertTrue(any("bridge_register" in l and "shop-coord" in l for l in lines))

    def test_up_without_capability_map(self):
        os.environ.pop("FAKE_MAP_FILE")
        os.environ["FAKE_MAP_MODE"] = "exit3"
        code, lines = self.up()
        self.assertEqual(code, 0, lines)

    def test_up_refusals(self):
        self.assertEqual(self.up(original=" ")[0], 3)
        self.assertEqual(self.up(sid=None)[0], 3)       # RepoCase clears CLAUDE_CODE_SESSION_ID
        git(self.repo, "rm", "-q", ".agent/config.json")
        git(self.repo, "commit", "-q", "-m", "drop")
        code, lines = self.up()
        self.assertEqual(code, 3)
        self.assertTrue(any(l.startswith("spec-guard-enabled") for l in lines), lines)

    def test_dirty_baseline_refused(self):
        (self.repo / "dirty.txt").write_text("x")
        code, lines = self.up()
        self.assertEqual(code, 3)
        self.assertTrue(any(l.startswith("baseline") for l in lines), lines)

    def test_relay_missing_refused(self):
        self.plugins.entries.pop("agent-relay@m")
        self.plugins.write()
        code, lines = self.up()
        self.assertEqual(code, 3)
        self.assertTrue(any(l.startswith("agent-relay") for l in lines), lines)

    def test_one_coordinator(self):
        self.assertEqual(self.up()[0], 0)
        self.assertEqual(self.up(), (0, ["本会话已是模块协调 shop-coord，没有改动"]))
        code, lines = self.up(sid="sid-2")
        self.assertEqual(code, 3)
        text = "\n".join(lines)
        self.assertIn("已有模块协调 shop-coord", text)
        self.assertIn(str(self.repo), text)
        self.assertIn("分支 main", text)
        self.assertIn("takeover shop-coord", text)

    def test_prepare_reuses_coordinator(self):
        self.assertEqual(self.up()[0], 0)
        res = start.prepare(self.repo, ["b", "c"], "开 b 和 c", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        coords = [n for n, s in store.records(store.open_store(self.repo), "session").items() if s["role"] == "coordinator"]
        self.assertEqual(coords, ["shop-coord"])

    def test_default_max_is_two(self):
        self.assertEqual(start.DEFAULT_MAX, 2)

    def test_existing_max_kept(self):
        db = store.init_store(self.repo)[0]
        with db.transaction(actor="t") as tx:
            tx.put("config", "main", {"projectShort": "shop", "integrationBranch": "main", "maxModules": 3,
                                      "crewDir": str(self.tmp / "repo-crew")}, action="set")
        self.assertEqual(self.up(short=None)[0], 0)
        self.assertEqual(store.get(db, "config", "main")["maxModules"], 3)


class DownTest(StartCase):
    """Acceptance 4."""

    def test_down_refused_with_modules(self):
        res = start.prepare(self.repo, ["b"], "开 b", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        code, lines = coordinator.down(self.repo, "关掉协调会话")
        self.assertEqual(code, 3)
        self.assertIn("b（shop-b）", "\n".join(lines))

    def test_down_then_up_again(self):
        self.assertEqual(coordinator.up(self.repo, "shop", "升级", session_id="sid-1")[0], 0)
        self.assertEqual(coordinator.down(self.repo, "关掉", session_id="sid-1")[0], 0)
        rec = store.get(store.open_store(self.repo), "session", "shop-coord")
        self.assertEqual(rec["status"], "retired")
        self.assertNotIn("hostSession", rec)
        self.assertEqual(coordinator.up(self.repo, None, "再升级", session_id="sid-9")[0], 0)

    def test_down_needs_words_and_own_session(self):
        self.assertEqual(coordinator.up(self.repo, "shop", "升级", session_id="sid-1")[0], 0)
        self.assertEqual(coordinator.down(self.repo, "", session_id="sid-1")[0], 3)
        self.assertEqual(coordinator.down(self.repo, "关掉", session_id="sid-2")[0], 3)

    def test_cli(self):
        words = self.tmp / "w.txt"
        words.write_text("升级为协调会话", encoding="utf-8")
        env = dict(os.environ, CLAUDE_CODE_SESSION_ID="sid-cli")
        out = self.run_cli("coordinator", "up", "--short", "shop", "--original-file", str(words), env=env)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("shop-coord", out.stdout)
        again = self.run_cli("coordinator", "up", "--original-file", str(words), env=dict(env, CLAUDE_CODE_SESSION_ID="x"))
        self.assertEqual(again.returncode, 3)
        down = self.run_cli("coordinator", "down", "--original-file", str(words), env=env)
        self.assertEqual(down.returncode, 0, down.stdout + down.stderr)


if __name__ == "__main__":
    unittest.main()
