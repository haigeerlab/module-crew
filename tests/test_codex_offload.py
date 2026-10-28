"""crew-codex-offload, round 2: the module session hands its Tasks to one Codex session through delegate >= 1.3,
checks what comes back and commits it itself (see spec/crew-codex-offload.md)."""

import hashlib
import json
import os
import unittest
from pathlib import Path

from helpers import MergeCase, git

from module_crew import offload, store

DELEGATE_13 = {"interface": "1.3", "run": {
    "command": "/delegate:run", "backends": ["codex"], "write": "explicit",
    "resume": {"optIn": "--resumable", "option": "--resume", "backends": ["codex"],
               "statuses": ["done", "needs-input", "timeout"]},
    "timeout": {"status": "timeout", "exitCode": 124},
    "result": {"schemaVersion": 1, "line": "delegate: result=<path>", "strict": "--strict",
               "statuses": ["done", "needs-input", "timeout", "unmarked", "failed", "interrupted", "unreaped", "empty"]},
    "continue": {"option": "--continue", "backends": ["codex"], "accepts": ["done"], "chain": "--resumable",
                 "stateRetentionDays": 14},
    "longRun": {"option": "--timeout", "minSeconds": 541, "maxSeconds": 7200, "defaultSeconds": 540, "background": "caller"},
    "check": {"option": "--check", "shell": False, "when": "done", "timeoutSeconds": 600},
    "writeAuthorization": {"option": "--authorized-by", "requires": "--write", "recorded": "result.authorization"}}}

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

TODO = ("# Todo: b\n\n- [x] Task 1：打底\n- [ ] Task 2：做页面\n- [ ] Task 3：做接口\n"
        "- [ ] Checkpoint 1（report）：页面就位\n- [ ] Checkpoint 2（gate）：最终验收\n")
WORDS = "下一个模块交给 Codex"


def with_delegate(**changes) -> dict:
    """DELEGATE_13 with run.<key> replaced (None drops it); `interface` sets the version."""
    doc = json.loads(json.dumps(DELEGATE_13))
    for key, value in changes.items():
        if key == "interface":
            doc["interface"] = value
        elif value is None:
            doc["run"].pop(key, None)
        else:
            doc["run"][key] = value
    return doc


class OffloadCase(MergeCase):
    """Module b with an approved-looking Spec and Plan, quick check and ledger on, delegate 1.3, scopeCheck."""

    def setUp(self) -> None:
        super().setUp()
        self.delegate = self.plugins.install("delegate", DELEGATE_13)
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
        self.runs = 0

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
        offload.set_switch(self.db, self.repo, "on", WORDS)

    def set_host(self, host: str):
        with self.db.transaction(actor="test") as tx:
            rec = store.get(self.db, "session", "shop-b")
            tx.put("session", "shop-b", {**rec, "host": host}, action="set")

    def quick_count(self) -> int:
        return len(self.quick_calls.read_text()) if self.quick_calls.exists() else 0

    def approve_b(self, todo: str | None = None, sync_after: bool = True):
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
        if sync_after:
            out = sync.run(wt)
            assert out.code == 0, out.lines
        self.db = store.open_store(self.repo)
        return res

    def started(self, todo: str = TODO) -> offload.Outcome:
        self.switch_on()
        self.approve_b(todo)
        out = offload.start(self.wt["b"], "b")
        assert out.code == 0, out.lines
        return out

    def rec(self) -> dict:
        return store.get(store.open_store(self.repo), "offload", "b")

    def head(self) -> str:
        return git(self.wt["b"], "rev-parse", "HEAD").strip()

    def outputs(self, status: str | None, code: int, answer: str = "DONE: 改好了", line: bool = True,
                result_line: bool = True, file_status: str | None = "same", grant: str | None = "same",
                run_id: str | None = None) -> tuple[Path, Path]:
        """What /delegate:run would print: stdout (answer, result= line, result line), stderr, and the result file."""
        self.runs += 1
        rid = run_id or f"r{self.runs}"
        result = self.tmp / f"{rid}.result.json"
        sha = self.rec()["authorization"]["sha256"] if grant == "same" else grant
        doc = {"schemaVersion": 1, "status": status if file_status == "same" else file_status, "exitCode": code,
               "runId": rid, "authorization": {"source": "file", "path": "x", "sha256": sha, "bytes": 1} if sha else None}
        if file_status is not None:
            result.write_text(json.dumps(doc), encoding="utf-8")
        stdout, stderr = [answer] if answer else [], ["delegate: 元数据……"]
        if line and status is not None:
            if result_line and file_status is not None:
                stdout.append(f"delegate: result={result}")
            stdout.append(f"delegate: run_id={rid} status={status} resumable=true")
        elif file_status is not None:
            stderr.append(f"delegate: result={result}")
        out, err = self.tmp / f"{rid}.out", self.tmp / f"{rid}.err"
        out.write_text("\n".join(stdout) + "\n", encoding="utf-8")
        err.write_text("\n".join(stderr) + "\n", encoding="utf-8")
        return out, err

    def codex(self, files: dict | None = None, tick=("Task 2",), status: str | None = "done", code: int = 0,
              **kw) -> offload.Outcome:
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
        out, err = self.outputs(status, code, **kw)
        return offload.settle(wt, "b", out, err, code)

    def parse_draft(self, out):
        from module_crew import protocol
        draft = "\n".join(out.lines[out.lines.index("【等待用户】"):])
        msg = protocol.parse(draft)
        self.assertEqual(msg.kind, "wait-user", msg)
        self.assertFalse(msg.problems, msg.problems)
        return draft


class SwitchTest(OffloadCase):
    """Decision 1 (round 1, unchanged) plus the words kept for the grant."""

    def test_on_with_words(self):
        out = self.run_cli("config", "set", "--codex-offload", "on", "--original", "打开额度外包")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("同一个 Codex 会话", out.stdout)
        cfg = store.get(store.open_store(self.repo), "config", "main")
        self.assertEqual(cfg["codexOffload"], "on")
        self.assertEqual(cfg["codexOffloadOriginal"]["original"], "打开额度外包")

    def test_refused_without_ledger(self):
        self.set_cfg(checkLedger=None)
        out = self.run_cli("config", "set", "--codex-offload", "on", "--original", "打开额度外包")
        self.assertEqual(out.returncode, 3)
        self.assertIn("checkLedger", out.stderr)
        self.assertNotIn("codexOffload", store.get(store.open_store(self.repo), "config", "main"))

    def test_empty_words_refused(self):
        self.assertEqual(self.run_cli("config", "set", "--codex-offload", "on", "--original", " ").returncode, 3)

    def test_warns_when_not_ready(self):
        (self.delegate / "interface.json").write_text(json.dumps(with_delegate(interface="1.2")))
        out = self.run_cli("config", "set", "--codex-offload", "on", "--original", "打开额度外包")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("⚠️", out.stdout)
        self.assertIn("1.3", out.stdout)


class ReadyTest(OffloadCase):
    """Acceptance 1."""

    def setUp(self) -> None:
        super().setUp()
        self.switch_on()

    def why(self, module="b"):
        return offload.ready(self.db, self.repo, module)

    def test_all_met(self):
        self.assertIsNone(self.why())

    def test_delegate_12(self):
        (self.delegate / "interface.json").write_text(json.dumps(with_delegate(interface="1.2")))
        self.assertIn("低于 1.3", self.why())

    def test_each_flag(self):
        for changes, words in (({"continue": None}, "run.continue"), ({"longRun": None}, "run.longRun"),
                               ({"longRun": {"option": "--timeout", "maxSeconds": 900}}, "run.longRun"),
                               ({"result": None}, "run.result"), ({"writeAuthorization": None}, "run.writeAuthorization"),
                               ({"resume": {"option": "--resume", "backends": ["codex"], "statuses": ["done", "needs-input"]}},
                                "run.resume")):
            with self.subTest(words=words, changes=changes):
                (self.delegate / "interface.json").write_text(json.dumps(with_delegate(**changes)))
                self.assertIn(words, self.why())

    def test_switch_words_missing(self):
        self.set_cfg(codexOffloadOriginal=None)
        self.assertIn("原话", self.why())

    def test_module_on_codex(self):
        self.set_host("codex-desktop")
        self.assertIn("Codex", self.why())
        self.assertIsNone(offload.ready(self.db, self.repo))         # project-wide check leaves ⑤ out

    def test_ledger_off(self):
        self.set_cfg(checkLedger="off")
        self.assertIn("checkLedger", self.why())

    def test_no_scope_check(self):
        root = Path(self.plugins.entries["spec-guard@m"][-1]["installPath"])
        doc = json.loads((root / "interface.json").read_text())
        del doc["scopeCheck"]
        (root / "interface.json").write_text(json.dumps(doc))
        self.assertIn("scopeCheck", self.why())

    def test_untrusted(self):
        (self.codex_home / "config.toml").write_text(f'[projects."{self.repo}"]\ntrust_level = "untrusted"\n')
        self.assertIn("untrusted", self.why())


class NoticeTest(OffloadCase):
    """Acceptance 2, 3 and the first half of 10."""

    def notices(self, res) -> list:
        from module_crew import protocol
        db = store.open_store(self.repo)
        return [protocol.parse(store.read_body(db, x["body"])) for x in res.sends if x["kind"] == "coordination-notice"]

    def test_off_is_today(self):
        from module_crew import review
        res = self.approve_b(TODO, sync_after=False)
        [msg] = self.notices(res)
        self.assertEqual(msg.fields["要你做什么"], review.start_todo_today("b"))
        self.assertFalse(any("外包" in x for x in res.lines))
        self.assertIsNone(self.rec())

    def test_assigned(self):
        self.switch_on()
        res = self.approve_b(TODO, sync_after=False)
        [msg] = self.notices(res)
        self.assertFalse(msg.problems, msg.problems)
        todo = msg.fields["要你做什么"]
        for words in ("交给 Codex", "module-crew sync", "offload start b", "offload settle", "检查点、最终验收照常由你处理"):
            self.assertIn(words, todo)
        self.assertNotIn("【等待其他会话】", todo)
        rec = self.rec()
        self.assertEqual((rec["state"], rec["version"], rec["approval"]), ("assigned", 2, res.approval))
        grant = Path(rec["authorization"]["path"])
        text = grant.read_text(encoding="utf-8")
        for words in (WORDS, "模块 b", f"C{res.approval}"):
            self.assertIn(words, text)
        self.assertEqual(hashlib.sha256(grant.read_bytes()).hexdigest(), rec["authorization"]["sha256"])
        self.assertEqual(oct(grant.stat().st_mode & 0o777), "0o600")
        self.assertIn(f"授权文件 {grant}", "\n".join(res.lines))

    def test_module_on_codex_is_today(self):
        from module_crew import review
        self.switch_on()
        self.set_host("codex-desktop")
        res = self.approve_b(TODO, sync_after=False)
        [msg] = self.notices(res)
        self.assertEqual(msg.fields["要你做什么"], review.start_todo_today("b"))
        self.assertIn("模块会话在 Codex，本模块不外包", "\n".join(res.lines))
        self.assertIsNone(self.rec())

    def test_held_then_declined(self):
        from module_crew import protocol, review
        self.switch_on()
        (self.codex_home / "config.toml").write_text(f'[projects."{self.repo}"]\ntrust_level = "untrusted"\n')
        res = self.approve_b(TODO, sync_after=False)
        self.assertEqual(self.notices(res), [])
        self.assertIn("外包条件不满足", "\n".join(res.lines))
        out = self.run_cli("offload", "decline", "b", "--original", "让模块会话自己做")
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        msg = protocol.parse(Path(out.stdout.split("正文文件：")[1].strip()).read_text(encoding="utf-8"))
        self.assertFalse(msg.problems, msg.problems)
        self.assertEqual(msg.fields["要你做什么"], review.start_todo_today("b"))
        self.assertEqual(self.rec()["state"], "declined")
        res = offload.start(self.wt["b"], "b")
        self.assertEqual(res.code, 3)
        self.assertIn("开工时没交给 Codex", "\n".join(res.lines))


class StartTest(OffloadCase):
    """Acceptance 4."""

    def test_first_is_resumable(self):
        out = self.started()
        text = "\n".join(out.lines)
        rec = self.rec()
        grant = rec["authorization"]["path"]
        self.assertIn(f"/delegate:run --write --resumable --strict --timeout 1800 --authorized-by {grant} -- ", text)
        self.assertIn("后台", text)
        self.assertIn("--stderr", text)
        self.assertEqual((rec["state"], rec["task"]), ("running", "Task 2：做页面"))
        brief = Path(rec["runs"][-1]["text"]).read_text(encoding="utf-8")
        for words in ("Task 2：做页面", "spec/b.md", "tasks/b/plan.md", "不要提交", "不要推送", "不要删除", "NEED_USER:",
                      "DONE:", "Spec 没覆盖的决策", "测试改不红", "高风险不可逆"):
            self.assertIn(words, brief)

    def test_continue_after_done(self):
        self.started()
        self.assertEqual(self.codex(run_id="r-a").code, 0)
        out = offload.start(self.wt["b"], "b")
        self.assertEqual(out.code, 0, out.lines)
        self.assertIn("/delegate:run --continue r-a --write --strict --timeout 1800 --authorized-by", "\n".join(out.lines))
        rec = self.rec()
        self.assertEqual((rec["task"], rec["head"]), ("Task 3：做接口", None))
        self.assertIn("上一项已核对并提交", Path(rec["runs"][-1]["text"]).read_text(encoding="utf-8"))

    def refused(self, out, words):
        self.assertEqual(out.code, 3, out.lines)
        self.assertIn(words, "\n".join(out.lines))

    def test_checkpoint_not_sent(self):
        self.switch_on()
        self.approve_b(TODO.replace("- [ ] Task 2", "- [x] Task 2").replace("- [ ] Task 3", "- [x] Task 3"))
        self.refused(offload.start(self.wt["b"], "b"), "由你按 Plan 处理")
        self.assertEqual(self.rec()["state"], "assigned")

    def test_not_module_session(self):
        self.switch_on()
        self.approve_b(TODO)
        self.refused(offload.start(self.repo, "b"), "模块会话 worktree")

    def test_not_assigned(self):
        self.approve_b(TODO)
        self.switch_on()                                   # turned on after b started: b stays with Claude
        self.refused(offload.start(self.wt["b"], "b"), "开工时没交给 Codex")

    def test_round_one_record(self):
        self.switch_on()
        self.approve_b(TODO)
        with self.db.transaction(actor="test") as tx:
            tx.put("offload", "b", {"module": "b", "state": "idle", "runs": []}, action="set")
        self.refused(offload.start(self.wt["b"], "b"), "旧版")

    def test_grant_changed(self):
        self.switch_on()
        self.approve_b(TODO)
        Path(self.rec()["authorization"]["path"]).write_text("改过了\n", encoding="utf-8")
        self.refused(offload.start(self.wt["b"], "b"), "授权文件")

    def test_dirty(self):
        self.switch_on()
        self.approve_b(TODO)
        (self.wt["b"] / "src").mkdir(exist_ok=True)
        (self.wt["b"] / "src" / "x.py").write_text("x = 1\n")
        self.refused(offload.start(self.wt["b"], "b"), "不干净")

    def test_not_synced(self):
        self.switch_on()
        self.approve_b(TODO, sync_after=False)
        self.refused(offload.start(self.wt["b"], "b"), "sync")

    def test_already_running(self):
        self.started()
        self.refused(offload.start(self.wt["b"], "b"), "正在跑")

    def test_cli(self):
        self.switch_on()
        self.approve_b(TODO)
        out = self.run_cli("offload", "start", "b", cwd=self.wt["b"])
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        self.assertIn("--resumable", out.stdout)


class ClassifyTest(OffloadCase):
    """Acceptance 8: every row of decision 7's table and the four unknowns."""

    GRANT = "g" * 64

    def sort(self, status, code, grant=GRANT, **kw):
        out, err = self.outputs(status, code, grant=grant, **kw)
        return offload.classify(code, offload.read_outputs(out.read_text(), err.read_text()), self.GRANT)

    def test_rows(self):
        rows = [("done", 0, {}, "done"), ("needs-input", 0, {"answer": "NEED_USER: 用哪个？"}, "needs-input"),
                ("timeout", 124, {}, "timeout"), ("unmarked", 1, {"line": False}, "retry"),
                ("failed", 1, {"line": False}, "retry"), ("empty", 2, {"line": False}, "retry"),
                ("interrupted", 143, {"line": False}, "interrupted"), ("interrupted", 130, {"line": False}, "interrupted"),
                ("unreaped", 125, {"line": False}, "unreaped"), (None, 125, {"file_status": None}, "unreaped"),
                (None, 64, {"file_status": None}, "refused")]
        for status, code, kw, cls in rows:
            with self.subTest(status=status, code=code):
                self.assertEqual(self.sort(status, code, **kw).cls, cls)

    def test_unknowns(self):
        rows = [("weird", 0, {}), ("done", 1, {}), ("done", 0, {"file_status": "timeout"}),
                ("done", 0, {"grant": "0" * 64}), ("done", 0, {"grant": None}),
                ("done", 0, {"result_line": False, "file_status": None}), ("needs-input", 0, {"answer": "没有标记"})]
        for status, code, kw in rows:
            with self.subTest(status=status, code=code, kw=kw):
                self.assertEqual(self.sort(status, code, **kw).cls, "unknown")

    def test_question_drops_result_line(self):
        for result_line in (True, False):
            with self.subTest(result_line=result_line):
                out, err = self.outputs("needs-input", 0, grant=self.GRANT, result_line=result_line,
                                        answer="先做了 A\nNEED_USER: 金额用分还是元？\n分：精确；元：好读")
                got = offload.read_outputs(out.read_text(), err.read_text())
                self.assertEqual(offload._after(got.answer, offload.NEED_USER), "金额用分还是元？\n分：精确；元：好读")
                # without the result= line there is no result file to vouch for the grant: never taken as an answer
                self.assertEqual(offload.classify(0, got, self.GRANT).cls, "needs-input" if result_line else "unknown")


class DoneTest(OffloadCase):
    """Acceptance 5."""

    def test_commits(self):
        self.started()
        before = self.head()
        out = self.codex(run_id="r-ok")
        self.assertEqual(out.code, 0, out.lines)
        subject = git(self.wt["b"], "log", "-1", "--format=%s")
        self.assertIn("Task 2", subject)
        self.assertIn("r-ok", subject)
        self.assertEqual(sorted(git(self.wt["b"], "diff", "--name-only", before, "HEAD").split()),
                         ["src/page.py", "tasks/b/todo.md"])
        rec = self.rec()
        self.assertEqual((rec["state"], rec["head"], rec["runs"][-1]["commit"]), ("idle", "r-ok", self.head()))
        ledger = [r for r in store.records(store.open_store(self.repo), "check").values() if r.get("by") == "offload"]
        self.assertEqual([r["result"] for r in ledger], ["pass"])
        self.assertIn("offload start b", "\n".join(out.lines))

    def assert_retried(self, out, words):
        self.assertEqual(out.code, 4, out.lines)
        text = "\n".join(out.lines)
        self.assertIn(words, text)
        self.assertIn("--continue", text)
        rec = self.rec()
        self.assertEqual(rec["state"], "running")
        self.assertEqual(rec["runs"][-1]["mode"], "continue")
        self.assertIn(words, Path(rec["runs"][-1]["text"]).read_text(encoding="utf-8"))

    def test_outside_file(self):
        self.started()
        before = self.head()
        out = self.codex({"src/page.py": "PAGE = 1\n", "README.md": "changed\n"})
        self.assert_retried(out, "README.md")
        self.assertEqual(self.head(), before)
        self.assertEqual((self.wt["b"] / "README.md").read_text(), "changed\n")
        self.assertEqual(self.quick_count(), 0)

    def test_deletion_is_outside(self):
        (self.wt["b"] / "src").mkdir(exist_ok=True)
        (self.wt["b"] / "src" / "old.py").write_text("OLD = 1\n")
        git(self.wt["b"], "add", "-A")
        git(self.wt["b"], "commit", "-qm", "b: old")
        self.started()
        self.assert_retried(self.codex({"src/old.py": None}), "src/old.py")

    def test_not_ticked_and_other_ticked(self):
        self.started()
        self.assert_retried(self.codex(tick=()), "没勾")
        self.tearDown()
        self.setUp()
        self.started()
        self.assert_retried(self.codex(tick=("Task 2", "Task 3")), "Task 3")

    def test_quick_check_fails(self):
        self.started()
        before = self.head()
        self.assert_retried(self.codex({"src/page.py": "PAGE = 1\n", "src/BROKEN.py": "x\n"}), "快检查")
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
        self.started()
        self.assertEqual(self.codex({"src/page.py": "PAGE = 1\n", "config/app.json": "{}\n"}).code, 0)

    def test_second_miss_goes_to_claude(self):
        self.started()
        self.codex({"src/page.py": "PAGE = 1\n", "README.md": "changed\n"})
        out = self.codex(files={})                                    # still outside
        self.assertEqual(out.code, 4, out.lines)
        text = "\n".join(out.lines)
        self.assertIn("Task 2：做页面 改由 Claude 写（Codex 连续 2 次没通过", text)
        rec = self.rec()
        self.assertEqual((rec["state"], rec["claudeTasks"]), ("idle", ["Task 2：做页面"]))
        self.assertEqual(rec["head"], rec["runs"][-1]["runId"])      # a done run: the chain goes on
        git(self.wt["b"], "reset", "-q")
        todo = self.wt["b"] / "tasks" / "b" / "todo.md"
        todo.write_text(todo.read_text().replace("- [x] Task 2", "- [ ] Task 2"))
        (self.wt["b"] / "README.md").unlink()
        git(self.wt["b"], "add", "-A")
        git(self.wt["b"], "commit", "-qm", "b: Task 2 half by Claude")
        self.assertIn("已退回 Claude", "\n".join(offload.start(self.wt["b"], "b").lines))
        todo.write_text(todo.read_text().replace("- [ ] Task 2", "- [x] Task 2"))
        git(self.wt["b"], "commit", "-qam", "b: Task 2 by Claude")
        out = offload.start(self.wt["b"], "b")
        self.assertEqual(out.code, 0, out.lines)
        self.assertIn(f"--continue {rec['head']}", "\n".join(out.lines))
        self.assertIn("由模块会话完成", Path(self.rec()["runs"][-1]["text"]).read_text(encoding="utf-8"))


class StopsTest(OffloadCase):
    """Acceptance 6 to 9: needs-input, timeout, retries, stops and handing to Claude."""

    def test_needs_input(self):
        self.started()
        before = self.head()
        out = self.codex(tick=(), status="needs-input", answer="先做了 A\nNEED_USER: 金额用分还是元？\n分：精确；元：好读",
                         run_id="r-q")
        self.assertEqual(out.code, 5, out.lines)
        rec = self.rec()
        self.assertEqual((rec["state"], rec["runs"][-1]["runId"]), ("needs-input", "r-q"))
        self.assertEqual(rec["runs"][-1]["question"], "金额用分还是元？\n分：精确；元：好读")
        self.assertEqual(rec.get("failures"), {})
        draft = self.parse_draft(out)
        self.assertIn("金额用分还是元？\n分：精确；元：好读", draft)
        self.assertIn("来自：shop-b", draft)
        self.assertEqual((self.head(), self.quick_count()), (before, 0))
        self.assertEqual(offload.resume(self.wt["b"], "b", {"original": " "}).code, 3)
        res = self.run_cli("offload", "resume", "b", "--original", "用分", cwd=self.wt["b"])
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertIn("/delegate:run --resume r-q --write --strict --timeout 1800 --authorized-by", res.stdout)
        run = self.rec()["runs"][-1]
        self.assertEqual((run["mode"], run["answer"]["original"]), ("resume", "用分"))
        self.assertEqual(Path(run["text"]).read_text(encoding="utf-8"), "用分")
        self.assertEqual(self.codex().code, 0)

    def test_timeout(self):
        self.started()
        before = self.head()
        out = self.codex({"src/page.py": "PAGE = 1\n", "spec/b.md": "# 改到一半\n"}, tick=(), status="timeout", code=124,
                         answer="TIME_UP: 页面骨架写好，接口还没接")
        self.assertEqual(out.code, 5, out.lines)
        text = "\n".join(out.lines)
        self.assertEqual(self.rec()["state"], "timeout")
        self.assertEqual((self.quick_count(), self.head()), (0, before))
        for words in ("?? src/", "1 file changed", "页面骨架写好，接口还没接"):
            self.assertIn(words, text)
        draft = self.parse_draft(out)
        for words in ("offload resume b", "offload takeover b", "先停"):
            self.assertIn(words, draft)
        res = offload.resume(self.wt["b"], "b", {"original": "接着做"})
        self.assertEqual(res.code, 0, res.lines)
        again = self.codex(files={}, tick=(), status="timeout", code=124, answer="TIME_UP: 还没好")
        self.assertEqual(again.code, 4, again.lines)                  # second miss: to Claude
        self.assertEqual(self.rec()["claudeTasks"], ["Task 2：做页面"])

    def test_retry_new_chain(self):
        self.started()
        out = self.codex(files={}, tick=(), status="failed", code=1, line=False)
        self.assertEqual(out.code, 4, out.lines)
        self.assertIn("--resumable", "\n".join(out.lines))
        self.assertEqual(self.rec()["runs"][-1]["mode"], "resumable")

    def test_unreaped_always_asks(self):
        self.started()
        for _ in range(2):
            out = self.codex(files={}, tick=(), status="unreaped", code=125, line=False)
            self.assertEqual(out.code, 5, out.lines)
            draft = self.parse_draft(out)
            self.assertNotIn("offload start b --again", draft)
            if self.rec()["state"] == "stopped" and len(self.rec()["failures"]["Task 2：做页面"]) == 1:
                self.assertEqual(offload.start(self.wt["b"], "b", again=True, answer={"original": "重派"}).code, 0)
        self.assertEqual(self.rec()["claudeTasks"], [])

    def test_unknown_stops_with_tail(self):
        self.started()
        out = self.codex(files={}, tick=(), status="weird", code=0, answer="最后一句")
        self.assertEqual(out.code, 5, out.lines)
        self.assertEqual(self.rec()["state"], "stopped")
        self.assertIn("最后一句", "\n".join(out.lines))
        draft = self.parse_draft(out)
        self.assertIn("offload start b --again", draft)
        self.assertEqual(offload.start(self.wt["b"], "b", again=True, answer={"original": " "}).code, 3)

    def test_unreadable_output(self):
        self.started()
        res = offload.settle(self.wt["b"], "b", self.tmp / "missing.out", self.tmp / "missing.err", 0)
        self.assertEqual(res.code, 5)
        self.assertEqual(self.rec()["state"], "stopped")

    def test_takeover(self):
        self.started()
        self.codex(files={}, tick=(), status="weird", code=0)
        self.assertEqual(self.run_cli("offload", "takeover", "b", "--original", " ", cwd=self.wt["b"]).returncode, 3)
        out = self.run_cli("offload", "takeover", "b", "--original", "B", cwd=self.wt["b"])
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        rec = self.rec()
        self.assertEqual((rec["state"], rec["claudeTasks"], rec["takenOver"]["original"]), ("idle", ["Task 2：做页面"], "B"))


class ShowTest(OffloadCase):
    """Acceptance 10 (second half) and 11."""

    def test_show(self):
        self.assertEqual(self.run_cli("offload", "show").returncode, 3)
        self.started()
        self.codex(run_id="r-1")
        offload.start(self.wt["b"], "b")
        self.codex(tick=(), status="needs-input", answer="NEED_USER: 金额用分还是元？", run_id="r-2")
        out = self.run_cli("offload", "show", "b")
        self.assertEqual(out.returncode, 0, out.stderr)
        for words in ("等用户回答", "Task 3：做接口", "金额用分还是元？", "r-1→r-2"):
            self.assertIn(words, out.stdout)
        js = json.loads(self.run_cli("offload", "show", "--json").stdout)
        self.assertEqual(js["offload"][0]["state"], "needs-input")

    def test_legacy_and_handback_gone(self):
        with self.db.transaction(actor="test") as tx:
            tx.put("offload", "b", {"module": "b", "state": "handed-back", "runs": []}, action="set")
        self.assertIn("旧版记录", self.run_cli("offload", "show").stdout)
        self.assertEqual(self.run_cli("offload", "handback", "b").returncode, 2)


if __name__ == "__main__":
    unittest.main()
