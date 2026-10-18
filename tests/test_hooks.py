import unittest

from helpers import MergeCase, RepoCase, git

from module_crew import hooks, store


class SilentTest(RepoCase):
    def test_unrelated_and_uninitialised(self):
        outside = self.tmp / "plain"
        outside.mkdir()
        for cwd in (outside, self.repo):
            with self.subTest(cwd=str(cwd)):
                self.assertIsNone(hooks.detect(cwd))
                self.assertIsNone(hooks.session_start(cwd, "startup"))
                self.assertIsNone(hooks.prompt_line(cwd))


class DetectTest(MergeCase):
    def test_module_worktree_and_subdir(self):
        (self.wt["b"] / "src").mkdir(exist_ok=True)
        for cwd in (self.wt["b"], self.wt["b"] / "src"):
            with self.subTest(cwd=str(cwd)):
                role = hooks.detect(cwd)
                self.assertEqual((role.kind, role.name, role.module), ("dev", "shop-b", "b"))

    def test_integration_checkout_is_coordinator(self):
        role = hooks.detect(self.repo)
        self.assertEqual((role.kind, role.name), ("coordinator", "shop-coord"))

    def test_unregistered_checkout_silent(self):
        from helpers import make_worktree
        other = make_worktree(self.repo, "other")
        self.assertIsNone(hooks.detect(other))

    def test_retired_session_silent(self):
        db = store.open_store(self.repo)
        with db.transaction(actor="t") as tx:
            tx.put("session", "shop-c", dict(tx.get("session", "shop-c"), status="retired"), action="retired")
        self.assertIsNone(hooks.detect(self.wt["c"]))


class RoleMarkerTest(MergeCase):
    def set_marker(self, checkout, text):
        from module_crew import role
        path = role.marker_path(checkout)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_marker_wins_over_registered_path(self):
        moved = self.tmp / "moved-b"
        git(self.repo, "worktree", "move", str(self.wt["b"]), str(moved))
        role = hooks.detect(moved)
        self.assertEqual((role.kind, role.name, role.module), ("dev", "shop-b", "b"))

    def test_coordinator_marker(self):
        role = hooks.detect(self.repo)
        self.assertEqual((role.kind, role.name), ("coordinator", "shop-coord"))

    def test_marker_without_session_is_silent(self):
        self.set_marker(self.wt["c"], "module x\n")
        self.assertIsNone(hooks.detect(self.wt["c"]))
        self.assertIsNone(hooks.session_start(self.wt["c"], "startup"))

    def test_no_or_invalid_marker_falls_back_to_path(self):
        from module_crew import role
        role.marker_path(self.wt["b"]).unlink()
        self.set_marker(self.wt["c"], "module c\nmodule b\n")
        for m in ("b", "c"):
            with self.subTest(m=m):
                found = hooks.detect(self.wt[m])
                self.assertEqual((found.kind, found.module), ("dev", m))


class TextTest(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def approve_spec_plan(self, m, base):
        from module_crew import review
        s = review.add(self.db, self.spec_review(m), f"shop-{m}", base).number
        p = review.add(self.db, self.plan_review(m), f"shop-{m}", base + 1).number
        assert review.approve(self.repo, [s, p], "批").code == 0
        # the module syncs the baseline as the start notice asks; the approved copies (with markers) win
        git(self.wt[m], "merge", "-q", "-X", "theirs", "--no-edit", "main")

    def stage(self, m):
        return hooks.session_start(self.wt[m], "startup")

    def test_dev_text_and_stages(self):
        text = self.stage("b")
        for words in ("模块 b", "shop-b", "shop-coord", "crew-dev", "【等待其他会话】", "写 Spec 与 Plan"):
            self.assertIn(words, text)
        self.approve_spec_plan("b", 100)
        self.assertIn("可以构建", self.stage("b"))
        from module_crew import merge
        self.approve_final("b", 200)
        self.assertIn("等协调会话合并", self.stage("b"))
        self.assertEqual(merge.run(self.repo, check_command="python3 -c pass").code, 0)
        self.assertIn("已合入集成分支", self.stage("b"))

    def test_returned_note(self):
        from module_crew import merge
        self.approve_spec_plan("b", 100)
        self.approve_final("b", 200)
        merge.run(self.repo, check_command=self.check_script(fail_if="src/b.py"))
        text = self.stage("b")
        self.assertIn("可以构建", text)
        self.assertIn("上次最终验收被退回：完整检查失败", text)

    def test_dev_open_tickets(self):
        from module_crew import inbox
        n = inbox.add(self.db, "【等待其他会话】\n结束：无\n在等谁：API\n等什么：数据\n", "shop-b", 9).number
        self.assertIn(f"#{n}", self.stage("b"))
        self.assertIn("无", self.stage("c").split("未关的等待单：")[1])

    def test_prompt_lines(self):
        line = hooks.prompt_line(self.wt["b"])
        self.assertEqual(line.count("\n"), 0)
        self.assertIn("b 的模块会话（shop-b）", line)
        coord = hooks.prompt_line(self.repo)
        self.assertEqual(coord.count("\n"), 0)
        self.assertIn("未关 事项", coord)

    def test_coordinator_text(self):
        self.approve_final("b", 1)
        text = hooks.session_start(self.repo, "resume")
        for words in ("协调会话", "shop-coord", "待合并 1", "module-crew status", "等待审批", "crew-coordinator"):
            self.assertIn(words, text)

    def test_compact_adds_check_first(self):
        for cwd in (self.wt["b"], self.repo):
            text = hooks.session_start(cwd, "compact")
            for words in ("先跑 `module-crew status`", "以状态库为准", "不按压缩前的记忆重做"):
                self.assertIn(words, text)
        self.assertNotIn("压缩", hooks.session_start(self.repo, "startup"))


import ast
import json
import subprocess
import time

from helpers import PLUGIN_ROOT


def run_hook(event, cwd, payload=None):
    data = json.dumps(payload if payload is not None else {"cwd": str(cwd)})
    start = time.perf_counter()
    r = subprocess.run([str(PLUGIN_ROOT / "bin" / "module-crew"), "hook", event], cwd=cwd, input=data,
                       capture_output=True, text=True)
    return r, time.perf_counter() - start


class HookCommandTest(MergeCase):
    def test_outputs_and_timing(self):
        r, secs = run_hook("session-start", self.wt["b"], {"cwd": str(self.wt["b"]), "source": "compact"})
        self.assertEqual(r.returncode, 0)
        doc = json.loads(r.stdout)
        self.assertEqual(doc["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("以状态库为准", doc["hookSpecificOutput"]["additionalContext"])
        self.assertLess(secs, 1.0)
        print(f"\n  hook session-start: {secs * 1000:.0f} ms", file=__import__("sys").stderr)
        r, secs = run_hook("prompt", self.repo)
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertLess(secs, 1.0)
        print(f"  hook prompt: {secs * 1000:.0f} ms", file=__import__("sys").stderr)

    def test_silent_outside_and_on_errors(self):
        outside = self.tmp / "plain"
        outside.mkdir()
        for cwd, payload in ((outside, None), (self.wt["b"], "not json at all")):
            data = payload if isinstance(payload, str) else json.dumps({"cwd": str(cwd)})
            r = subprocess.run([str(PLUGIN_ROOT / "bin" / "module-crew"), "hook", "session-start"], cwd=cwd,
                               input=data, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)
            if cwd == outside:
                self.assertEqual(r.stdout, "")
        (store.open_store(self.repo).path / "meta.json").write_text("{broken")
        r, _ = run_hook("session-start", self.wt["b"])
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_hooks_json_and_imports(self):
        doc = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text())
        for event, arg in (("SessionStart", "hook session-start"), ("UserPromptSubmit", "hook prompt")):
            cmd = doc["hooks"][event][0]["hooks"][0]["command"]
            self.assertIn(f"bin/module-crew", cmd)
            self.assertIn(arg, cmd)
            self.assertIn("|| true", cmd)
            self.assertTrue(cmd.rstrip().endswith("exit 0"))
        imported = set()
        for node in (n for f in ("hooks.py", "role.py")
                     for n in ast.walk(ast.parse((PLUGIN_ROOT / "module_crew" / f).read_text()))):
            if isinstance(node, ast.Import):
                imported |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported |= {node.module or ""} | {f"{node.module}.{a.name}" for a in node.names}
        for banned in ("subprocess", "module_crew.probe", "module_crew.start", "module_crew.review", "module_crew.merge"):
            self.assertNotIn(banned, imported)


class TakeoverTest(MergeCase):
    def test_takeover(self):
        db = store.open_store(self.repo)
        before = store.get(db, "session", "shop-b")
        r = self.run_cli("takeover", "shop-b", "--original", "让新会话接管 b")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("bridge_register", r.stdout)
        self.assertEqual(store.get(db, "session", "shop-b"), before)
        ev = store.events(db, key="shop-b", kind="session")[-1]
        self.assertEqual((ev["type"], ev["data"]["original"]), ("session.taken-over", "让新会话接管 b"))
        self.assertEqual(self.run_cli("takeover", "shop-x", "--original", "x").returncode, 3)
        self.assertEqual(self.run_cli("takeover", "shop-b", "--original", "  ").returncode, 3)
