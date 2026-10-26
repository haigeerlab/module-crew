"""crew-declared-scope: declared public files edited in the module branch, early landing, the final-review section,
modules with a dependency not opened together (see spec/crew-declared-scope.md)."""

import json
import os
import unittest
from pathlib import Path

from helpers import MergeCase, ReviewCase, StartCase, git

from module_crew import declared, store

FAKE_DECLARED = '''import json, os, sys
args = sys.argv[1:]
log = os.environ.get("FAKE_DECLARED_ARGS")
if log:
    with open(log, "a") as f:
        f.write(json.dumps(args) + "\\n")
module = args[args.index("--module") + 1]
spec = json.load(open(os.environ["FAKE_DECLARED_OUT"]))
mine = spec.get(module, spec.get("*", {"code": 0, "out": {"declared": False}}))
out = dict(mine.get("out") or {})
out.setdefault("module", module)
print(json.dumps(out, ensure_ascii=False))
sys.exit(mine.get("code", 0))
'''

DECLARED_COMMAND = ["python3", "-B", "hooks/module_scope.py", "declared", "--project", "<project-root>",
                    "--module", "<module-id>"]


def usable(paths=("config/app.json", "shared/"), configs=(), patches=(), deps=(), commit="abc123"):
    return {"code": 0, "out": {"planApproved": True, "approvedCommit": commit, "declared": True,
                               "publicPaths": list(paths), "configs": list(configs), "patches": list(patches),
                               "dependencies": [{"name": n, "range": r} for n, r in deps]}}


class DeclaredMixin:
    """A fake spec-guard 1.11 whose declaredScope answers from FAKE_DECLARED_OUT, per module."""

    def with_declared(self, answers: dict, version: str = "1.11"):
        root = Path(self.plugins.entries["spec-guard@m"][-1]["installPath"])
        doc = json.loads((root / "interface.json").read_text())
        doc["interface"] = version
        if version >= "1.11":
            doc["declaredScope"] = {"command": DECLARED_COMMAND}
        else:
            doc.pop("declaredScope", None)
        (root / "interface.json").write_text(json.dumps(doc))
        (root / "hooks" / "module_scope.py").write_text(FAKE_DECLARED)
        out = self.tmp / "declared-out.json"
        out.write_text(json.dumps(answers))
        self.args_log = self.tmp / "declared-args.jsonl"
        os.environ["FAKE_DECLARED_OUT"], os.environ["FAKE_DECLARED_ARGS"] = str(out), str(self.args_log)
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in ("FAKE_DECLARED_OUT", "FAKE_DECLARED_ARGS")])

    def switch(self, value: str | None):
        db = store.open_store(self.repo)
        with db.transaction(actor="test") as tx:
            cfg = dict(tx.get("config", "main") or {})
            if value is None:
                cfg.pop("declaredScope", None)
            else:
                cfg["declaredScope"] = value
            tx.put("config", "main", cfg, action="set")
        return db


class ReadTest(DeclaredMixin, ReviewCase):
    """Acceptance 3 at the read layer; Spec assumption 1 and 2."""

    def test_usable_and_inside(self):
        self.with_declared({"b": usable(configs=["tsconfig.base.json"], patches=["patches/x.patch"],
                                        deps=[("zod", "^3")])})
        d = declared.read(self.repo, "b")
        self.assertTrue(d.usable, d.reason)
        self.assertIsNone(d.reason)
        self.assertEqual(d.approved_commit, "abc123")
        self.assertEqual(d.dependencies, [{"name": "zod", "range": "^3"}])
        for path in ("config/app.json", "shared/a/b.ts", "tsconfig.base.json", "patches/x.patch"):
            self.assertTrue(d.inside(path), path)
        for path in ("package.json", "config/app.json.bak", "sharedx/a.ts", "config/other.json"):
            self.assertFalse(d.inside(path), path)
        call = json.loads(self.args_log.read_text().splitlines()[-1])
        self.assertEqual(call[:2], ["declared", "--project"])
        self.assertEqual(call[-2:], ["--module", "b"])

    def unusable(self, answers, version="1.11"):
        self.with_declared(answers, version)
        d = declared.read(self.repo, "b")
        self.assertFalse(d.usable)
        self.assertFalse(d.inside("config/app.json"))
        return d.reason

    def test_plan_not_approved(self):
        answer = usable()
        answer["out"].update(planApproved=False, approvedCommit=None)
        self.assertIn("Plan 批准后改过或未批准", self.unusable({"b": answer}))

    def test_no_section(self):
        self.assertIn("没有预先声明一节", self.unusable({"b": {"code": 0, "out": {"planApproved": True, "declared": False}}}))

    def test_malformed(self):
        self.assertIn("bad-path", self.unusable({"b": {"code": 4, "out": {"error": "bad-path"}}}))

    def test_old_spec_guard(self):
        self.assertIn("低于 1.11", self.unusable({"b": usable()}, version="1.10"))

    def test_command_fails(self):
        self.assertIn("没跑成", self.unusable({"b": {"code": 2, "out": {}}}))

    def test_switch(self):
        db = store.open_store(self.repo)
        self.assertFalse(declared.enabled(db))
        self.switch("on")
        self.assertTrue(declared.enabled(db))
        self.switch("off")
        self.assertFalse(declared.enabled(db))


class ConfigSetTest(DeclaredMixin, ReviewCase):
    """Acceptance 1."""

    def test_on_with_original(self):
        self.with_declared({})
        out = self.run_cli("config", "set", "--declared-scope", "on", "--original", "打开声明范围")
        self.assertEqual(out.returncode, 0, out.stderr)
        db = store.open_store(self.repo)
        self.assertEqual(store.get(db, "config", "main")["declaredScope"], "on")
        ev = [e for e in store.events(db) if e["data"].get("declaredScope") == "on"]
        self.assertEqual(ev[-1]["data"]["original"], "打开声明范围")
        self.assertNotIn("低于 1.11", out.stdout)

    def test_empty_original(self):
        out = self.run_cli("config", "set", "--declared-scope", "on", "--original", " ")
        self.assertEqual(out.returncode, 3)
        self.assertNotIn("declaredScope", store.get(store.open_store(self.repo), "config", "main"))

    def test_old_spec_guard_warns_but_writes(self):
        self.with_declared({}, version="1.10")
        out = self.run_cli("config", "set", "--declared-scope", "on", "--original", "打开")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("低于 1.11", out.stdout)
        self.assertEqual(store.get(store.open_store(self.repo), "config", "main")["declaredScope"], "on")

    def test_off(self):
        self.switch("on")
        out = self.run_cli("config", "set", "--declared-scope", "off", "--original", "关掉")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(store.get(store.open_store(self.repo), "config", "main")["declaredScope"], "off")


class ScopeCommandTest(DeclaredMixin, ReviewCase):
    """Acceptance 3: `module-crew scope` in a module worktree."""

    FILES = ("config/app.json", "shared/a/b.ts", "package.json")

    def scope(self, *extra):
        return self.run_cli("scope", *self.FILES, *extra, cwd=self.wt["b"])

    def test_inside_and_outside(self):
        self.with_declared({"b": usable()})
        self.switch("on")
        out = self.scope()
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = out.stdout.splitlines()
        self.assertIn("config/app.json：名单内，直接在本分支改", lines)
        self.assertIn("shared/a/b.ts：名单内，直接在本分支改", lines)
        self.assertIn("package.json：名单外，要改发【公共变更请求】", lines)
        call = json.loads(self.args_log.read_text().splitlines()[-1])
        self.assertEqual(Path(call[call.index("--project") + 1]).resolve(), self.wt["b"].resolve())   # assumption 3
        data = json.loads(self.scope("--json").stdout)
        self.assertEqual((data["switch"], data["usable"], data["module"]), ("on", True, "b"))
        self.assertEqual([f["inside"] for f in data["files"]], [True, True, False])

    def test_unusable_says_why_first(self):
        cases = [({"b": {"code": 0, "out": {"planApproved": False, "declared": True}}}, "1.11"),
                 ({"b": {"code": 0, "out": {"planApproved": True, "declared": False}}}, "1.11"),
                 ({"b": {"code": 4, "out": {"error": "unknown-line"}}}, "1.11"),
                 ({"b": usable()}, "1.10")]
        self.switch("on")
        for answers, version in cases:
            self.with_declared(answers, version)
            out = self.scope()
            self.assertEqual(out.returncode, 0, out.stderr)
            lines = out.stdout.splitlines()
            self.assertTrue(lines[0].startswith("声明不可用："), lines)
            self.assertEqual(sum("名单外" in x for x in lines[1:]), 3, lines)

    def test_switch_off(self):
        self.with_declared({"b": usable()})
        for value in (None, "off"):
            self.switch(value)
            lines = self.scope().stdout.splitlines()
            self.assertEqual(lines[0], "开关没开：公共文件一律发【公共变更请求】")
            self.assertEqual(sum("名单外" in x for x in lines[1:]), 3, lines)
        self.assertFalse(self.args_log.exists())      # off: spec-guard is not even asked

    def test_not_a_module_worktree(self):
        self.assertEqual(self.run_cli("scope", "x").returncode, 2)


class KickoffTest(DeclaredMixin, StartCase):
    """Acceptance 4: the 全局约束 line of the kickoff text."""

    OLD = "全局约束：不改公共文件（要改发【公共变更请求】）；被挡住发【等待其他会话】；发出前 module-crew protocol check。"
    NEW = ("全局约束：Plan「预先声明」名单内的公共文件直接在本分支改（`module-crew scope <文件>` 可查）；名单外的不改，"
           "要改发【公共变更请求】；被挡住发【等待其他会话】；发出前 module-crew protocol check。")

    def kickoff(self, module):
        from module_crew import start
        res = start.prepare(self.repo, [module], f"开 {module}", short="shop", max_modules=3)
        assert res.code == 0, res.lines
        return store.read_body(store.open_store(self.repo), res.prepared[0]["kickoff"]).splitlines()

    def test_on_and_off(self):
        lines = self.kickoff("b")
        self.assertIn(self.OLD, lines)
        self.switch("on")
        lines = self.kickoff("c")
        self.assertIn(self.NEW, lines)
        self.assertNotIn(self.OLD, lines)
        self.switch("off")
        self.assertIn(self.OLD, self.kickoff("d"))


def request(files, what="改配置", why="别的模块马上要用", stopped="否"):
    lines = "\n".join(files)
    return (f"【公共变更请求】\n结束：无\n来自：b\n文件：\n{lines}\n改什么：{what}\n为什么：{why}\n"
            f"是否完全停住：{stopped}\n")


class ChangeAddTest(DeclaredMixin, ReviewCase):
    """Acceptance 5."""

    def setUp(self):
        super().setUp()
        self.with_declared({"b": usable(configs=["package.json"]), "c": usable(paths=["shared/"])})
        self.db = self.switch("on")

    def add(self, files, sender="shop-b", rid=1):
        from module_crew import changes
        out = changes.add(self.db, request(files), sender, rid)
        self.assertEqual(out.code, 0, out.lines)
        return out, store.get(self.db, "request", str(out.number))

    def test_all_inside(self):
        out, rec = self.add(["config/app.json", "package.json"])
        self.assertIs(rec["declared"], True)
        self.assertEqual(rec["declaredCommit"], "abc123")
        self.assertIn("dependency", rec["hints"])                       # still recorded ...
        text = "\n".join(out.lines)
        self.assertIn(f"名单内：提前落地，不用问用户；用 change land C{out.number} --from-module", text)
        self.assertNotIn("要问用户", text.replace("不用问用户", ""))   # ... but no longer asks the user
        call = json.loads(self.args_log.read_text().splitlines()[-1])
        self.assertEqual(Path(call[call.index("--project") + 1]).resolve(), self.repo.resolve())   # assumption 3

    def test_mixed(self):
        out, rec = self.add(["config/app.json", "tsconfig.base.json"])
        self.assertIs(rec["declared"], False)
        self.assertNotIn("declaredCommit", rec)
        self.assertIn("名单内：config/app.json；有名单外的文件，整条照今天处理", out.lines)

    def test_conflict_with_another_request(self):
        self.add(["shared/x.ts"], sender="shop-c", rid=1)
        out, rec = self.add(["shared/x.ts"], sender="shop-b", rid=2)
        self.assertIs(rec["declared"], False)
        self.assertIn("要问用户", out.lines)
        self.assertTrue(any("名单内，但和别的请求改同一个文件" in x for x in out.lines), out.lines)

    def test_unusable(self):
        self.with_declared({"b": {"code": 4, "out": {"error": "bad-path"}}})
        out, rec = self.add(["config/app.json"])
        self.assertIs(rec["declared"], False)
        self.assertTrue(any(x.startswith("声明不可用：") and x.endswith("照今天处理") for x in out.lines), out.lines)

    def test_off_writes_nothing_new(self):
        self.switch("off")
        out, rec = self.add(["config/app.json"])
        self.assertNotIn("declared", rec)
        self.assertFalse(self.args_log.exists())
        self.assertEqual(out.lines[-1], "可由模块协调判断是否在已批准 Spec 范围内直接办")


if __name__ == "__main__":
    unittest.main()
