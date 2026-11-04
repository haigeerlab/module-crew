"""crew-spec-ahead: open a module whose dependencies are not done yet, for its Spec and Plan only."""

import copy
import unittest

from pathlib import Path

from helpers import START_MAP, MergeCase, StartCase, git
from test_declared_scope import DeclaredMixin

from module_crew import protocol, review, start, store


def ahead_map(**status):
    """START_MAP with some statuses replaced (e depends on b and c and is not_ready by default)."""
    doc = copy.deepcopy(START_MAP)
    for m in doc["modules"]:
        m["status"] = status.get(m["id"], m["status"])
    return doc


class PrepareTest(StartCase):
    def dev(self, module):
        sessions = store.records(store.open_store(self.repo), "session")
        return next(v for v in sessions.values() if v.get("role") == "dev" and v.get("module") == module)

    def test_not_ready_module_opens_for_spec_and_plan(self):
        res = start.prepare(self.repo, ["e"], "先开 e 写 Spec", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        self.assertIn("e：提前开工（依赖 b、c 未完成），只写 Spec 与 Plan", res.lines)
        self.assertEqual(self.dev("e")["specAhead"], {"missing": ["b", "c"], "since": res.approval})
        item = store.get(store.open_store(self.repo), "item", str(res.approval))
        self.assertEqual(item["specAhead"], ["e"])

    def test_plain_module_carries_no_spec_ahead(self):
        res = start.prepare(self.repo, ["b"], "开 b", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        self.assertNotIn("specAhead", self.dev("b"))
        self.assertNotIn("specAhead", store.get(store.open_store(self.repo), "item", str(res.approval)))

    def test_missing_counts_only_unfinished_dependencies(self):
        self.set_map(ahead_map(b="done"))
        res = start.prepare(self.repo, ["e"], "先开 e", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(self.dev("e")["specAhead"]["missing"], ["c"])

    def assert_refused(self, modules, words, **kw):
        before = (git(self.repo, "branch", "--list"), git(self.repo, "worktree", "list"))
        res = start.prepare(self.repo, modules, "开吧", **{"short": "shop", **kw})
        self.assertEqual(res.code, 3, res.lines)
        self.assertIn(words, " ".join(res.lines))
        self.assertEqual((git(self.repo, "branch", "--list"), git(self.repo, "worktree", "list")), before)

    def test_blocked_module_still_refused(self):
        self.set_map(ahead_map(e="blocked"))
        self.assert_refused(["e"], "不在可开工列表")

    def test_other_blockers_unchanged(self):
        self.assert_refused(["b", "c", "e"], "空位", max_modules=2)
        (self.tmp / "repo-crew" / "e").mkdir(parents=True)
        self.assert_refused(["e"], "目录已存在")

    def test_branch_exists_or_serial_refused(self):
        git(self.repo, "branch", "e")
        self.assert_refused(["e"], "分支已存在")
        git(self.repo, "branch", "-D", "e")
        self.assertEqual(start.prepare(self.repo, ["d"], "开 d", short="shop").code, 0)      # the store exists
        db = store.open_store(self.repo)
        with db.transaction(actor="test") as tx:
            tx.put("config", "main", {**tx.get("config", "main"), "mode": "serial"}, action="set")
        self.assert_refused(["e"], "串行")

    def test_existing_session_refused(self):
        self.assertEqual(start.prepare(self.repo, ["e"], "开 e", short="shop").code, 0)
        self.assert_refused(["e"], "已有在用的模块会话")

    def test_plan_does_not_propose(self):
        picked = [m["id"] for m in start.plan(self.repo, 3).modules]
        self.assertNotIn("e", picked)


AHEAD_LINES = ["这是提前开工：依赖 b、c 还没合入。只写 Spec 与 Plan、照常交审；Plan 批准后不会马上收到开工通知，"
               "停在原地等，不要构建，也不用为此发【等待其他会话】。",
               "依赖合入后模块协调会问用户，再发开工通知；收到后先 module-crew sync 拿到依赖的代码再构建。"]


class KickoffTextTest(StartCase):
    """Acceptance 2: the kickoff carries the two limiting lines, otherwise unchanged."""

    def setUp(self):
        super().setUp()
        self.res = start.prepare(self.repo, ["e"], "先开 e", short="shop")
        assert self.res.code == 0, self.res.lines
        self.p = self.res.prepared[0]
        self.cfg = store.get(store.open_store(self.repo), "config", "main")

    def render(self, host="claude-desktop", ahead=None):
        info = {"id": "e", "responsibility": "汇总", "dependsOn": ["b", "c"]}
        return start.render_kickoff("e", info, self.p["worktree"], self.cfg, "shop-e", "shop-coord", self.res.approval,
                                    host, spec_ahead=ahead)

    def test_lines_and_place(self):
        text = self.p["kickoffPath"].read_text(encoding="utf-8")
        lines = text.splitlines()
        i = lines.index(AHEAD_LINES[0])
        self.assertTrue(lines[i - 1].startswith("这一步只做："))
        self.assertEqual(lines[i + 1:i + 3], [AHEAD_LINES[1], "收到开工类【协调通知】之前不要开始构建。"])
        self.assertEqual(text, self.render(ahead=["b", "c"]))
        self.assertEqual([x for x in lines if x not in AHEAD_LINES], self.render().splitlines())

    def test_codex_host(self):
        text = self.render("codex-desktop", ["b", "c"])
        self.assertTrue(all(x in text.splitlines() for x in AHEAD_LINES))
        self.assertIn("Codex", text)


class DeclaredScopeTest(DeclaredMixin, StartCase):
    """Decision 2: with declaredScope on, only spec-ahead modules skip the dependency holds."""

    def setUp(self):
        super().setUp()
        assert start.prepare(self.repo, ["d"], "开 d", short="shop", max_modules=4).code == 0   # the store exists

    def test_same_batch_with_dependency(self):
        for value in ("off", "on"):
            with self.subTest(declaredScope=value):
                self.switch(value)
                self.assertFalse([r for r in start.validate(self.repo, ["b", "e"], "开 b 和 e", None, None)[0]
                                  if "依赖关系" in r])
        res = start.prepare(self.repo, ["b", "e"], "开 b 和 e")
        self.assertEqual(res.code, 0, res.lines)

    def test_upstream_in_use_does_not_hold(self):
        self.switch("on")
        self.assertEqual(start.prepare(self.repo, ["b"], "开 b").code, 0)
        res = start.prepare(self.repo, ["e"], "先开 e")
        self.assertEqual(res.code, 0, res.lines)

    def test_plain_modules_still_held(self):
        self.set_map(dict(START_MAP, startable={"modules": ["b", "e"], "conflicts": []}))   # e startable: plain
        self.switch("on")
        self.assertIn("同一次要开的 b 和 e 有依赖关系，不能同时开",
                      start.validate(self.repo, ["b", "e"], "开", None, None)[0])


class AheadCase(MergeCase):
    """b and c opened as usual (ReviewCase), e (depends on b and c) opened ahead with a committed Spec and Plan."""

    def setUp(self):
        super().setUp()
        res = start.prepare(self.repo, ["e"], "先开 e 写 Spec")
        assert res.code == 0, res.lines
        wt = self.wt["e"] = Path(res.prepared[0]["worktree"])
        (wt / "spec").mkdir(exist_ok=True)
        (wt / "tasks" / "e").mkdir(parents=True, exist_ok=True)
        (wt / "spec" / "e.md").write_text("<!-- spec-guard: review pending -->\n# Spec: e\n", encoding="utf-8")
        (wt / "tasks" / "e" / "plan.md").write_text("<!-- spec-guard: review pending -->\n# Plan: e\n", encoding="utf-8")
        (wt / "tasks" / "e" / "todo.md").write_text("# Todo: e\n\n- [ ] Task 1\n", encoding="utf-8")
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", "e: spec and plan")
        self.db = store.open_store(self.repo)

    def merged(self, *modules):
        with self.db.transaction(actor="test") as tx:
            for m in modules:
                n = tx.allocate_number()
                tx.put("item", str(n), {"state": "closed", "kind": "merge-approval", "module": m,
                                        "closedReason": "merged"}, action="closed")

    def approve_e(self):
        s = review.add(self.db, self.spec_review("e"), "shop-e", 101).number
        p = review.add(self.db, self.plan_review("e"), "shop-e", 102).number
        res = review.approve(self.repo, [s, p], "e 的 Spec 和 Plan 批准")
        self.assertEqual(res.code, 0, res.lines)
        return res

    def notices(self, res):
        return [x for x in res.sends if x["kind"] == "coordination-notice"]

    def dev(self, module):
        return next(v for v in store.records(self.db, "session").values()
                    if v.get("role") == "dev" and v.get("module") == module and v.get("status") == "active")


class ApproveGateTest(AheadCase):
    """Acceptance 7, 8."""

    def test_dependencies_not_merged_no_start_notice(self):
        res = self.approve_e()
        self.assertEqual(self.notices(res), [])
        self.assertIn("user-reply", [x["kind"] for x in res.sends])
        self.assertIn("e：提前开工的模块，依赖 b、c 还没合入，没有发开工通知；依赖就位后 status 与 merge run 会提示，"
                      "问用户一次再运行 start kickoff e", res.lines)
        self.assertIsNone(self.dev("e").get("kickoff"))

    def test_dependencies_merged_start_notice_as_today(self):
        self.merged("b")
        self.set_map(ahead_map(c="done"))
        res = self.approve_e()
        self.assertEqual(len(self.notices(res)), 1)
        self.assertEqual(self.dev("e")["kickoff"], res.approval)

    def test_plain_module_unaffected(self):
        s = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        p = review.add(self.db, self.plan_review("b"), "shop-b", 2).number
        res = review.approve(self.repo, [s, p], "b 批准")
        self.assertEqual(len(self.notices(res)), 1)
        self.assertIsNone(self.dev("b").get("kickoff"))


class KickoffTest(AheadCase):
    """Acceptance 9 (refusals), 11, 12."""

    def unchanged(self, fn):
        before = (store.records(self.db, "item"), store.records(self.db, "session"))
        out = fn()
        self.assertEqual(out.code, 3, out.lines)
        self.assertEqual((store.records(self.db, "item"), store.records(self.db, "session")), before)
        return out

    def test_refused_before_dependencies_merge(self):
        self.approve_e()
        out = self.unchanged(lambda: start.kickoff(self.repo, "e", "可以开工"))
        self.assertIn("依赖 b、c 还没合入", "\n".join(out.lines))

    def test_refused_without_plan_or_original(self):
        self.merged("b", "c")
        self.assertIn("还没都批准", "\n".join(self.unchanged(lambda: start.kickoff(self.repo, "e", "开工")).lines))
        self.approve_e()
        self.unchanged(lambda: start.kickoff(self.repo, "e", "  "))
        self.unchanged(lambda: start.kickoff(self.repo, "b", "开工"))       # not opened ahead

    def test_kickoff(self):
        res = self.approve_e()
        self.merged("b", "c")
        out = start.kickoff(self.repo, "e", "可以开工")
        self.assertEqual(out.code, 0, out.lines)
        rec = next((int(k), v) for k, v in store.records(self.db, "item").items() if v["kind"] == "start-kickoff")
        self.assertEqual((rec[1]["module"], rec[1]["approval"], rec[1]["answer"]["original"]), ("e", res.approval, "可以开工"))
        self.assertEqual(self.dev("e")["kickoff"], rec[0])
        [send] = out.sends
        self.assertEqual(send["to"], "shop-e")
        msg = protocol.parse(store.read_body(self.db, send["body"]))
        self.assertFalse(msg.problems, msg.problems)
        self.assertIn(f"用户批准事项 C{res.approval}", msg.fields["依据"])
        self.assertIn(f"依赖 b、c 已合入，用户 C{rec[0]} 同意开工", msg.fields["依据"])
        self.assertEqual(msg.fields["要你做什么"], review.start_todo_today("e"))
        self.unchanged(lambda: start.kickoff(self.repo, "e", "再开一次"))

    def test_offload_conditions_not_met(self):
        from module_crew import offload
        self.approve_e()
        self.merged("b", "c")
        with self.db.transaction(actor="test") as tx:          # switch on; delegate is not installed, so not ready
            tx.put("config", "main", {**tx.get("config", "main"), offload.SWITCH: "on"}, action="set")
        out = self.unchanged(lambda: start.kickoff(self.repo, "e", "可以开工"))
        self.assertIn("offload decline e", "\n".join(out.lines))
        self.assertEqual(out.sends, [])

    def test_cli(self):
        self.approve_e()
        self.merged("b", "c")
        out = self.run_cli("start", "kickoff", "e", "--original", "可以开工")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("发送 【协调通知】 → shop-e", out.stdout)
        self.assertEqual(self.run_cli("start", "kickoff", "e", "--original", "x").returncode, 3)


class PlanRevisionTest(AheadCase):
    """S78: a Plan revision approved after the module opened ahead lets it start before its dependencies merge."""

    def unchanged(self, fn):
        before = (store.records(self.db, "item"), store.records(self.db, "session"))
        out = fn()
        self.assertEqual(out.code, 3, out.lines)
        self.assertEqual((store.records(self.db, "item"), store.records(self.db, "session")), before)
        return out

    def test_kickoff_before_dependencies_merge(self):
        res = self.approve_e()
        out = start.kickoff(self.repo, "e", "按修订开工", plan_revision=res.approval)
        self.assertEqual(out.code, 0, out.lines)
        rec = next((int(k), v) for k, v in store.records(self.db, "item").items() if v["kind"] == "start-kickoff")
        self.assertEqual((rec[1]["planRevision"], rec[1]["answer"]["original"]), (res.approval, "按修订开工"))
        self.assertEqual(self.dev("e")["kickoff"], rec[0])
        [send] = out.sends
        msg = protocol.parse(store.read_body(self.db, send["body"]))
        self.assertFalse(msg.problems, msg.problems)
        self.assertIn(f"依赖 b、c 未合入，按已批 Plan 修订 C{res.approval} 不等依赖，用户 C{rec[0]} 同意开工",
                      msg.fields["依据"])
        self.assertNotIn("e 提前开工", self.run_cli("status").stdout)

    def test_already_sent_records_only(self):
        res = self.approve_e()
        out = start.kickoff(self.repo, "e", "手工已发开工", plan_revision=res.approval, already_sent=True)
        self.assertEqual(out.code, 0, out.lines)
        self.assertEqual(out.sends, [])
        rec = next((int(k), v) for k, v in store.records(self.db, "item").items() if v["kind"] == "start-kickoff")
        self.assertTrue(rec[1]["alreadySent"])
        self.assertEqual(self.dev("e")["kickoff"], rec[0])
        self.assertNotIn("e 提前开工", self.run_cli("status").stdout)

    def test_refused_revisions(self):
        res = self.approve_e()
        since = self.dev("e")["specAhead"]["since"]
        for c in (since, 99999):                                 # not an approval; no such item
            self.assertIn("不是", "\n".join(self.unchanged(
                lambda: start.kickoff(self.repo, "e", "开工", plan_revision=c)).lines))
        s = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        p = review.add(self.db, self.plan_review("b"), "shop-b", 2).number
        other = review.approve(self.repo, [s, p], "b 批准").approval
        self.unchanged(lambda: start.kickoff(self.repo, "e", "开工", plan_revision=other))     # another module's Plan
        with self.db.transaction(actor="test") as tx:          # opened ahead after that approval
            name, v = start.spec_ahead_session(store.records(self.db, "session"), "e")
            tx.put("session", name, dict(v, specAhead=dict(v["specAhead"], since=res.approval + 1)), action="set")
        self.unchanged(lambda: start.kickoff(self.repo, "e", "开工", plan_revision=res.approval))

    def test_cli(self):
        res = self.approve_e()
        out = self.run_cli("start", "kickoff", "e", "--original", "x", "--plan-revision", "C1")
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        out = self.run_cli("start", "kickoff", "e", "--original", "按修订开工", "--plan-revision", f"C{res.approval}",
                           "--already-sent")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("发送", out.stdout)


class HintTest(AheadCase):
    """Acceptance 9 (hint), 10: status (text and --json) and merge run."""

    READY = "e 的依赖已就位，可以发开工通知：问用户一次，同意后 module-crew start kickoff e --original-file <原话文件>"

    def status(self):
        out = self.run_cli("status")
        return out.stdout

    def json_rows(self):
        import json
        return json.loads(self.run_cli("status", "--json").stdout)["store"]["specAhead"]

    def test_waiting_then_ready_then_gone(self):
        self.approve_e()
        self.assertIn("e 提前开工，等 b、c 合入", self.status())
        self.merged("b", "c")
        self.assertIn(self.READY, self.status())
        [row] = self.json_rows()
        self.assertEqual((row["module"], row["missing"], row["kickoffReady"], row["kickoff"]), ("e", [], True, None))
        self.assertEqual(start.kickoff(self.repo, "e", "可以开工").code, 0)
        self.assertNotIn("e 的依赖已就位", self.status())
        self.assertIsInstance(self.json_rows()[0]["kickoff"], int)

    def test_plan_not_approved_yet(self):
        self.merged("b", "c")
        self.assertIn("e 提前开工，依赖已就位，Plan 批准后直接发开工通知", self.status())

    def test_merge_run_says_ready(self):
        from module_crew import merge
        self.approve_e()
        self.merged("b")
        self.approve_final("c", 5200)
        res = merge.run(self.repo, check_command=self.check_script())
        self.assertEqual(res.code, 0, res.lines)
        self.assertIn(self.READY, res.lines)


class DocsTest(unittest.TestCase):
    """Acceptance 13 and the docs."""

    def read(self, rel):
        from helpers import PLUGIN_ROOT
        return (PLUGIN_ROOT / rel).read_text(encoding="utf-8")

    def test_coordinator_skills(self):
        texts = [self.read(f"{d}/crew-coordinator/SKILL.md") for d in ("skills", "codex-skills")]
        sections = [t.split("## 开工", 1)[1].split("\n## ", 1)[0] for t in texts]
        for section in sections:
            for words in ("提前开工", "用户原话点名", "依赖未就绪", "start kickoff", "问用户一次"):
                self.assertIn(words, section)
        para = [s[s.index("提前开工（"):].split("\n7.", 1)[0] for s in sections]
        self.assertEqual(para[0], para[1])

    def test_dev_skills(self):
        for d in ("skills", "codex-skills"):
            text = self.read(f"{d}/crew-dev/SKILL.md")
            section = text.split("## 交审节奏、返工与证据", 1)[1].split("\n## ", 1)[0]
            for words in ("提前开工", "Plan 批准后", "停住", "不发【等待其他会话】"):
                self.assertIn(words, section)

    def test_guide_commands_readme(self):
        self.assertIn("提前开工", self.read("docs/guide.md"))
        self.assertIn("start kickoff", self.read("docs/commands.md"))
        self.assertIn("提前开工", self.read("README.md"))
        self.assertIn("start kickoff", self.read("README.en.md"))


if __name__ == "__main__":
    unittest.main()
