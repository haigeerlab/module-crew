"""crew-check-ledger: quick and full checks kept apart, results recorded per tree (see spec/crew-check-ledger.md)."""
import unittest

from helpers import MergeCase, git

from module_crew import checks, merge, store


class LedgerCase(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def cfg(self) -> dict:
        return store.get(self.db, "config", "main") or {}

    def config_set(self, *args, original="打开检查记账"):
        return self.run_cli("config", "set", *args, "--original", original, cwd=self.repo)

    def counting_script(self, name: str, fail_if: str | None = None) -> str:
        """A check command that appends a line to <tmp>/<name>.calls each time it runs; fails when `fail_if` exists."""
        calls = self.tmp / f"{name}.calls"
        script = self.tmp / f"{name}.py"
        script.write_text(
            "import os, sys\n"
            f"open({str(calls)!r}, 'a').write('x\\n')\n"
            "print('FAIL: test_value' if " + f"{fail_if!r} and os.path.exists({fail_if!r})" + " else 'ok')\n"
            f"sys.exit(1 if {fail_if!r} and os.path.exists({fail_if!r}) else 0)\n", encoding="utf-8")
        return f"python3 {script}"

    def calls(self, name: str) -> int:
        f = self.tmp / f"{name}.calls"
        return len(f.read_text().splitlines()) if f.exists() else 0

    def switch_on(self, quick: str | None = None, full: str | None = None) -> None:
        quick = quick or self.counting_script("quick")
        full = full or self.counting_script("full")
        from module_crew import merge
        merge._write_config(self.db, {**self.cfg(), "checkCommand": full})
        out = self.config_set("--quick-check-command", quick)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        out = self.config_set("--check-ledger", "on")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


class ConfigTest(LedgerCase):
    """Task 1 (Spec AC 2): the switch and the quick-check command need the user's words and both commands."""

    def test_switch_needs_both_commands(self):
        out = self.config_set("--check-ledger", "on")
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn("quickCheckCommand", out.stdout + out.stderr)
        self.assertNotIn("checkLedger", self.cfg())
        self.assertEqual(self.config_set("--quick-check-command", "python3 -c pass").returncode, 0)
        out = self.config_set("--check-ledger", "on")
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn("checkCommand", out.stdout + out.stderr)
        self.assertNotIn("checkLedger", self.cfg())
        self.assertFalse(checks.enabled(self.cfg()))

    def test_switch_on_and_off(self):
        self.switch_on()
        self.assertEqual(self.cfg()["checkLedger"], "on")
        self.assertTrue(checks.enabled(self.cfg()))
        out = self.config_set("--check-ledger", "off", original="关掉检查记账")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(self.cfg()["checkLedger"], "off")
        self.assertFalse(checks.enabled(self.cfg()))

    def test_quick_command_operators_refused(self):
        for command in ("pnpm lint && pnpm test", "make test | tee out", "make test;"):
            with self.subTest(command=command):
                out = self.config_set("--quick-check-command", command)
                self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
                self.assertIn("shell 运算符", out.stdout + out.stderr)
                self.assertNotIn("quickCheckCommand", self.cfg())
        self.assertEqual(self.config_set("--quick-check-command", "/bin/sh -c 'a && b'").returncode, 0)

    def test_needs_original(self):
        out = self.config_set("--quick-check-command", "python3 -c pass", original="  ")
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertNotIn("quickCheckCommand", self.cfg())
        out = self.run_cli("config", "set", "--check-ledger", "on", cwd=self.repo)
        self.assertNotEqual(out.returncode, 0)

    def test_original_recorded(self):
        self.switch_on()
        ev = [e for e in store.events(self.db, kind="config") if "checkLedger" in (e["data"] or {})]
        self.assertEqual(ev[-1]["data"]["original"], "打开检查记账")


class LedgerRecordTest(LedgerCase):
    """Task 1: one record per <tree>.<kind>; a different command does not count."""

    def test_record_and_lookup(self):
        tree = git(self.repo, "rev-parse", "HEAD^{tree}").strip()
        self.assertIsNone(checks.lookup(self.db, tree, "quick", "python3 a.py"))
        checks.record(self.db, {"tree": tree, "kind": "quick", "command": "python3 a.py", "result": "pass",
                                "exitCode": 0, "tail": "ok", "commit": None, "where": str(self.repo), "by": "shop-b",
                                "startedAt": store.now(), "seconds": 1, "inheritedFrom": None})
        got = checks.lookup(self.db, tree, "quick", "python3 a.py")
        self.assertEqual(got["result"], "pass")
        self.assertIsNone(checks.lookup(self.db, tree, "quick", "python3 b.py"))
        self.assertIsNone(checks.lookup(self.db, tree, "full", "python3 a.py"))
        self.assertIsNotNone(store.get(self.db, "check", f"{tree}.quick"))


class QuickTest(LedgerCase):
    """Task 2 (Spec AC 3, 4, 12): check quick records once per tree, refuses a dirty tree, never records a timeout."""

    def quick(self, *args, m="b"):
        return self.run_cli("check", "quick", *args, cwd=self.wt[m])

    def tree(self, m="b"):
        return git(self.wt[m], "rev-parse", "HEAD^{tree}").strip()

    def test_off_refused(self):
        out = self.quick()
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn("checkLedger", out.stdout + out.stderr)
        self.assertEqual(store.records(self.db, "check"), {})

    def test_records_once_per_tree(self):
        self.switch_on()
        out = self.quick()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(self.calls("quick"), 1)
        rec = store.get(self.db, "check", f"{self.tree()}.quick")
        self.assertEqual((rec["result"], rec["by"], rec["kind"]), ("pass", "shop-b", "quick"))
        self.assertEqual(rec["command"], self.cfg()["quickCheckCommand"])
        self.assertEqual(rec["commit"], git(self.wt["b"], "rev-parse", "HEAD").strip())
        out = self.quick()
        self.assertEqual(out.returncode, 0)
        self.assertIn("不重跑", out.stdout)
        self.assertEqual(self.calls("quick"), 1)
        self.assertEqual(self.quick("--rerun").returncode, 0)
        self.assertEqual(self.calls("quick"), 2)

    def test_new_command_runs_again(self):
        self.switch_on()
        self.quick()
        other = self.counting_script("quick2")
        self.assertEqual(self.config_set("--quick-check-command", other).returncode, 0)
        self.assertEqual(self.quick().returncode, 0)
        self.assertEqual(self.calls("quick2"), 1)

    def test_full_pass_covers_quick(self):
        self.switch_on()
        checks.record(self.db, {"tree": self.tree(), "kind": "full", "command": self.cfg()["checkCommand"],
                                "result": "pass", "exitCode": 0, "tail": "", "commit": None, "where": "x",
                                "by": "merge-run", "startedAt": store.now(), "seconds": 1, "inheritedFrom": None})
        out = self.quick()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(self.calls("quick"), 0)

    def test_dirty_refused(self):
        self.switch_on()
        (self.wt["b"] / "spec" / "b.md").write_text("changed\n", encoding="utf-8")
        out = self.quick()
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        git(self.wt["b"], "checkout", "--", "spec/b.md")
        (self.wt["b"] / "new.txt").write_text("x", encoding="utf-8")
        self.assertEqual(self.quick().returncode, 3)
        self.assertEqual(self.calls("quick"), 0)
        self.assertEqual(store.records(self.db, "check"), {})

    def test_fail_recorded(self):
        flag = self.wt["b"] / "broken"
        self.switch_on(quick=self.counting_script("quick", fail_if=str(flag)))
        flag.write_text("", encoding="utf-8")
        git(self.wt["b"], "add", "-A")
        git(self.wt["b"], "commit", "-q", "-m", "b: broken")
        out = self.quick()
        self.assertEqual(out.returncode, 5, out.stdout + out.stderr)
        self.assertIn("FAIL: test_value", out.stdout)
        self.assertEqual(store.get(self.db, "check", f"{self.tree()}.quick")["result"], "fail")
        self.assertEqual(self.quick().returncode, 5)
        self.assertEqual(self.calls("quick"), 1)

    def test_cannot_run_or_timeout_not_recorded(self):
        self.switch_on(quick="/nonexistent/check-affected")
        out = self.quick()
        self.assertEqual(out.returncode, 4, out.stdout + out.stderr)
        sleeper = self.tmp / "sleep.py"
        sleeper.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
        self.assertEqual(self.config_set("--quick-check-command", f"python3 {sleeper}").returncode, 0)
        from module_crew import merge
        merge._write_config(self.db, {**self.cfg(), "checkTimeout": 1})
        out = self.quick()
        self.assertEqual(out.returncode, 4, out.stdout + out.stderr)
        self.assertIn("超时", out.stderr)
        self.assertEqual(store.records(self.db, "check"), {})

    def test_coordinator_checkout_refused(self):
        self.switch_on()
        out = self.run_cli("check", "quick", cwd=self.repo)
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)

    def test_show_and_list(self):
        self.switch_on()
        self.quick()
        out = self.run_cli("check", "show", "--json", cwd=self.wt["b"])
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        import json
        rows = json.loads(out.stdout)["checks"]
        self.assertEqual([r["kind"] for r in rows], ["quick"])
        out = self.run_cli("check", "list", "--json", cwd=self.repo)
        self.assertEqual(len(json.loads(out.stdout)["checks"]), 1)
        out = self.run_cli("check", "show", cwd=self.wt["c"])
        self.assertEqual(out.returncode, 0)
        self.assertIn("没有检查记录", out.stdout)


class MergeLedgerTest(LedgerCase):
    """Task 3 (Spec AC 5): merge run always runs the full check; with the switch on the result is recorded and the
    tick commit's tree inherits it."""

    def todo(self, m):
        path = self.wt[m] / "tasks" / m / "todo.md"
        path.write_text(f"# Todo: {m}\n\n- [x] Task 1\n- [ ] 最终验收（gate）\n", encoding="utf-8")

    def test_recorded_and_inherited(self):
        self.switch_on()
        self.todo("b")
        self.approve_final("b", 1)
        res = merge.run(self.repo)
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(self.calls("full"), 1)
        merged_tree = git(self.repo, "rev-parse", f"{res.merge_commit}^{{tree}}").strip()
        rec = store.get(self.db, "check", f"{merged_tree}.full")
        self.assertEqual((rec["result"], rec["by"], rec["commit"]), ("pass", "merge-run", res.merge_commit))
        head = git(self.repo, "rev-parse", "HEAD").strip()
        self.assertNotEqual(head, res.merge_commit)            # the tick commit
        top = store.get(self.db, "check", f"{git(self.repo, 'rev-parse', 'HEAD^{tree}').strip()}.full")
        self.assertEqual((top["result"], top["inheritedFrom"], top["commit"]), ("pass", merged_tree, head))

    def test_full_check_runs_even_when_recorded(self):
        self.switch_on()
        self.approve_final("b", 1)
        merge.run(self.repo)
        self.approve_final("c", 2)
        merge.run(self.repo)
        self.assertEqual(self.calls("full"), 2)

    def test_failure_recorded(self):
        self.switch_on(full=self.counting_script("full", fail_if="fail.flag"))
        self.approve_final("b", 1, path="fail.flag", content="")
        res = merge.run(self.repo)
        self.assertEqual(res.code, 5, res.lines)
        merged_tree = git(self.repo, "rev-parse", f"{res.merge_commit}^{{tree}}").strip()
        self.assertEqual(store.get(self.db, "check", f"{merged_tree}.full")["result"], "fail")

    def test_other_changes_not_inherited(self):
        self.switch_on()
        self.approve_final("b", 1)
        res = merge.run(self.repo)
        (self.repo / "other.txt").write_text("x\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "other")
        self.assertIsNone(checks.inherit(self.db, self.cfg(), self.repo, res.merge_commit, "b"))
        top = git(self.repo, "rev-parse", "HEAD^{tree}").strip()
        self.assertIsNone(store.get(self.db, "check", f"{top}.full"))

    def test_off_nothing_recorded(self):
        self.approve_final("b", 1)
        self.assertEqual(merge.run(self.repo, check_command=self.counting_script("full")).code, 0)
        self.assertEqual(self.calls("full"), 1)
        self.assertEqual(store.records(self.db, "check"), {})


class WordingTest(LedgerCase):
    """Task 4 (Spec AC 6, 1): every "sync, then check" sentence follows the switch."""

    QUICK = "跑 `module-crew check quick`（快检查）"

    def setUp(self):
        super().setUp()
        from module_crew import hooks
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")

    def texts(self) -> dict[str, str]:
        from module_crew import changes, failure, hooks, protocol, tasks, unqueued
        from test_changes import request
        out = {}
        failure.suspend(self.db, "c", "等设计稿", "先挂起 c")
        self.approve_final("b", 1)
        res = merge.run(self.repo, check_command=None if self.cfg().get("checkCommand") else "python3 -c pass")
        n = tasks.add(self.db, self.repo, "feature", "改文档", "补说明", ["docs/x.md"], "写好", "加说明").number
        d = tasks.dispatch(self.db, self.repo, n)
        out["kickoff"] = store.read_body(self.db, d.kickoff)
        hooks.bind(self.db, d.relay, "sid-t", d.worktree)
        out["resume"] = protocol.parse(store.read_body(self.db, failure.resume(self.db, "c", "恢复 c").sends[0]["body"])).fields["要你做什么"]
        r = changes.add(self.db, request(["a.json"]), "shop-c", 5003).number
        (self.repo / "a.json").write_text("{}\n", encoding="utf-8")
        land = changes.land(self.repo, r)
        self.assertEqual(land.code, 0, land.lines)
        out["land"] = protocol.parse(store.read_body(self.db, land.sends[0]["body"])).fields["要你做什么"]
        (self.repo / "manual.txt").write_text("x\n", encoding="utf-8")
        git(self.repo, "add", "manual.txt")
        git(self.repo, "commit", "-q", "-m", "手动提交")
        sends = unqueued.notify(self.db, self.repo)
        self.assertTrue(sends)
        for x in sends:
            self.assertTrue(protocol.parse(store.read_body(self.db, x["body"])).ok)
        out["unqueued"] = protocol.parse(store.read_body(self.db, sends[0]["body"])).fields["要你做什么"]
        sync = self.run_cli("sync", cwd=self.wt["c"])
        self.assertEqual(sync.returncode, 0, sync.stdout + sync.stderr)
        out["sync"] = sync.stdout
        self.approve_final("c", 2)
        res = merge.run(self.repo, check_command=None if self.cfg().get("checkCommand") else "python3 -c pass")
        self.assertEqual(res.code, 0, res.lines)
        [note] = [x for x in res.sends if x["kind"] == "sync-baseline"]
        msg = protocol.parse(store.read_body(self.db, note["body"]))
        self.assertTrue(msg.ok, msg.problems)
        out["merge"] = msg.fields["要你做什么"]
        return out

    def test_switch_on(self):
        self.switch_on()
        for name, text in self.texts().items():
            with self.subTest(name=name):
                self.assertIn("module-crew check quick", text)
                self.assertNotIn("跑完整检查", text)

    def test_switch_off_unchanged(self):
        for name, text in self.texts().items():
            with self.subTest(name=name):
                self.assertIn("完整检查", text)
                self.assertNotIn("check quick", text)


if __name__ == "__main__":
    unittest.main()
