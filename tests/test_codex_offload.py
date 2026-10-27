"""crew-codex-offload: Codex runs a module's Tasks through delegate, the coordinator checks and commits for it
(see spec/crew-codex-offload.md)."""

import json
import os
import unittest
from pathlib import Path

from helpers import MergeCase, git

from module_crew import offload, store

DELEGATE_11 = {"interface": "1.1", "run": {
    "command": "/delegate:run", "backends": ["codex"], "write": "explicit",
    "resume": {"optIn": "--resumable", "option": "--resume", "backends": ["codex"], "statuses": ["done", "needs-input"]}}}
DELEGATE_12 = json.loads(json.dumps(DELEGATE_11))
DELEGATE_12["interface"] = "1.2"
DELEGATE_12["run"]["resume"]["statuses"].append("timeout")

SCOPE_COMMAND = ["python3", "-B", "hooks/module_scope.py", "check", "--project", "<project-root>", "--module", "<module-id>",
                 "--base", "<base-ref>", "--format", "json"]

# A fake spec-guard scopeCheck: changed files since --base, scoped by name (src/ and lib/ exclusive, the module's
# spec and tasks own, anything else outside). FAKE_SCOPE_CODE forces an exit code.
FAKE_SCOPE = '''import json, os, subprocess, sys
a = sys.argv[1:]
if a[0] == "declared":
    print(os.environ.get("FAKE_DECLARED_JSON", '{"declared": false}'))
    sys.exit(0)
if os.environ.get("FAKE_SCOPE_CODE"):
    sys.exit(int(os.environ["FAKE_SCOPE_CODE"]))
root, module, base = a[a.index("--project") + 1], a[a.index("--module") + 1], a[a.index("--base") + 1]
run = lambda *x: subprocess.run(["git", "-C", root] + list(x), capture_output=True, text=True).stdout
files = []
for line in run("diff", "--no-renames", "--name-status", base, "--").splitlines():
    st, path = line.split("\\t", 1)
    files.append((st, path))
files += [("?", p) for p in run("ls-files", "--others", "--exclude-standard").splitlines() if p]
out = []
for st, p in files:
    if p.startswith(("src/", "lib/")):
        scope = "exclusive"
    elif p == "spec/%s.md" % module or p.startswith("tasks/%s/" % module):
        scope = "own"
    else:
        scope = "outside"
    out.append({"path": p, "status": st, "scope": scope})
print(json.dumps({"module": module, "base": base, "files": out, "outside": sum(f["scope"] == "outside" for f in out)}))
'''


class OffloadCase(MergeCase):
    """Module b with an approved-looking Spec and Plan, quick check and ledger on, delegate 1.1, scopeCheck."""

    def setUp(self) -> None:
        super().setUp()
        self.delegate = self.plugins.install("delegate", DELEGATE_11)
        root = Path(self.plugins.entries["spec-guard@m"][-1]["installPath"])
        doc = json.loads((root / "interface.json").read_text())
        doc["interface"] = "1.11"
        doc["scopeCheck"] = {"command": SCOPE_COMMAND}
        (root / "interface.json").write_text(json.dumps(doc))
        (root / "hooks" / "module_scope.py").write_text(FAKE_SCOPE)
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in ("FAKE_SCOPE_CODE", "FAKE_DECLARED_JSON")])
        self.codex_home = self.tmp / "codex-home"
        self.codex_home.mkdir()
        old = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = str(self.codex_home)
        self.addCleanup(lambda: os.environ.__setitem__("CODEX_HOME", old) if old else os.environ.pop("CODEX_HOME", None))
        self.quick = self.tmp / "quick.py"
        self.quick_calls = self.tmp / "quick-calls"
        self.quick.write_text(
            "import os, sys\n"
            f"open({str(self.quick_calls)!r}, 'a').write('x')\n"
            "sys.exit(1 if os.path.exists('src/BROKEN.py') else 0)\n", encoding="utf-8")
        self.db = store.open_store(self.repo)
        with self.db.transaction(actor="test") as tx:
            cfg = dict(tx.get("config", "main") or {})
            cfg.update({"checkCommand": self.check_script(), "quickCheckCommand": f"python3 {self.quick}",
                        "checkLedger": "on"})
            tx.put("config", "main", cfg, action="set")

    def set_cfg(self, **kv):
        with self.db.transaction(actor="test") as tx:
            cfg = dict(tx.get("config", "main") or {})
            for k, v in kv.items():
                if v is None:
                    cfg.pop(k, None)
                else:
                    cfg[k] = v
            tx.put("config", "main", cfg, action="set")

    def switch_on(self):
        self.set_cfg(codexOffload="on")

    def quick_count(self) -> int:
        return len(self.quick_calls.read_text()) if self.quick_calls.exists() else 0

    def approve_b(self, todo: str | None = None) -> int:
        """Approve b's Spec and Plan in the integration checkout, then sync b so its branch has the approval."""
        from module_crew import review, sync
        wt = self.wt["b"]
        if todo is not None:
            (wt / "tasks" / "b" / "todo.md").write_text(todo, encoding="utf-8")
            git(wt, "add", "-A")
            git(wt, "commit", "-q", "-m", "b: todo")
        s = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        p = review.add(self.db, self.plan_review("b"), "shop-b", 2).number
        res = review.approve(self.repo, [s, p], "批准 b")
        assert res.code == 0, res.lines
        out = sync.run(wt)
        assert out.code == 0, out.lines
        self.db = store.open_store(self.repo)
        return res.approval

    def started(self, todo: str | None = None) -> offload.Outcome:
        self.switch_on()
        self.approve_b(todo)
        out = offload.start(self.repo, "b")
        assert out.code == 0, out.lines
        return out


class SwitchTest(OffloadCase):
    """Acceptance 1."""

    def test_on_with_words(self):
        out = self.run_cli("config", "set", "--codex-offload", "on", "--original", "打开额度外包")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("已打开额度外包", out.stdout)
        db = store.open_store(self.repo)
        self.assertEqual(store.get(db, "config", "main")["codexOffload"], "on")
        events = [json.loads(line) for line in (db.path / "events.jsonl").read_text().splitlines()]
        self.assertTrue(any((e.get("data") or {}).get("original") == "打开额度外包" and "codexOffload" in (e.get("data") or {})
                            for e in events))

    def test_refused_without_ledger(self):
        self.set_cfg(checkLedger=None)
        out = self.run_cli("config", "set", "--codex-offload", "on", "--original", "打开额度外包")
        self.assertEqual(out.returncode, 3)
        self.assertIn("checkLedger", out.stderr)
        self.assertNotIn("codexOffload", store.get(store.open_store(self.repo), "config", "main"))

    def test_empty_words_refused(self):
        out = self.run_cli("config", "set", "--codex-offload", "on", "--original", " ")
        self.assertEqual(out.returncode, 3)

    def test_warns_when_not_ready(self):
        (self.delegate / "interface.json").write_text(json.dumps({"interface": "1.0", "run": {"command": "/delegate:run"}}))
        out = self.run_cli("config", "set", "--codex-offload", "on", "--original", "打开额度外包")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("⚠️", out.stdout)
        self.assertIn("delegate", out.stdout)

    def test_off(self):
        self.switch_on()
        out = self.run_cli("config", "set", "--codex-offload", "off", "--original", "关掉额度外包")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertFalse(offload.enabled(store.open_store(self.repo)))


class ReadyTest(OffloadCase):
    """Acceptance 3: each of the six conditions."""

    def setUp(self) -> None:
        super().setUp()
        self.switch_on()

    def test_all_met(self):
        self.assertIsNone(offload.ready(self.db, self.repo))

    def test_switch_off(self):
        self.set_cfg(codexOffload=None)
        self.assertIn("codexOffload", offload.ready(self.db, self.repo))

    def test_ledger_off(self):
        self.set_cfg(checkLedger="off")
        self.assertIn("checkLedger", offload.ready(self.db, self.repo))

    def test_delegate_10(self):
        (self.delegate / "interface.json").write_text(json.dumps({"interface": "1.0", "run": {"command": "/delegate:run"}}))
        self.assertIn("1.1", offload.ready(self.db, self.repo))

    def test_delegate_without_resume(self):
        doc = json.loads(json.dumps(DELEGATE_11))
        del doc["run"]["resume"]
        (self.delegate / "interface.json").write_text(json.dumps(doc))
        self.assertIn("run.resume", offload.ready(self.db, self.repo))

    def test_delegate_missing(self):
        del self.plugins.entries["delegate@m"]
        self.plugins.write()
        self.assertIn("delegate", offload.ready(self.db, self.repo))

    def test_no_scope_check(self):
        root = Path(self.plugins.entries["spec-guard@m"][-1]["installPath"])
        doc = json.loads((root / "interface.json").read_text())
        del doc["scopeCheck"]
        (root / "interface.json").write_text(json.dumps(doc))
        self.assertIn("scopeCheck", offload.ready(self.db, self.repo))

    def test_concurrency_off(self):
        from helpers import START_MAP
        self.set_map({**START_MAP, "moduleConcurrency": "off"})
        self.assertIn("moduleConcurrency", offload.ready(self.db, self.repo))

    def test_coordinator_on_codex(self):
        with self.db.transaction(actor="test") as tx:
            for name, rec in store.records(self.db, "session").items():
                if rec.get("role") == "coordinator":
                    tx.put("session", name, {**rec, "host": "codex-desktop", "hostHandover": {
                        "from": "claude-desktop", "to": "codex-desktop", "at": "2026-10-26T00:00:00+08:00",
                        "original": "换到 Codex", "pending": False}}, action="set")
        self.assertIn("Codex", offload.ready(self.db, self.repo))

    def test_untrusted(self):
        (self.codex_home / "config.toml").write_text(f'[projects."{self.repo}"]\ntrust_level = "untrusted"\n')
        self.assertIn("untrusted", offload.ready(self.db, self.repo))

    def test_not_set_trust_is_fine(self):
        (self.codex_home / "config.toml").write_text("")
        self.assertIsNone(offload.ready(self.db, self.repo))

    def test_resume_timeout_flag(self):
        self.assertFalse(offload.delegate_interface(self.repo).resume_timeout)
        (self.delegate / "interface.json").write_text(json.dumps(DELEGATE_12))
        self.assertTrue(offload.delegate_interface(self.repo).resume_timeout)



TODO = "# Todo: b\n\n- [x] Task 1：打底\n- [ ] Task 2：做页面\n- [ ] Checkpoint 1（report）：页面就位\n- [ ] Checkpoint 2（gate）：最终验收\n"


class ParseTest(unittest.TestCase):
    """What delegate printed, sorted into done / needs-input / timeout / unknown (assumption 6)."""

    def test_done(self):
        r = offload.parse_result("做完了\ndelegate: run_id=r1 status=done resumable=true\n", 0)
        self.assertEqual((r.kind, r.run_id), ("done", "r1"))

    def test_needs_input(self):
        r = offload.parse_result("先做了 A\nNEED_USER: 用哪个库？\n选 x 还是 y\ndelegate: run_id=r2 status=needs-input resumable=true\n", 0)
        self.assertEqual((r.kind, r.run_id, r.question), ("needs-input", "r2", "用哪个库？\n选 x 还是 y"))

    def test_needs_input_without_marker_is_unknown(self):
        r = offload.parse_result("问题\ndelegate: run_id=r2 status=needs-input resumable=true\n", 0)
        self.assertEqual(r.kind, "unknown")

    def test_timeout_11(self):
        r = offload.parse_result("半截输出\n", 124)
        self.assertEqual((r.kind, r.run_id), ("timeout", None))

    def test_timeout_12(self):
        text = "进度：做完一半\ndelegate: run_id=r3 status=timeout resumable=true\n"
        self.assertEqual(offload.parse_result(text, 124).kind, "unknown")
        r = offload.parse_result(text, 124, resume_timeout=True)
        self.assertEqual((r.kind, r.run_id), ("timeout", "r3"))

    def test_unknown(self):
        for text, code in (("拒绝\n", 64), ("坏了\n", 1), ("没结果行\n", 0),
                           ("x\ndelegate: run_id=r4 status=weird resumable=true\n", 0),
                           ("x\ndelegate: run_id=r4 status=done resumable=true\n", 3)):
            self.assertEqual(offload.parse_result(text, code).kind, "unknown", (text, code))

    def test_next_item(self):
        self.assertEqual(offload.next_item(TODO)[:2], ("Task 2：做页面", True))
        self.assertEqual(offload.next_item(TODO.replace("- [ ] Task 2", "- [x] Task 2"))[:2],
                         ("Checkpoint 1（report）：页面就位", False))
        self.assertIsNone(offload.next_item("# Todo\n\n- [x] Task 1\n"))


class StartTest(OffloadCase):
    """Acceptance 5 and the start part of acceptance 2."""

    def test_off(self):
        self.approve_b(TODO)
        out = offload.start(self.repo, "b")
        self.assertEqual(out.code, 3)
        self.assertIn("codexOffload", "\n".join(out.lines))
        self.assertIsNone(store.get(self.db, "offload", "b"))

    def test_start_task(self):
        out = self.started(TODO)
        text = "\n".join(out.lines)
        self.assertIn("/delegate:run --write --resumable", text)
        self.assertIn(str(self.wt["b"]), text)
        self.assertIn("offload settle b", text)
        rec = store.get(store.open_store(self.repo), "offload", "b")
        self.assertEqual(rec["state"], "running")
        self.assertEqual(rec["task"], "Task 2：做页面")
        self.assertEqual(rec["base"], git(self.wt["b"], "rev-parse", "HEAD").strip())
        brief = Path(rec["runs"][-1]["brief"]).read_text(encoding="utf-8")
        for words in ("Task 2：做页面", "spec/b.md", "tasks/b/plan.md", "不要提交", "不要推送", "不要删除", "NEED_USER:",
                      "Spec 没覆盖的决策", "测试改不红", "高风险不可逆"):
            self.assertIn(words, brief)
        self.assertIn(rec["runs"][-1]["brief"], text)

    def test_checkpoint_not_sent(self):
        self.switch_on()
        self.approve_b(TODO.replace("- [ ] Task 2", "- [x] Task 2"))
        out = offload.start(self.repo, "b")
        self.assertEqual(out.code, 3)
        self.assertIn("offload handback b", "\n".join(out.lines))
        self.assertIsNone(store.get(self.db, "offload", "b"))

    def test_dirty_worktree(self):
        self.switch_on()
        self.approve_b(TODO)
        (self.wt["b"] / "src").mkdir(exist_ok=True)
        (self.wt["b"] / "src" / "x.py").write_text("x = 1\n")
        out = offload.start(self.repo, "b")
        self.assertEqual(out.code, 3)
        self.assertIn("不干净", "\n".join(out.lines))
        self.assertIsNone(store.get(self.db, "offload", "b"))

    def test_not_synced(self):
        from module_crew import review
        self.switch_on()
        (self.wt["b"] / "tasks" / "b" / "todo.md").write_text(TODO, encoding="utf-8")
        git(self.wt["b"], "commit", "-qam", "b: todo")
        s = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        p = review.add(self.db, self.plan_review("b"), "shop-b", 2).number
        assert review.approve(self.repo, [s, p], "批准 b").code == 0
        out = offload.start(self.repo, "b")
        self.assertEqual(out.code, 3)
        self.assertIn("sync", "\n".join(out.lines))

    def test_not_approved(self):
        self.switch_on()
        out = offload.start(self.repo, "b")
        self.assertEqual(out.code, 3)
        self.assertIn("Plan", "\n".join(out.lines))

    def test_already_running(self):
        self.started(TODO)
        out = offload.start(self.repo, "b")
        self.assertEqual(out.code, 3)
        self.assertIn("running", "\n".join(out.lines))

    def test_not_ready(self):
        self.switch_on()
        self.approve_b(TODO)
        self.set_cfg(checkLedger="off")
        out = offload.start(self.repo, "b")
        self.assertEqual(out.code, 3)
        self.assertIn("checkLedger", "\n".join(out.lines))

    def test_cli(self):
        self.switch_on()
        self.approve_b(TODO)
        out = self.run_cli("offload", "start", "b")
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        self.assertIn("/delegate:run --write --resumable", out.stdout)



DONE = "改好了\ndelegate: run_id=r1 status=done resumable=true\n"


class SettleCase(OffloadCase):
    def codex(self, files: dict | None = None, tick=("Task 2",), output: str = DONE, code: int = 0) -> offload.Outcome:
        """Pretend Codex changed files (None deletes) and ticked items, then settle what delegate printed."""
        wt = self.wt["b"]
        for rel, text in (files if files is not None else {"src/page.py": "PAGE = 1\n"}).items():
            if text is None:
                (wt / rel).unlink()
            else:
                (wt / rel).parent.mkdir(parents=True, exist_ok=True)
                (wt / rel).write_text(text, encoding="utf-8")
        todo = wt / "tasks" / "b" / "todo.md"
        body = todo.read_text(encoding="utf-8")
        for name in tick:
            body = body.replace(f"- [ ] {name}", f"- [x] {name}")
        todo.write_text(body, encoding="utf-8")
        out = self.tmp / "delegate.out"
        out.write_text(output, encoding="utf-8")
        return offload.settle(self.repo, "b", out, code)

    def head(self) -> str:
        return git(self.wt["b"], "rev-parse", "HEAD").strip()

    def rec(self) -> dict:
        return store.get(store.open_store(self.repo), "offload", "b")


class DoneTest(SettleCase):
    """Acceptance 6."""

    def test_commits_for_codex(self):
        self.started(TODO)
        before = self.head()
        out = self.codex()
        self.assertEqual(out.code, 0, out.lines)
        self.assertNotEqual(self.head(), before)
        subject = git(self.wt["b"], "log", "-1", "--format=%s")
        self.assertIn("Task 2", subject)
        self.assertIn("r1", subject)
        self.assertEqual(git(self.wt["b"], "status", "--porcelain").strip(), "")
        changed = git(self.wt["b"], "diff", "--name-only", before, "HEAD").split()
        self.assertEqual(sorted(changed), ["src/page.py", "tasks/b/todo.md"])
        rec = self.rec()
        self.assertEqual(rec["state"], "idle")
        self.assertEqual(rec["runs"][-1]["commit"], self.head())
        self.assertEqual(rec["runs"][-1]["runId"], "r1")
        ledger = [r for r in store.records(store.open_store(self.repo), "check").values() if r.get("by") == "offload"]
        self.assertEqual([r["result"] for r in ledger], ["pass"])
        self.assertEqual(self.quick_count(), 1)
        self.assertIn("offload handback b", "\n".join(out.lines))     # next item is a checkpoint

    def test_next_task_is_started_next(self):
        self.started(TODO.replace("- [ ] Checkpoint 1", "- [ ] Task 3：做接口\n- [ ] Checkpoint 1"))
        out = self.codex()
        self.assertEqual(out.code, 0, out.lines)
        self.assertIn("offload start b", "\n".join(out.lines))

    def assert_stopped(self, out, words: str):
        self.assertEqual(out.code, 5, out.lines)
        self.assertIn(words, "\n".join(out.lines))
        rec = self.rec()
        self.assertEqual(rec["state"], "stopped")
        self.assertIn(words, rec["runs"][-1]["reason"])
        draft = "\n".join(out.lines[out.lines.index("【等待用户】"):])
        from module_crew import protocol
        msg = protocol.parse(draft)
        self.assertEqual(msg.kind, "wait-user", msg)
        self.assertFalse(msg.problems, msg.problems)

    def test_outside_file(self):
        self.started(TODO)
        before = self.head()
        out = self.codex({"src/page.py": "PAGE = 1\n", "README.md": "changed\n"})
        self.assert_stopped(out, "README.md")
        self.assertEqual(self.head(), before)
        self.assertEqual((self.wt["b"] / "README.md").read_text(), "changed\n")
        self.assertEqual(self.quick_count(), 0)

    def test_deletion_is_outside(self):
        (self.wt["b"] / "src").mkdir(exist_ok=True)
        (self.wt["b"] / "src" / "old.py").write_text("OLD = 1\n")
        git(self.wt["b"], "add", "-A")
        git(self.wt["b"], "commit", "-qm", "b: old")
        self.started(TODO)
        before = self.head()
        out = self.codex({"src/old.py": None})
        self.assert_stopped(out, "src/old.py")
        self.assertEqual(self.head(), before)

    def test_not_ticked(self):
        self.started(TODO)
        out = self.codex(tick=())
        self.assert_stopped(out, "没勾")

    def test_ticked_other_item(self):
        self.started(TODO)
        out = self.codex(tick=("Task 2", "Checkpoint 1"))
        self.assert_stopped(out, "Checkpoint 1")

    def test_quick_check_fails(self):
        self.started(TODO)
        before = self.head()
        out = self.codex({"src/page.py": "PAGE = 1\n", "src/BROKEN.py": "x\n"})
        self.assert_stopped(out, "快检查")
        self.assertEqual(self.head(), before)
        self.assertTrue((self.wt["b"] / "src" / "BROKEN.py").exists())

    def test_declared_file_is_inside(self):
        root = Path(self.plugins.entries["spec-guard@m"][-1]["installPath"])
        doc = json.loads((root / "interface.json").read_text())
        doc["declaredScope"] = {"command": ["python3", "-B", "hooks/module_scope.py", "declared", "--project",
                                            "<project-root>", "--module", "<module-id>"]}
        (root / "interface.json").write_text(json.dumps(doc))
        os.environ["FAKE_DECLARED_JSON"] = json.dumps({"module": "b", "planApproved": True, "approvedCommit": "abc",
                                                       "declared": True, "publicPaths": ["config/app.json"],
                                                       "dependencies": [], "configs": [], "patches": []})
        self.set_cfg(declaredScope="on")
        self.started(TODO)
        out = self.codex({"src/page.py": "PAGE = 1\n", "config/app.json": "{}\n"})
        self.assertEqual(out.code, 0, out.lines)

    def test_scope_check_unusable(self):
        self.started(TODO)
        os.environ["FAKE_SCOPE_CODE"] = "4"
        out = self.codex()
        self.assert_stopped(out, "scopeCheck")

    def test_not_running(self):
        self.switch_on()
        self.approve_b(TODO)
        out = self.tmp / "delegate.out"
        out.write_text(DONE)
        res = offload.settle(self.repo, "b", out, 0)
        self.assertEqual(res.code, 3)

    def test_cli(self):
        self.started(TODO)
        (self.wt["b"] / "src").mkdir(exist_ok=True)
        (self.wt["b"] / "src" / "page.py").write_text("PAGE = 1\n")
        todo = self.wt["b"] / "tasks" / "b" / "todo.md"
        todo.write_text(todo.read_text().replace("- [ ] Task 2", "- [x] Task 2"))
        out = self.tmp / "delegate.out"
        out.write_text(DONE)
        res = self.run_cli("offload", "settle", "b", "--output", str(out), "--exit", "0")
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)



NEEDS = "先做了不受影响的部分\nNEED_USER: 金额用分还是元？\n分：精确；元：好读\ndelegate: run_id=r7 status=needs-input resumable=true\n"


class StopsTest(SettleCase):
    """Acceptance 7 (first half), 8 and 9."""

    def parse_draft(self, out):
        from module_crew import protocol
        draft = "\n".join(out.lines[out.lines.index("【等待用户】"):])
        msg = protocol.parse(draft)
        self.assertEqual(msg.kind, "wait-user", msg)
        self.assertFalse(msg.problems, msg.problems)
        return draft

    def test_needs_input(self):
        self.started(TODO)
        before = self.head()
        out = self.codex(tick=(), output=NEEDS)
        self.assertEqual(out.code, 5, out.lines)
        rec = self.rec()
        self.assertEqual(rec["state"], "needs-input")
        self.assertEqual(rec["runs"][-1]["runId"], "r7")
        self.assertEqual(rec["runs"][-1]["question"], "金额用分还是元？\n分：精确；元：好读")
        draft = self.parse_draft(out)
        self.assertIn("金额用分还是元？\n分：精确；元：好读", draft)
        self.assertIn("offload resume b", draft)
        self.assertEqual(self.head(), before)
        self.assertEqual(self.quick_count(), 0)

    def test_timeout_11(self):
        self.started(TODO)
        before = self.head()
        out = self.codex({"src/page.py": "PAGE = 1\n", "spec/b.md": "# 改到一半\n"}, tick=(), output="做到一半\n", code=124)
        self.assertEqual(out.code, 5, out.lines)
        text = "\n".join(out.lines)
        self.assertEqual(self.rec()["state"], "timeout")
        self.assertEqual(self.quick_count(), 0)
        self.assertEqual(self.head(), before)
        self.assertIn("?? src/", text)                       # git status --short
        self.assertIn("1 file changed", text)                # git diff --stat: spec/b.md
        draft = self.parse_draft(out)
        self.assertIn("offload start b --again", draft)
        self.assertNotIn("offload resume", draft)

    def test_timeout_12(self):
        from test_codex_offload import DELEGATE_12
        (self.delegate / "interface.json").write_text(json.dumps(DELEGATE_12))
        self.started(TODO)
        out = self.codex(tick=(), output="进度：页面骨架写好，接口还没接\ndelegate: run_id=r9 status=timeout resumable=true\n", code=124)
        self.assertEqual(out.code, 5, out.lines)
        rec = self.rec()
        self.assertEqual((rec["state"], rec["runs"][-1]["runId"]), ("timeout", "r9"))
        self.assertIn("进度：页面骨架写好，接口还没接", "\n".join(out.lines))
        draft = self.parse_draft(out)
        self.assertIn("offload resume b", draft)

    def test_unknown_kinds(self):
        self.started(TODO)
        for text, code in (("拒绝\n", 64), ("坏了\n", 2), ("没结果行\n", 0),
                           ("x\ndelegate: run_id=r4 status=weird resumable=true\n", 0)):
            with self.subTest(code=code, text=text):
                if self.rec()["state"] != "running":
                    self.assertEqual(offload.start(self.repo, "b", again=True).code, 0)
                out = self.codex(files={}, tick=(), output=text, code=code)
                self.assertEqual(out.code, 5, out.lines)
                self.assertEqual(self.rec()["state"], "stopped")
                self.assertIn("认不出", self.rec()["runs"][-1]["reason"])
                self.assertIn(text.strip().splitlines()[-1], "\n".join(out.lines))
                draft = self.parse_draft(out)
                self.assertNotIn("offload resume", draft)

    def test_unreadable_output(self):
        self.started(TODO)
        res = offload.settle(self.repo, "b", self.tmp / "missing.out", 0)
        self.assertEqual(res.code, 5)
        self.assertEqual(self.rec()["state"], "stopped")



class ResumeTest(SettleCase):
    """Acceptance 7 (second half) and 8 (second half)."""

    def test_resume_needs_input(self):
        self.started(TODO)
        self.codex(tick=(), output=NEEDS)
        out = self.run_cli("offload", "resume", "b", "--original", "用分")
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        self.assertIn("/delegate:run --resume r7 --write", out.stdout)
        rec = self.rec()
        self.assertEqual(rec["state"], "running")
        run = rec["runs"][-1]
        self.assertEqual((run["resumeOf"], run["answer"]["original"]), ("r7", "用分"))
        self.assertEqual(Path(run["answerFile"]).read_text(encoding="utf-8"), "用分")
        self.assertIn(run["answerFile"], out.stdout)
        done = self.codex(output=DONE.replace("r1", "r8"))
        self.assertEqual(done.code, 0, done.lines)

    def test_resume_needs_words(self):
        self.started(TODO)
        self.codex(tick=(), output=NEEDS)
        out = self.run_cli("offload", "resume", "b", "--original", "  ")
        self.assertEqual(out.returncode, 3)
        self.assertEqual(self.rec()["state"], "needs-input")

    def test_resume_wrong_state(self):
        self.started(TODO)
        res = offload.resume(self.repo, "b", {"original": "用分"})
        self.assertEqual(res.code, 3)
        self.codex(tick=(), output="做到一半\n", code=124)          # 1.1 timeout: no run id
        res = offload.resume(self.repo, "b", {"original": "接着做"})
        self.assertEqual(res.code, 3)
        self.assertIn("--again", "\n".join(res.lines))

    def test_resume_timeout_12(self):
        (self.delegate / "interface.json").write_text(json.dumps(DELEGATE_12))
        self.started(TODO)
        self.codex(tick=(), output="进度\ndelegate: run_id=r9 status=timeout resumable=true\n", code=124)
        res = offload.resume(self.repo, "b", {"original": "接着做"})
        self.assertEqual(res.code, 0, res.lines)
        self.assertIn("--resume r9", "\n".join(res.lines))

    def test_again_needs_words(self):
        self.started(TODO)
        self.codex(tick=(), output="做到一半\n", code=124)
        out = self.run_cli("offload", "start", "b", "--again")
        self.assertEqual(out.returncode, 3)
        self.assertEqual(self.rec()["state"], "timeout")

    def test_again_after_timeout_keeps_task_and_base(self):
        self.started(TODO)
        base = self.rec()["base"]
        self.codex({"src/page.py": "PAGE = 0\n"}, tick=(), output="做到一半\n", code=124)
        out = self.run_cli("offload", "start", "b", "--again", "--original", "接着做")
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        rec = self.rec()
        self.assertEqual((rec["state"], rec["base"], rec["task"]), ("running", base, "Task 2：做页面"))
        self.assertEqual(rec["runs"][-1]["again"]["original"], "接着做")
        brief = Path(rec["runs"][-1]["brief"]).read_text(encoding="utf-8")
        self.assertIn("上次留下的改动", brief)

    def test_again_after_stop_with_ticked_item_keeps_task(self):
        self.started(TODO)
        self.codex({"src/page.py": "PAGE = 1\n", "README.md": "越界\n"})      # ticked, but outside → stopped
        self.assertEqual(offload.start(self.repo, "b", again=True).code, 0)
        self.assertEqual(self.rec()["task"], "Task 2：做页面")

    def test_again_refused_while_waiting(self):
        self.started(TODO)
        self.assertEqual(offload.start(self.repo, "b", again=True).code, 3)       # running
        self.codex(tick=(), output=NEEDS)
        res = offload.start(self.repo, "b", again=True)
        self.assertEqual(res.code, 3)
        self.assertIn("offload resume", "\n".join(res.lines))



class NoticeTest(SettleCase):
    """Acceptance 4, 10 and the approve part of acceptance 2."""

    def notice(self, res) -> list:
        from module_crew import protocol
        db = store.open_store(self.repo)
        return [protocol.parse(store.read_body(db, x["body"])) for x in res.sends if x["kind"] == "coordination-notice"]

    def approve(self):
        from module_crew import review
        (self.wt["b"] / "tasks" / "b" / "todo.md").write_text(TODO, encoding="utf-8")
        git(self.wt["b"], "commit", "-qam", "b: todo")
        s = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        p = review.add(self.db, self.plan_review("b"), "shop-b", 2).number
        return review.approve(self.repo, [s, p], "批准 b")

    def test_off_is_today(self):
        from module_crew import review
        res = self.approve()
        [msg] = self.notice(res)
        self.assertEqual(msg.fields["要你做什么"], review.start_todo_today("b"))
        self.assertFalse(any("外包" in x for x in res.lines))

    def test_offload_notice(self):
        self.switch_on()
        res = self.approve()
        [msg] = self.notice(res)
        self.assertFalse(msg.problems, msg.problems)
        todo = msg.fields["要你做什么"]
        for words in ("外包给 Codex", "module-crew sync", "不构建", "【等待其他会话】", "先不同步"):
            self.assertIn(words, todo)
        self.assertIn("offload start b", "\n".join(res.lines))

    def test_held_when_not_ready(self):
        self.switch_on()
        (self.codex_home / "config.toml").write_text(f'[projects."{self.repo}"]\ntrust_level = "untrusted"\n')
        res = self.approve()
        self.assertEqual(self.notice(res), [])
        self.assertIn("外包条件不满足", "\n".join(res.lines))
        out = self.run_cli("offload", "decline", "b", "--original", "让模块会话自己做")
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        from module_crew import protocol, review
        path = out.stdout.split("正文文件：")[1].strip()
        msg = protocol.parse(Path(path).read_text(encoding="utf-8"))
        self.assertFalse(msg.problems, msg.problems)
        self.assertEqual(msg.fields["类型"], "开工")
        self.assertEqual(msg.fields["要你做什么"], review.start_todo_today("b"))
        self.assertEqual(self.rec()["state"], "handed-back")
        self.assertEqual(self.run_cli("offload", "decline", "b", "--original", " ").returncode, 3)

    def test_handback_checkpoint(self):
        self.started(TODO)
        self.codex()
        out = offload.handback(self.repo, "b")
        self.assertEqual(out.code, 0, out.lines)
        from module_crew import protocol
        path = out.lines[-1].split("正文文件：")[1].strip()
        msg = protocol.parse(Path(path).read_text(encoding="utf-8"))
        self.assertFalse(msg.problems, msg.problems)
        self.assertEqual(msg.fields["类型"], "恢复")
        self.assertIn("C", msg.fields["依据"])
        self.assertIn("Checkpoint 1", msg.fields["要你做什么"])
        self.assertEqual(self.rec()["state"], "idle")

    def test_handback_after_stop(self):
        self.started(TODO)
        self.codex(tick=(), output="做到一半\n", code=124)
        out = offload.handback(self.repo, "b")
        self.assertEqual(out.code, 0, out.lines)
        self.assertEqual(self.rec()["state"], "handed-back")
        res = offload.start(self.repo, "b")
        self.assertEqual(res.code, 3)
        self.assertIn("--again", "\n".join(res.lines))

    def test_handback_refused(self):
        self.switch_on()
        self.approve_b(TODO)
        self.assertEqual(offload.handback(self.repo, "b").code, 3)            # never offloaded
        offload.start(self.repo, "b")
        self.assertEqual(offload.handback(self.repo, "b").code, 3)            # running



class ShowTest(SettleCase):
    """Acceptance 11."""

    def test_show(self):
        self.assertEqual(self.run_cli("offload", "show").returncode, 3)
        self.started(TODO)
        self.codex(tick=(), output=NEEDS)
        out = self.run_cli("offload", "show", "b")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("等用户回答", out.stdout)
        self.assertIn("Task 2：做页面", out.stdout)
        self.assertIn("金额用分还是元？", out.stdout)
        js = json.loads(self.run_cli("offload", "show", "--json").stdout)
        self.assertEqual(js["offload"][0]["state"], "needs-input")

    def test_show_commits(self):
        self.started(TODO)
        self.codex()
        out = self.run_cli("offload", "show")
        self.assertIn(self.head()[:7], out.stdout)


if __name__ == "__main__":
    unittest.main()
