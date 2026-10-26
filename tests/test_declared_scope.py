"""crew-declared-scope: declared public files edited in the module branch, early landing, the final-review section,
modules with a dependency not opened together (see spec/crew-declared-scope.md)."""

import json
import os
import unittest
from pathlib import Path

from helpers import START_MAP, MergeCase, ReviewCase, StartCase, git

from module_crew import declared, protocol, review, store
from test_review_display import FinalTablesCase

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

    def test_cli_card_only_when_the_user_is_asked(self):
        for rid, files in ((7, ["config/app.json"]), (8, ["tsconfig.base.json"])):
            path = self.tmp / f"req{rid}.txt"
            path.write_text(request(files), encoding="utf-8")
            out = self.run_cli("change", "add", str(path), "--from", "shop-b", "--relay-id", str(rid))
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual("给用户看的正文" in out.stdout, rid == 8, out.stdout)

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


class LandBase(DeclaredMixin, ReviewCase):
    """Module b has committed a declared public file, shared/x.ts."""

    def setUp(self):
        super().setUp()
        self.with_declared({"b": usable()})
        self.db = self.switch("on")
        f = self.wt["b"] / "shared" / "x.ts"
        f.parent.mkdir(parents=True)
        f.write_text("export const X = 1\n", encoding="utf-8")
        git(self.wt["b"], "add", "-A")
        git(self.wt["b"], "commit", "-q", "-m", "b: shared x")
        self.module_commit = git(self.wt["b"], "rev-parse", "HEAD").strip()

    def add(self, files=("shared/x.ts",), rid=4700):
        from module_crew import changes
        out = changes.add(self.db, request(list(files)), "shop-b", rid)
        assert out.code == 0, out.lines
        return out.number

    def land(self, n, *extra):
        return self.run_cli("change", "land", str(n), "--from-module", *extra)



class LandFromModuleTest(LandBase):
    """Acceptance 6 and 7."""

    def test_lands_from_the_module_branch(self):
        from module_crew import protocol
        n = self.add()
        before = git(self.repo, "rev-parse", "main").strip()
        out = self.land(n)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(git(self.repo, "rev-list", "--count", f"{before}..main").strip(), "1")
        self.assertEqual(git(self.repo, "diff", "--name-only", before, "main").split(), ["shared/x.ts"])
        self.assertEqual(git(self.repo, "show", "main:shared/x.ts"), "export const X = 1\n")
        subject = git(self.repo, "log", "-1", "--format=%s", "main")
        self.assertIn(f"公共变更请求 C{n}（shop-b）提前落地", subject)
        rec = store.get(self.db, "request", str(n))
        self.assertEqual((rec["state"], rec["closedReason"]), ("closed", "landed"))
        self.assertEqual(rec["fromModule"], {"commit": self.module_commit})
        self.assertIs(rec["toldUser"], False)
        self.assertIn("提前落地，记入待汇总（change landed）", out.stdout)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        bodies = {}
        for line in out.stdout.splitlines():
            if line.startswith("发送 【协调通知】 → "):
                to = line.split("→ ")[1].split("，")[0]
                bodies[to] = Path(line.rsplit("正文文件：", 1)[1]).read_text(encoding="utf-8")
        self.assertEqual(set(bodies), {"shop-b", "shop-c"})
        self.assertTrue(bodies["shop-b"].startswith("回复：#4700\n"))
        self.assertFalse(bodies["shop-c"].startswith("回复："))
        for text in bodies.values():
            self.assertTrue(protocol.parse(text).ok, text)

    def refused(self, n, why):
        before = (git(self.repo, "rev-parse", "main"), git(self.repo, "status", "--porcelain"),
                  store.get(self.db, "request", str(n)))
        out = self.land(n)
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn(why, out.stdout + out.stderr)
        self.assertEqual(before, (git(self.repo, "rev-parse", "main"), git(self.repo, "status", "--porcelain"),
                                  store.get(self.db, "request", str(n))))

    def test_not_declared(self):
        n = self.add(["shared/x.ts", "tsconfig.base.json"])
        self.refused(n, "不是名单内的提前落地请求")

    def test_dirty_checkout(self):
        n = self.add()
        (self.repo / "stray.txt").write_text("x\n")
        self.refused(n, "集成 checkout 落地前就有改动")

    def test_file_missing_on_module_branch(self):
        n = self.add(["shared/x.ts", "shared/gone.ts"])
        self.refused(n, "模块分支上没有 shared/gone.ts")

    def test_declaration_gone_before_landing(self):
        n = self.add()
        self.with_declared({"b": {"code": 0, "out": {"planApproved": False, "declared": True}}})
        self.refused(n, "声明不可用")

    def test_scope_is_open_to_module_sessions(self):
        from module_crew import __main__ as cli
        self.assertIn(("scope", None), cli._ANY_SESSION)


class LandedTest(LandBase):
    """Acceptance 8."""

    def test_list_and_mark_told(self):
        self.assertEqual(self.run_cli("change", "landed").returncode, 3)
        n = self.add()
        self.assertEqual(self.land(n).returncode, 0)
        out = self.run_cli("change", "landed")
        self.assertEqual(out.returncode, 0, out.stderr)
        commit = store.get(self.db, "request", str(n))["commit"]
        self.assertIn(f"C{n} b：shared/x.ts 已提前进集成分支（{commit[:7]}，", out.stdout)
        self.assertIn("名单内、没问用户", out.stdout)
        data = json.loads(self.run_cli("change", "landed", "--json").stdout)
        self.assertEqual([(d["request"], d["module"], d["files"], d["commit"]) for d in data],
                         [(n, "b", ["shared/x.ts"], commit)])
        bad = self.run_cli("change", "landed", "--mark-told", str(n), "999")
        self.assertEqual(bad.returncode, 3)
        self.assertIs(store.get(self.db, "request", str(n))["toldUser"], False)
        ok = self.run_cli("change", "landed", "--mark-told", f"C{n}")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIs(store.get(self.db, "request", str(n))["toldUser"], True)
        self.assertEqual(self.run_cli("change", "landed").returncode, 3)
        self.assertEqual(self.run_cli("change", "landed", "--mark-told", str(n)).returncode, 3)   # already told


class FinalSectionTest(DeclaredMixin, FinalTablesCase):
    """Acceptance 9: b also changed shared/x.ts (landed early as C<n>) and package.json, both declared."""

    def finish(self, m, content=None, path=None):
        f = self.wt[m] / "shared" / "x.ts"
        f.parent.mkdir(exist_ok=True)
        f.write_text("export const X = 1\n", encoding="utf-8")
        return super().finish(m, content, path)

    def setUp(self):
        super().setUp()
        self.with_declared({"b": usable(paths=["shared/"], configs=["package.json"], deps=[("zod", "^3")])})
        with self.db.transaction(actor="test") as tx:
            self.early = tx.allocate_number()
            tx.put("request", str(self.early), {"state": "closed", "from": "shop-b", "files": ["shared/x.ts"],
                                                "closedReason": "landed", "commit": "1234567890abcdef",
                                                "fromModule": {"commit": "f" * 40}, "toldUser": True}, action="landed")

    def display(self):
        return next(i for i in review.batch(self.repo)["items"] if i["number"] == self.n)["display"]

    def points(self):
        [(n, path, text)] = review.for_hub(self.repo)
        return protocol.parse(text).fields["要点"].splitlines()

    def test_on(self):
        self.switch("on")
        t = self.display()
        self.assertEqual(t["declared"]["state"], "ok")
        files = {r["path"]: r for r in t["declared"]["files"]}
        self.assertEqual(set(files), {"shared/x.ts", "package.json"})
        self.assertEqual(files["shared/x.ts"]["landed"], {"request": self.early, "commit": "1234567"})
        self.assertNotIn("landed", files["package.json"])
        self.assertEqual({r["path"] for r in t["code"]}, {"src/a.py", "src/extra.py"})
        self.assertEqual(t["dependencies"], ["left-pad 1.3.0（package.json）（未声明）"])
        points = self.points()
        for words in ("声明内公共文件：", f"- 新增 shared/x.ts（+1 −0，已提前落地 C{self.early}（1234567））",
                      "- 新增 package.json（+5 −0）", "- left-pad 1.3.0（package.json）（未声明）"):
            self.assertIn(words, points)
        self.assertLess(points.index("代码："), points.index("声明内公共文件："))
        self.assertLess(points.index("声明内公共文件："), points.index("提交："))

    def test_declared_dependency_not_marked(self):
        self.with_declared({"b": usable(paths=["shared/"], configs=["package.json"], deps=[("left-pad", "1.3.0")])})
        self.switch("on")
        self.assertEqual(self.display()["dependencies"], ["left-pad 1.3.0（package.json）"])

    def test_nothing_declared_changed(self):
        self.with_declared({"b": usable(paths=["other/"])})
        self.switch("on")
        t = self.display()
        self.assertEqual((t["declared"]["state"], t["declared"]["files"]), ("ok", []))
        points = self.points()
        self.assertEqual(points[points.index("声明内公共文件：") + 1], "- 无")

    def test_unavailable(self):
        self.with_declared({"b": {"code": 4, "out": {"error": "bad-path"}}})
        self.switch("on")
        t = self.display()
        self.assertEqual(t["declared"]["state"], "unavailable")
        self.assertIn("bad-path", t["declared"]["reason"])
        self.assertIn("package.json", {r["path"] for r in t["code"]})
        self.assertEqual(t["dependencies"], ["left-pad 1.3.0（package.json）"])
        self.assertTrue(any(x.startswith("声明内公共文件：声明不可用：") and x.endswith("名单内外没有区分")
                            for x in self.points()))

    def test_off(self):
        for value in (None, "off"):
            self.switch(value)
            t = self.display()
            self.assertEqual(t["declared"]["state"], "off")
            self.assertIn("package.json", {r["path"] for r in t["code"]})
            self.assertFalse(any("声明内公共文件" in x for x in self.points()))


class DependencyTest(DeclaredMixin, StartCase):
    """Acceptance 10: b and c depend on a; a is reopened and has a module session in use."""

    def setUp(self):
        super().setUp()
        from module_crew import start
        assert start.prepare(self.repo, ["d"], "开 d", short="shop", max_modules=4).code == 0
        self.db = store.open_store(self.repo)
        with self.db.transaction(actor="test") as tx:
            tx.put("session", "shop-a-r2", {"role": "dev", "host": "claude-desktop", "status": "active", "module": "a",
                                           "worktree": str(self.tmp / "wa")}, action="registered")

    def plan(self):
        from module_crew import start
        return start.plan(self.repo)

    def validate(self, modules):
        from module_crew import start
        return start.validate(self.repo, modules, "开", None, None)[0]

    WHY = "和在用的 a 有依赖关系，等它合入再开"

    def test_on_holds_both_sides(self):
        self.switch("on")
        p = self.plan()
        self.assertEqual(p.modules, [])
        reasons = {r["module"]: r["reason"] for r in p.reasons}
        self.assertEqual((reasons["b"], reasons["c"]), (self.WHY, self.WHY))
        out = self.run_cli("start", "plan")
        self.assertIn(f"  b：{self.WHY}", out.stdout)
        before = (store.records(self.db, "session"), git(self.repo, "branch", "--list"))
        res = self.run_cli("start", "prepare", "b", "--original", "开 b")
        self.assertEqual(res.returncode, 3, res.stdout + res.stderr)
        self.assertIn("b 和在用的 a 有依赖关系", res.stdout + res.stderr)
        self.assertEqual(before, (store.records(self.db, "session"), git(self.repo, "branch", "--list")))

    def test_held_ones_listed_when_others_are_proposed(self):
        self.set_map(dict(START_MAP, startable={"modules": ["b", "c", "f"], "conflicts": []},
                          modules=START_MAP["modules"] + [{"id": "f", "responsibility": "独立页", "dependsOn": [],
                                                           "status": "ready"}]))
        self.switch("on")
        p = self.plan()
        self.assertEqual([m["id"] for m in p.modules], ["f"])
        out = self.run_cli("start", "plan").stdout
        self.assertIn("暂不提议：", out)
        self.assertIn(f"  b：{self.WHY}", out)

    def test_merged_upstream_no_longer_holds(self):
        with self.db.transaction(actor="test") as tx:
            n = tx.allocate_number()
            tx.put("item", str(n), {"state": "closed", "kind": "merge-approval", "module": "a", "closedReason": "merged"},
                   action="closed")
        self.switch("on")
        self.assertEqual([m["id"] for m in self.plan().modules], ["b", "c"])
        self.assertFalse(any("依赖关系" in r for r in self.validate(["b"])))

    def test_same_batch(self):
        with self.db.transaction(actor="test") as tx:
            tx.put("session", "shop-a-r2", dict(tx.get("session", "shop-a-r2"), status="retired"), action="retired")
        self.set_map(dict(START_MAP, startable={"modules": ["b", "e"], "conflicts": []}))
        self.switch("on")
        self.assertIn("同一次要开的 b 和 e 有依赖关系，不能同时开", self.validate(["b", "e"]))

    def test_off(self):
        for value in (None, "off"):
            self.switch(value)
            self.assertEqual([m["id"] for m in self.plan().modules], ["b", "c"])
            self.assertFalse(any("依赖关系" in r for r in self.validate(["b"])))


ROOT = Path(__file__).resolve().parent.parent


class DocsTest(unittest.TestCase):
    """Acceptance 11 and the README."""

    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_dev_skills(self):
        for rel in ("skills/crew-dev/SKILL.md", "codex-skills/crew-dev/SKILL.md"):
            text = self.read(rel)
            for words in ("declaredScope", "module-crew scope <文件>", "名单内", "直接在本分支改", "名单外",
                          "确实要提前进集成分支"):
                self.assertIn(words, text, rel)

    def test_coordinator_skills(self):
        for rel in ("skills/crew-coordinator/SKILL.md", "codex-skills/crew-coordinator/SKILL.md"):
            text = self.read(rel)
            for words in ("config set --declared-scope", "change land <编号> --from-module", "不问用户", "change landed",
                          "--mark-told", "声明内公共文件", "有依赖关系"):
                self.assertIn(words, text, rel)

    def test_readme(self):
        text = self.read("README.md")
        for words in ("declaredScope", "change land <编号> --from-module", "change landed", "module-crew scope",
                      "声明内公共文件", "--declared-scope"):
            self.assertIn(words, text)


if __name__ == "__main__":
    unittest.main()
