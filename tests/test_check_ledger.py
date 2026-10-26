"""crew-check-ledger: quick and full checks kept apart, results recorded per tree (see spec/crew-check-ledger.md)."""
import unittest

from helpers import PLUGIN_ROOT, MergeCase, git

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


class BaselineTest(LedgerCase):
    """Task 5 (Spec AC 7, 8, 9): one full check per baseline tree, the merge lock both ways, one fix task per red run."""

    def setUp(self):
        super().setUp()
        from module_crew import hooks
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")

    def baseline(self, *args):
        return self.run_cli("check", "baseline", *args, cwd=self.repo)

    def commit_main(self, *names):
        for name in names:
            (self.repo / name).write_text(f"{name}\n", encoding="utf-8")
        git(self.repo, "add", *names)
        git(self.repo, "commit", "-q", "-m", f"手动提交 {' '.join(names)}")
        return git(self.repo, "rev-parse", "HEAD").strip()

    def fix_tasks(self):
        return {k: t for k, t in store.records(self.db, "task").items() if t.get("baseline")}

    def red_switch(self):
        self.switch_on(quick=self.counting_script("quick", fail_if="fail.flag"),
                       full=self.counting_script("full", fail_if="fail.flag"))

    def test_off_and_not_coordinator(self):
        self.assertEqual(self.baseline().returncode, 3)
        self.switch_on()
        out = self.run_cli("check", "baseline", cwd=self.wt["b"])
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertEqual(self.calls("full"), 0)

    def test_records_once(self):
        self.switch_on()
        out = self.baseline()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        tree = git(self.repo, "rev-parse", "HEAD^{tree}").strip()
        rec = store.get(self.db, "check", f"{tree}.full")
        self.assertEqual((rec["result"], rec["by"]), ("pass", "baseline"))
        self.assertEqual(self.baseline().returncode, 0)
        self.assertEqual(self.calls("full"), 1)
        self.assertEqual(self.baseline("--rerun").returncode, 0)
        self.assertEqual(self.calls("full"), 2)

    def test_merge_lock_held(self):
        from module_crew import mergelock
        self.switch_on()
        lock = mergelock.acquire(self.db, 99, "b")
        try:
            out = self.baseline()
            self.assertEqual(out.returncode, 6, out.stdout + out.stderr)
            self.assertIn("合并 C99", out.stdout + out.stderr)
        finally:
            mergelock.release(self.db, lock)
        self.assertEqual(self.calls("full"), 0)

    def test_merge_refused_while_baseline_runs(self):
        import subprocess, time
        from module_crew import mergelock
        slow = self.tmp / "slow.py"
        slow.write_text("import time\ntime.sleep(4)\n", encoding="utf-8")
        self.switch_on(full=f"python3 {slow}")
        self.approve_final("b", 1)
        child = subprocess.Popen([str(PLUGIN_ROOT / "bin" / "module-crew"), "check", "baseline"], cwd=self.repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            for _ in range(100):
                if mergelock.read(self.db):
                    break
                time.sleep(0.05)
            self.assertIn("基线检查", mergelock.describe(mergelock.read(self.db)))
            res = merge.run(self.repo)
            self.assertEqual(res.code, 6, res.lines)
            self.assertIn("基线检查", res.lines[0])
        finally:
            out, err = child.communicate(timeout=60)
        self.assertEqual(child.returncode, 0, out + err)
        self.assertEqual(merge.run(self.repo).code, 0)

    def test_red_baseline_makes_one_fix_task(self):
        self.red_switch()
        green = git(self.repo, "rev-parse", "HEAD").strip()
        self.assertEqual(self.baseline().returncode, 0)
        red = self.commit_main("fail.flag", "other.txt")
        out = self.baseline()
        self.assertEqual(out.returncode, 5, out.stdout + out.stderr)
        [(n, t)] = self.fix_tasks().items()
        self.assertIn(f"T{n}", out.stdout)
        self.assertEqual(t["type"], "bug")
        self.assertIn("修基线", t["title"])
        self.assertIn("FAIL: test_value", t["what"])
        self.assertEqual(sorted(t["expectedFiles"]), ["fail.flag", "other.txt"])
        self.assertEqual(t["baseline"], {"tree": git(self.repo, "rev-parse", "HEAD^{tree}").strip(), "commit": red})
        self.assertIn("checkLedger", t["original"])
        self.assertIn("打开检查记账", t["original"])
        self.assertNotEqual(green, red)
        again = self.baseline()                       # the old record: no rerun, no second task
        self.assertEqual(again.returncode, 5)
        self.assertIn(f"T{n}", again.stdout)
        self.commit_main("more.txt")                   # a new red tree while the fix task is still open
        third = self.baseline()
        self.assertEqual(third.returncode, 5)
        self.assertIn(f"T{n}", third.stdout)
        self.assertEqual(len(self.fix_tasks()), 1)
        self.assertEqual(self.calls("full"), 3)

    def test_no_green_baseline_no_task(self):
        self.red_switch()
        self.commit_main("fail.flag")
        out = self.baseline()
        self.assertEqual(out.returncode, 5, out.stdout + out.stderr)
        self.assertIn("没有可比的绿基线", out.stdout)
        self.assertEqual(self.fix_tasks(), {})

    def test_quick_failure_mentions_red_baseline(self):
        self.red_switch()
        self.baseline()
        self.commit_main("fail.flag")
        self.baseline()
        [n] = self.fix_tasks()
        f = self.wt["b"] / "fail.flag"
        f.write_text("", encoding="utf-8")
        git(self.wt["b"], "add", "-A")
        git(self.wt["b"], "commit", "-q", "-m", "b: red")
        out = self.run_cli("check", "quick", cwd=self.wt["b"])
        self.assertEqual(out.returncode, 5, out.stdout + out.stderr)
        self.assertIn(f"修基线任务 T{n}", out.stdout)


class LandTest(LedgerCase):
    """Task 6 (Spec AC 10): change land runs the quick check on the staged tree before it commits."""

    def setUp(self):
        super().setUp()
        from module_crew import changes
        from test_changes import request
        self.changes = changes
        self.n = changes.add(self.db, request(["a.json"]), "shop-b", 5003).number
        self.head = git(self.repo, "rev-parse", "HEAD").strip()

    def edit(self, text="{}\n"):
        (self.repo / "a.json").write_text(text, encoding="utf-8")

    def test_pass_commits_and_records(self):
        self.switch_on()
        self.edit()
        tree = None
        res = self.changes.land(self.repo, self.n)
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(self.calls("quick"), 1)
        tree = git(self.repo, "rev-parse", "HEAD^{tree}").strip()
        rec = store.get(self.db, "check", f"{tree}.quick")
        self.assertEqual((rec["result"], rec["by"], rec["commit"]), ("pass", "change-land", None))

    def test_fail_keeps_staged(self):
        self.switch_on(quick=self.counting_script("quick", fail_if="a.json"))
        self.edit()
        res = self.changes.land(self.repo, self.n)
        self.assertEqual(res.code, 5, res.lines)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), self.head)
        self.assertIn("A  a.json", git(self.repo, "status", "--porcelain"))
        self.assertEqual(store.get(self.db, "request", str(self.n))["state"], "open")
        self.assertEqual(res.sends, [])

    def test_skip_needs_words(self):
        self.switch_on(quick=self.counting_script("quick", fail_if="a.json"))
        self.edit()
        res = self.changes.land(self.repo, self.n, skip_quick=True)
        self.assertEqual(res.code, 3, res.lines)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), self.head)
        res = self.changes.land(self.repo, self.n, "这次先落地，快检查的问题另修", skip_quick=True)
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(self.calls("quick"), 0)
        rec = store.get(self.db, "request", str(self.n))
        self.assertEqual(rec["quickCheckSkipped"]["original"], "这次先落地，快检查的问题另修")

    def test_cli_flag(self):
        self.switch_on()
        self.edit()
        out = self.run_cli("change", "land", f"C{self.n}", "--skip-quick-check", cwd=self.repo)
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)

    def test_off_unchanged(self):
        self.edit()
        self.assertEqual(self.changes.land(self.repo, self.n).code, 0)
        self.assertEqual(store.records(self.db, "check"), {})


class FinalReviewTest(LedgerCase):
    """Task 7 (Spec AC 11): a final acceptance carries the ledger entries of its tree; a missing one only warns."""

    def setUp(self):
        super().setUp()
        from module_crew import hooks
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")

    def test_module_final_with_quick(self):
        from module_crew import review
        self.switch_on()
        text = self.finish("b")
        self.assertEqual(self.run_cli("check", "quick", cwd=self.wt["b"]).returncode, 0)
        out = review.add(self.db, text, "shop-b", 801)
        self.assertEqual(out.code, 0, out.lines)
        rec = store.get(self.db, "item", str(out.number))
        tree = git(self.wt["b"], "rev-parse", "HEAD^{tree}").strip()
        self.assertEqual((rec["checks"]["tree"], rec["checks"]["quick"]["result"]), (tree, "pass"))
        self.assertIsNone(rec["checks"]["full"])
        shown = "\n".join(review.show(self.db, out.number))
        self.assertIn("检查账：快检查 通过", shown)
        batch = self.run_cli("review", "batch", cwd=self.repo)
        self.assertIn("检查账：快检查 通过", batch.stdout)

    def test_missing_only_warns(self):
        from module_crew import review
        self.switch_on()
        out = review.add(self.db, self.finish("b"), "shop-b", 802)
        self.assertEqual(out.code, 0, out.lines)
        self.assertTrue(any("没跑过快检查" in line for line in out.lines), out.lines)
        self.assertIn("没跑过快检查", "\n".join(review.show(self.db, out.number)))

    def test_light_task_final(self):
        from module_crew import hooks, review, tasks
        from test_light_task import hand_back
        self.switch_on()
        n = tasks.add(self.db, self.repo, "feature", "改文档", "补一段说明", ["docs/t.md"], "说明写好", "加一段说明").number
        d = tasks.dispatch(self.db, self.repo, n)
        hooks.bind(self.db, d.relay, f"sid-t{n}", d.worktree)
        from pathlib import Path
        wt = Path(d.worktree)
        (wt / "docs").mkdir(exist_ok=True)
        (wt / "docs" / "t.md").write_text("x\n", encoding="utf-8")
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", f"T{n}")
        self.assertEqual(self.run_cli("check", "quick", cwd=wt).returncode, 0)
        out = review.add(self.db, hand_back(n, d.worktree, ["docs/t.md"]), d.relay, 803)
        self.assertEqual(out.code, 0, out.lines)
        self.assertEqual(store.get(self.db, "item", str(out.number))["checks"]["quick"]["result"], "pass")

    def test_off_no_checks(self):
        from module_crew import review
        out = review.add(self.db, self.finish("b"), "shop-b", 804)
        self.assertNotIn("checks", store.get(self.db, "item", str(out.number)))
        self.assertFalse(any("检查账" in line for line in out.lines))


if __name__ == "__main__":
    unittest.main()
