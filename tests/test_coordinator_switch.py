"""crew-coordinator-switch: per-session coordinator switch (see spec/crew-coordinator-switch.md)."""

from __future__ import annotations

import json
import os
import unittest

from helpers import ProbeCase, ReviewCase, StartCase, git, make_worktree, spec_guard_interface

from module_crew import coordinator, hooks, probe, start, store


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


def run(event, cwd, sid=None, **extra):
    payload = {"cwd": str(cwd), **({"session_id": sid} if sid else {}), **extra}
    out = hooks.run_hook(event, json.dumps(payload))
    return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""


class QuietTest(ReviewCase):
    """Acceptance 5: no coordinator registration in use -> nothing, anywhere."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        self.elsewhere = make_worktree(self.repo, "side")
        with self.db.transaction(actor="t") as tx:
            tx.put("session", "shop-coord", {**tx.get("session", "shop-coord"), "status": "retired"}, action="retired")

    def test_silent_everywhere(self):
        for cwd in (self.repo, self.wt["b"], self.elsewhere):
            for event in ("session-start", "prompt", "session-end"):
                self.assertEqual(run(event, cwd, "sid-x"), "", (cwd, event))

    def test_silent_without_store(self):
        os_repo = self.tmp / "plain"
        os_repo.mkdir()
        git(os_repo, "init", "-q")
        self.assertEqual(run("session-start", os_repo, "sid-x"), "")


class SightingTest(ReviewCase):
    """Acceptance 6, 7, 9."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")
        self.elsewhere = make_worktree(self.repo, "side")

    def test_reminded_once(self):
        text = run("session-start", self.elsewhere, "sid-s1")
        self.assertIn("这个项目已有模块协调（在 " + str(self.repo) + "，分支 main）", text)
        self.assertIn("第一次回复用户时顺带说一次", text)
        self.assertNotIn("takeover", text)                          # not in the integration checkout
        rec = store.get(self.db, "sighting", "sid-s1")
        self.assertEqual((rec["cwd"], rec["branch"], rec["told"]), (str(self.elsewhere.resolve()), "side", False))
        for source in ("resume", "compact", "startup"):
            self.assertEqual(run("session-start", self.elsewhere, "sid-s1", source=source), "")
        self.assertEqual(run("prompt", self.elsewhere, "sid-s1"), "")

    def test_module_worktree_keeps_bind_hint(self):
        text = run("session-start", self.wt["b"], "sid-new")
        self.assertIn("本目录属于模块 b", text)
        self.assertIsNone(store.get(self.db, "sighting", "sid-new"))

    def test_registered_session_elsewhere_hears_nothing(self):
        self.assertEqual(run("session-start", self.elsewhere, "sid-coord"), "")

    def test_coordinator_told_once(self):
        run("session-start", self.elsewhere, "sid-s1")
        line = run("prompt", self.repo, "sid-coord")
        self.assertIn("有 1 个没登记的会话在本项目活动：" + str(self.elsewhere.resolve()) + "（分支 side）", line)
        self.assertTrue(store.get(self.db, "sighting", "sid-s1")["told"])
        self.assertNotIn("没登记的会话", run("prompt", self.repo, "sid-coord"))

    def test_unbound_coordinator_only_bind_hint(self):
        hooks.takeover(self.db, "shop-coord", "换个会话")
        self.assertIn("--original-file", run("session-start", self.repo, "sid-z"))
        self.assertEqual(run("session-start", self.elsewhere, "sid-z2"), "")

    def test_busy_store_is_silent(self):
        import fcntl
        fd = os.open(self.db.path / ".lock", os.O_RDWR)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        old = hooks.HOOK_WAIT
        hooks.HOOK_WAIT = 0.2
        self.addCleanup(setattr, hooks, "HOOK_WAIT", old)
        self.assertEqual(run("session-start", self.elsewhere, "sid-busy"), "")
        fcntl.flock(fd, fcntl.LOCK_UN)
        self.assertIsNone(store.get(self.db, "sighting", "sid-busy"))


class ClearHandoverTest(ReviewCase):
    """Acceptance 8, in the order measured on 2026-10-22: SessionEnd(old, clear) then SessionStart(new, clear)."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        hooks.bind(self.db, "shop-coord", "sid-old", self.repo, original="你来做模块协调")
        hooks.bind(self.db, "shop-b", "sid-b-old", self.wt["b"])

    def bound(self, name):
        return store.get(self.db, "session", name)["hostSession"]["sessionId"]

    def test_coordinator_rebound(self):
        self.assertEqual(run("session-end", self.repo, "sid-old", reason="clear"), "")
        text = run("session-start", self.repo, "sid-new", source="clear")
        self.assertIn("本会话是模块协调", text)
        self.assertIn("刚清空过", text)
        self.assertEqual(self.bound("shop-coord"), "sid-new")
        ev = store.events(self.db, key="shop-coord", kind="session")[-1]
        self.assertEqual((ev["type"], ev["data"]["oldSessionId"]), ("session.rebound-after-clear", "sid-old"))

    def test_module_rebound(self):
        run("session-end", self.wt["b"], "sid-b-old", reason="clear")
        self.assertIn("你是模块 b 的模块会话", run("session-start", self.wt["b"], "sid-b-new", source="clear"))
        self.assertEqual(self.bound("shop-b"), "sid-b-new")

    def test_not_rebound(self):
        run("session-end", self.repo, "sid-old", reason="other")            # not a clear
        run("session-start", self.repo, "sid-n1", source="clear")
        self.assertEqual(self.bound("shop-coord"), "sid-old")
        run("session-end", self.repo, "sid-old", reason="clear")
        run("session-start", self.wt["b"], "sid-n2", source="clear")         # another directory
        run("session-start", self.repo, "sid-n3", source="startup")          # not a clear start
        self.assertEqual(self.bound("shop-coord"), "sid-old")

    def test_window(self):
        import time
        hooks.end_session(self.db, "sid-old", str(self.repo), "clear")
        self.assertIsNone(hooks.rebind(self.db, "sid-late", str(self.repo), "clear", now=time.time() + 31))
        self.assertEqual(self.bound("shop-coord"), "sid-old")
        self.assertIsNone(hooks.rebind(self.db, "sid-later", str(self.repo), "clear", now=time.time() + 301))
        self.assertEqual(store.get(self.db, "handover", "shop-coord")["closedReason"], "expired")

    def test_hooks_json_has_session_end(self):
        from helpers import PLUGIN_ROOT
        doc = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertIn("hook session-end", doc["hooks"]["SessionEnd"][0]["hooks"][0]["command"])


class StatusTest(ReviewCase):
    """Acceptance 11."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")
        self.elsewhere = make_worktree(self.repo, "side")
        run("session-start", self.elsewhere, "sid-s1")

    def test_text(self):
        out = self.run_cli("status").stdout
        self.assertIn(f"shop-coord：在 {self.repo}，分支 main；已绑定会话", out)
        self.assertIn("没登记的会话：1 个", out)
        self.assertIn(f"{self.elsewhere.resolve()}（分支 side）", out)
        self.assertIn("还没告诉用户", out)

    def test_json(self):
        doc = json.loads(self.run_cli("status", "--json").stdout)
        coord = doc["store"]["coordinator"]
        self.assertEqual((coord["name"], coord["state"], coord["bound"], coord["branch"]), ("shop-coord", "active", True, "main"))
        self.assertEqual(doc["store"]["sightings"]["count"], 1)

    def test_retired(self):
        devs = [n for n, s in store.records(self.db, "session").items() if s["role"] == "dev"]
        with self.db.transaction(actor="t") as tx:
            for n in devs:
                tx.put("session", n, {**tx.get("session", n), "status": "retired"}, action="retired")
        self.assertEqual(coordinator.down(self.repo, "关掉", session_id="sid-coord")[0], 0)
        self.assertIn("shop-coord：", self.run_cli("status").stdout)
        self.assertIn("已关闭", self.run_cli("status").stdout)


class DesktopHandoverTest(ReviewCase):
    """Acceptance 8 (2026-10-22 revision): the desktop app ends a cleared process with reason "other" and starts the
    next one with source "startup" on the next message; CLAUDE_CODE_HOST_SESSION_ID (local_…) stays the same."""

    DESKTOP = {"CLAUDE_CODE_ENTRYPOINT": "claude-desktop", "CLAUDE_CODE_HOST_SESSION_ID": "local_aaa"}

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        self.env(self.DESKTOP)
        hooks.bind(self.db, "shop-coord", "sid-old", self.repo, original="你来做模块协调")

    def env(self, values):
        for k, v in values.items():
            old = os.environ.get(k)
            self.addCleanup(lambda k=k, old=old: os.environ.__setitem__(k, old) if old is not None else os.environ.pop(k, None))
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def bound(self):
        return store.get(self.db, "session", "shop-coord")["hostSession"]

    def test_bind_records_desktop_id(self):
        self.assertEqual(self.bound()["desktopId"], "local_aaa")

    def test_cli_bind_has_no_desktop_id(self):
        self.env({"CLAUDE_CODE_ENTRYPOINT": "cli"})
        self.assertNotIn("desktopId", hooks.identity("sid-x"))

    def test_rebound_after_desktop_clear(self):
        run("session-end", self.repo, "sid-old", reason="other")
        text = run("session-start", self.repo, "sid-new", source="startup")
        self.assertIn("本会话是模块协调", text)
        self.assertIn("刚清空过", text)
        self.assertEqual((self.bound()["sessionId"], self.bound()["desktopId"]), ("sid-new", "local_aaa"))
        ev = store.events(self.db, key="shop-coord", kind="session")[-1]
        self.assertEqual(ev["data"]["via"], "desktop")
        self.assertIsNone(store.get(self.db, "sighting", "sid-new"))

    def test_other_desktop_session_not_rebound(self):
        run("session-end", self.repo, "sid-old", reason="other")
        self.env({"CLAUDE_CODE_HOST_SESSION_ID": "local_bbb"})
        self.assertIn("这个项目已有模块协调", run("session-start", self.repo, "sid-other"))
        self.assertEqual(self.bound()["sessionId"], "sid-old")

    def test_not_before_the_old_process_ends(self):
        # a CLI child of the live session inherits local_aaa; with no SessionEnd there is no handover to take
        self.assertNotIn("本会话是模块协调", run("session-start", self.repo, "sid-child"))
        self.assertEqual(self.bound()["sessionId"], "sid-old")

    def test_other_directory_not_rebound(self):
        run("session-end", self.repo, "sid-old", reason="other")
        run("session-start", self.wt["b"], "sid-new")
        self.assertEqual(self.bound()["sessionId"], "sid-old")

    def test_old_session_coming_back_closes_handover(self):
        run("session-end", self.repo, "sid-old", reason="other")
        self.assertIn("本会话是模块协调", run("session-start", self.repo, "sid-old", source="resume"))
        self.assertEqual(store.get(self.db, "handover", "shop-coord")["closedReason"], "resumed")
        self.assertEqual(self.bound()["sessionId"], "sid-old")

    def test_expires_after_seven_days(self):
        import time
        hooks.end_session(self.db, "sid-old", str(self.repo), "other")
        self.assertIsNone(hooks.rebind(self.db, "sid-new", str(self.repo), "startup", now=time.time() + 8 * 86400,
                                       host_id="local_aaa"))
        self.assertEqual(store.get(self.db, "handover", "shop-coord")["closedReason"], "expired")

    def test_cli_binding_other_end_leaves_nothing(self):
        self.env({"CLAUDE_CODE_ENTRYPOINT": "cli"})
        hooks.takeover(self.db, "shop-coord", "换")
        hooks.bind(self.db, "shop-coord", "sid-cli", self.repo, original="你来做")
        run("session-end", self.repo, "sid-cli", reason="other")
        self.assertEqual(store.records(self.db, "handover"), {})


if __name__ == "__main__":
    unittest.main()
