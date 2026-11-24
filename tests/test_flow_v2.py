"""crew-flow-v2: spec-guard flow v2 modules (interface 1.18 tier) -- review nodes, starting, approvers, display."""

import json
import unittest

from helpers import START_MAP, MergeCase, ReviewCase, git, review_text
from module_crew import flow, probe, review, store
from test_autonomy_tier import TierMixin
from test_declared_scope import DeclaredMixin
from test_takeover_approve import TakeoverMixin, finding, report, takeover_row


class FlowMixin(TierMixin, TakeoverMixin, DeclaredMixin):
    """A fake spec-guard 1.18: every module in the fake /map carries its takeover row and, when given, a tier."""

    def with_flow(self, version: str = "1.18"):
        self.with_takeover(version=version, plugin_version="0.94.0")

    def set_flow(self, tiers: dict, rows: dict | None = None, steps: dict | None = None):
        doc = json.loads(json.dumps(START_MAP))
        for m in doc["modules"]:
            m.update((rows or {}).get(m["id"], takeover_row(source="default")))
            if m["id"] in tiers:
                m["tier"] = tiers[m["id"]]
            if m["id"] in (steps or {}):
                m["step"] = steps[m["id"]]
        self.set_map(doc)
        (self.repo / ".agent" / "config.json").touch()

    def db(self):
        return store.open_store(self.repo)

    def cli(self, *argv) -> tuple[int, str]:
        res = self.run_cli(*argv, cwd=self.repo)
        return res.returncode, res.stdout + res.stderr


class RecognizeTest(FlowMixin, ReviewCase):
    """Task 1, decision 1, acceptance 1."""

    def test_reads_five_kinds(self):
        self.with_flow()
        self.set_flow({"b": "normal", "c": "bug", "d": "important", "e": "small"})
        db = self.db()
        got = {m: flow.tier(db, self.repo, m) for m in ("a", "b", "c", "d", "e")}
        self.assertEqual(got, {"a": None, "b": "normal", "c": "bug", "d": "important", "e": "small"})
        self.assertTrue(flow.is_v2(got["c"]))
        self.assertFalse(flow.is_v2(got["a"]))
        self.assertEqual([m for m, t in got.items() if flow.full_docs(t)], ["b", "d"])

    def test_null_and_unknown_tier(self):
        self.assertIsNone(flow.tier_of({"tier": None}))
        self.assertIsNone(flow.tier_of({}))
        self.assertEqual(flow.tier_of({"tier": "huge"}), "normal")

    def test_older_spec_guard_is_old_flow(self):
        self.with_flow(version="1.17")
        self.set_flow({})                  # 1.17 has no tier field at all
        db = self.db()
        self.assertIsNone(flow.tier(db, self.repo, "b"))

    def test_no_takeover_interface_is_old_flow(self):
        db = self.db()                     # the plain fake spec-guard 1.7: /map is read but no takeover
        self.assertIsNone(flow.tier(db, self.repo, "b"))

    def test_step_words_and_probe_summary(self):
        self.assertEqual(flow.step_word({"step": "design"}), "写技术方案")
        self.assertEqual(flow.step_word({"step": "regression"}), "写回归")
        self.assertIsNone(flow.step_word({"step": "plan"}))
        doc = {"modules": [{"id": "a", "status": "done"}, {"id": "b", "tier": "normal", "status": "in_progress"}]}
        self.assertEqual(probe.summarize_map(doc)["flowV2"], {"b": "normal"})
        self.assertNotIn("flowV2", probe.summarize_map({"modules": [{"id": "a", "status": "done"}]}))


class FlowReviewMixin(FlowMixin):
    """Module worktrees b, c also hold a committed design and regression document."""

    def write_design(self, m: str):
        for name in ("design.md", "regression.md"):
            (self.wt[m] / "tasks" / m / name).write_text(f"# {name}: {m}\n", encoding="utf-8")
        git(self.wt[m], "add", "-A")
        git(self.wt[m], "commit", "-q", "-m", f"{m}: design")

    def design_review(self, m: str, node: str = "技术方案", files=("design.md", "regression.md")) -> str:
        return review_text(m, node, [(f"tasks/{m}/{name}", self.wt[m] / "tasks" / m / name) for name in files])

    def add(self, text: str, m: str = "b", rid: int = 1):
        return review.add(self.db(), text, f"shop-{m}", rid)


class NodeTest(FlowReviewMixin, ReviewCase):
    """Task 2, decisions 2, 3, 9, acceptance 2-4 (refusals)."""

    def setUp(self):
        super().setUp()
        self.with_flow()
        for m in ("b", "c"):
            self.write_design(m)

    def test_full_docs_module_refuses_plan_takes_design_by_transition(self):
        self.set_flow({"b": "normal"})
        out = self.add(self.plan_review("b"))
        self.assertEqual(out.code, 3)
        self.assertIn("新流程模块的 Plan 不交审", "\n".join(out.lines))
        out = self.add(self.spec_review("b"), rid=2)
        self.assertEqual(out.code, 0, out.lines)
        self.assertEqual(store.get(self.db(), "item", str(out.number))["node"], "spec")
        out = self.add(self.design_review("b", node="Spec"), rid=3)      # decision 9: before contract v2.10
        self.assertEqual(out.code, 0, out.lines)
        self.assertEqual(store.get(self.db(), "item", str(out.number))["node"], "design")

    def test_design_must_list_both_documents(self):
        self.set_flow({"b": "important"})
        out = self.add(self.design_review("b", node="Spec", files=("design.md",)))
        self.assertEqual(out.code, 3)            # not the transition shape: a Spec review missing spec/b.md
        self.assertIn("spec/b.md", "\n".join(out.lines))

    def test_one_doc_module_refuses_design_and_plan(self):
        self.set_flow({"b": "bug", "c": "small"})
        self.assertEqual(self.add(self.plan_review("b")).code, 3)
        out = self.add(self.plan_review("c", ), m="c", rid=2)
        self.assertIn("新流程模块的 Plan 不交审", "\n".join(out.lines))
        self.assertEqual(self.add(self.spec_review("b"), rid=3).code, 0)
        out = self.add(self.design_review("b", node="Spec"), rid=4)   # not a full-docs module: stays a Spec review
        self.assertEqual(out.code, 3)
        self.assertEqual(flow.refuse("bug", "design", "b"), "bug／小改动只写一份文档（spec/b.md），没有技术方案")

    def test_old_module_unchanged(self):
        self.set_flow({})
        self.assertEqual(self.add(self.plan_review("b")).code, 0)
        self.assertEqual(self.add(self.design_review("c", node="Spec"), m="c", rid=2).code, 3)
        self.assertIn("「技术方案」节点只用于", flow.refuse(None, "design", "c"))
        self.assertIsNone(flow.refuse(None, "plan", "c"))

    def test_refusal_table(self):
        table = {None: {"spec": 0, "interface": 0, "plan": 0, "design": 1, "final": 0},
                 "normal": {"spec": 0, "interface": 0, "plan": 1, "design": 0, "final": 0},
                 "important": {"spec": 0, "interface": 0, "plan": 1, "design": 0, "final": 0},
                 "bug": {"spec": 0, "interface": 0, "plan": 1, "design": 1, "final": 0},
                 "small": {"spec": 0, "interface": 0, "plan": 1, "design": 1, "final": 0}}
        for t, row in table.items():
            for node, refused in row.items():
                self.assertEqual(bool(flow.refuse(t, node, "m")), bool(refused), (t, node))

    def test_reviewer_scope_takes_design(self):
        from module_crew import sources
        self.assertEqual(sources.parse_scope("b", "design")["nodes"], ["design"])


def notices(db, res):
    from module_crew import protocol
    return [protocol.parse(store.read_body(db, x["body"])) for x in res.sends if x["kind"] == "coordination-notice"]


class StartTest(FlowReviewMixin, ReviewCase):
    """Task 3, decisions 4, 5, acceptance 2-4 (approvals)."""

    def setUp(self):
        super().setUp()
        self.with_flow()
        for m in ("b", "c"):
            self.write_design(m)

    def ok(self, text, m="b", rid=1):
        out = self.add(text, m=m, rid=rid)
        self.assertEqual(out.code, 0, out.lines)
        return out.number

    def test_full_docs_module_starts_after_design(self):
        self.set_flow({"b": "normal"})
        s = self.ok(self.spec_review("b"))
        first = review.approve(self.repo, [s], "b 的需求批准")
        self.assertEqual(first.code, 0, first.lines)
        self.assertEqual(notices(self.db(), first), [])
        d = self.ok(self.design_review("b", node="Spec"), rid=2)
        res = review.approve(self.repo, [d], "b 的技术方案批准")
        self.assertEqual(res.code, 0, res.lines)
        [msg] = notices(self.db(), res)
        self.assertTrue(msg.ok, msg.problems)
        self.assertIn("不交审，提交后按它构建", msg.fields["要你做什么"])
        self.assertIn(f"C{res.approval}（b 的 技术方案", msg.fields["依据"])
        self.assertIn(f"Spec 以前批准于 C{first.approval}", msg.fields["依据"])
        for name in ("design.md", "regression.md"):       # acceptance 4: the approved documents land
            self.assertTrue((self.repo / "tasks" / "b" / name).exists())

    def test_one_doc_module_starts_after_spec(self):
        self.set_flow({"c": "bug"})
        s = self.ok(self.spec_review("c"), m="c")
        res = review.approve(self.repo, [s], "c 的需求批准")
        [msg] = notices(self.db(), res)
        self.assertIn("tasks/c/plan.md（只留任务与检查点）", msg.fields["要你做什么"])

    def test_design_revision_does_not_start_again(self):
        self.set_flow({"b": "important"})
        s = self.ok(self.spec_review("b"))
        d = self.ok(self.design_review("b", node="Spec"), rid=2)
        self.assertEqual(len(notices(self.db(), review.approve(self.repo, [s, d], "都批准"))), 1)
        s2 = self.ok(self.spec_review("b"), rid=3)
        res = review.approve(self.repo, [s2], "需求修订批准")
        self.assertEqual(notices(self.db(), res), [])
        self.assertIn("这次批的不是开工所需的最后一份", "\n".join(res.lines))

    def test_old_module_start_notice_unchanged(self):
        self.set_flow({})
        s = self.ok(self.spec_review("b"))
        p = self.ok(self.plan_review("b"), rid=2)
        [msg] = notices(self.db(), review.approve(self.repo, [s, p], "都批准"))
        self.assertEqual(msg.fields["要你做什么"], review.start_todo_today("b"))

    def test_combined_project_keeps_flow_v2_separate(self):
        from module_crew import start
        self.set_flow({"b": "normal"})
        self.assertTrue(start.flow_v2(self.repo, "b"))
        self.assertFalse(start.flow_v2(self.repo, "c"))

    def test_hub_card_type(self):
        from module_crew import protocol
        self.assertIn("技术方案", protocol.WAIT_KINDS)             # contract v2.10 (Task 8)
        self.set_flow({"b": "normal"})
        d = self.ok(self.design_review("b"))
        db = self.db()
        item = {"number": d, "node": "design", "round": 0, "reviews": [], "decisions": []}
        lines = review._card_fields(db, [item], [])
        self.assertEqual(lines[0], "类型：技术方案")

    def test_contract_node_and_transition_hint(self):
        from module_crew import protocol
        self.set_flow({"b": "normal"})
        msg = protocol.parse(self.design_review("b"))
        self.assertEqual(msg.contract()["submission"]["node"], "design")
        out = self.add(self.design_review("b"), rid=7)
        self.assertEqual(out.code, 0, out.lines)
        self.assertNotIn("过渡写法", "\n".join(out.lines))
        out = self.add(self.design_review("b", node="Spec"), rid=8)
        self.assertIn("请模块改写「节点：技术方案」", "\n".join(out.lines))
        bad = protocol.parse(self.design_review("b", files=("design.md",)))
        self.assertIn("missing-design-file:regression.md", bad.problems)

    def test_release_next_step(self):
        self.assertTrue(flow.after_release("normal", "spec", "b").endswith("一起交审（节点 技术方案）"))
        self.assertEqual(flow.after_release("bug", "spec", "b"), "等开工通知")
        self.assertIsNone(flow.after_release(None, "spec", "b"))


def flow_row(design=None, approval=None, **kw):
    row = takeover_row(**kw)
    if design is not None:
        row["takeover"]["design"] = design
    if approval is not None:
        row["designApproval"] = {"status": approval}
    return row


class ApproverTest(FlowReviewMixin, ReviewCase):
    """Task 4, decision 6, acceptance 5."""

    def setUp(self):
        super().setUp()
        self.with_flow()
        for m in ("b", "c"):
            self.write_design(m)

    def who(self, m, node):
        from module_crew import takeover
        return takeover.approval(self.db(), self.repo, m, node)

    def test_requirement_always_user(self):
        from module_crew import takeover
        self.set_flow({"b": "normal"}, {"b": flow_row(spec="codex", plan="codex")})
        self.assertEqual(self.who("b", "spec"), ("human", takeover.FLOW_SPEC))
        out = self.add(self.spec_review("b"))
        self.assertEqual(out.code, 0, out.lines)
        self.assertNotIn("Codex 放行", "\n".join(out.lines))
        self.assertIn("Plan 不交审（旧档位的 Plan 一项已不生效）", takeover.line(takeover.module(self.db(), self.repo, "b")))

    def test_design_reviewer_human_and_upstream_missing(self):
        from module_crew import takeover
        self.set_flow({"b": "normal", "c": "normal"}, {"b": flow_row(design="reviewer"), "c": flow_row(design="human")})
        self.assertEqual(self.who("b", "design"), ("codex", None))
        self.assertEqual(self.who("c", "design"), ("human", None))
        out = self.add(self.design_review("b", node="Spec"))
        self.assertIn("交第二审查者：下一步 review codex", "\n".join(out.lines))
        self.set_flow({"b": "normal"})                       # spec-guard without the design item yet
        self.assertEqual(self.who("b", "design"), ("human", takeover.DESIGN_UPSTREAM))
        self.assertIn("因上游未发版而人批", takeover.line(takeover.module(self.db(), self.repo, "b")))

    def test_important_design_always_user(self):
        from module_crew import takeover
        self.set_flow({"b": "important"}, {"b": flow_row(design="reviewer", approval="not-required")})
        self.assertEqual(self.who("b", "design"), ("human", takeover.DESIGN_IMPORTANT))

    def test_skip_lands_and_starts(self):
        self.set_flow({"b": "normal"}, {"b": flow_row(design="reviewer", approval="not-required")})
        s = self.add(self.spec_review("b")).number
        self.assertEqual(review.approve(self.repo, [s], "b 的需求批准").code, 0)
        out = self.add(self.design_review("b", node="Spec"), rid=2)
        self.assertEqual(out.code, 0, out.lines)
        text = "\n".join(out.lines)
        self.assertIn("免审放行 C", text)
        [msg] = notices(self.db(), out)
        self.assertIn("免审放行事项", msg.fields["依据"])
        self.assertTrue((self.repo / "tasks" / "b" / "design.md").exists())

    def test_old_module_line_unchanged(self):
        from module_crew import takeover
        self.set_flow({}, {"b": flow_row(plan="codex")})
        items = takeover.module(self.db(), self.repo, "b")
        self.assertEqual(takeover.line(items), "批准方式：Spec 人批、Plan Codex 放行、合并 人合")
        self.assertEqual(self.who("b", "design"), ("human", None))


class SecondReviewerTest(FlowReviewMixin, ReviewCase):
    """Task 5, decision 7, acceptance 6."""

    def setUp(self):
        super().setUp()
        self.with_flow()
        self.write_design("b")
        self.set_flow({"b": "normal"}, {"b": flow_row(design="reviewer")})
        s = self.add(self.spec_review("b")).number
        assert review.approve(self.repo, [s], "b 的需求批准").code == 0
        self.n = self.add(self.design_review("b", node="Spec"), rid=2).number

    def files(self):
        import hashlib, subprocess
        rec = store.get(self.db(), "item", str(self.n))
        return {f["path"]: hashlib.sha256(subprocess.run(["git", "-C", str(self.wt["b"]), "show",
                                                          f"{rec['commit']}:{f['path']}"], capture_output=True,
                                                         check=True).stdout).hexdigest() for f in rec["files"]}

    def note(self, doc):
        path = self.tmp / f"report-{len(list(self.tmp.glob('report-*')))}.json"
        path.write_text(json.dumps(doc))
        return self.cli("review", "codex-note", f"C{self.n}", "--report", str(path))

    def design_report(self, findings=(), same=False, **kw):
        doc = report(self.files(), findings, backend="claude-code", **kw)
        doc["reviewer"] = {"vendor": "anthropic" if same else "openai", "backend": "claude-code" if same else "codex",
                           "same_vendor": same, "selection": "same-vendor" if same else "other-vendor"}
        doc["criteria"] = "design-v1"
        return doc

    def test_command(self):
        code, out = self.cli("review", "codex", f"C{self.n}")
        self.assertEqual(code, 0, out)
        self.assertIn("/delegate:review --profile design --backend auto --author-host claude-code --repo", out)
        self.assertIn("--paths tasks/b/design.md --paths tasks/b/regression.md --spec spec/b.md", out)
        self.assertNotIn("--model", out)
        self.assertNotIn("--effort", out)
        self.assertNotIn("--previous-report", out)

    def test_two_rounds_then_user(self):
        code, out = self.note(self.design_report([finding("迁移没写回滚", file="tasks/b/design.md")]))
        self.assertEqual(code, 0, out)
        self.assertIn("返工第 1 轮", out)
        again = self.cli("review", "codex", f"C{self.n}")[1]
        self.assertIn("--previous-report", again)
        code, out = self.note(self.design_report(recheck={"items": [{"status": "unresolved",
                                                                       "finding": {"title": "迁移没写回滚"}}]}))
        self.assertEqual(code, 5, out)
        self.assertIn("两轮都有阻断", out)

    def test_suggestion_only_passes_and_starts(self):
        code, out = self.note(self.design_report([finding("命名", severity="suggestion")], same=True))
        self.assertEqual(code, 0, out)
        self.assertIn("第二审查者（同厂商审查） 没有阻断意见", out)
        rec = store.get(self.db(), "item", str(self.n))
        self.assertEqual(rec["closedReason"], "codex-approved")

    def test_no_reviewer_releases_unreviewed(self):
        doc = {"schema_version": 1, "execution_status": "conditions_missing", "backend": None,
               "diagnostics": ["no_reviewer_available"], "reviewer": {"vendor": None, "backend": None,
                                                                       "same_vendor": None, "selection": "none"}}
        code, out = self.note(doc)
        self.assertEqual(code, 0, out)
        self.assertIn("未审：本机没有可用的第二审查者，由回归测试兜底", out)
        self.assertTrue((self.repo / "tasks" / "b" / "design.md").exists())

    def test_author_host(self):
        from module_crew import takeover
        self.assertEqual(takeover.author_host({"host": "codex-desktop"}), "codex")
        self.assertEqual(takeover.author_host({"host": "claude-desktop"}), "claude-code")


FAKE_VIEW = "import os, sys\nsys.stdout.write(os.environ.get('FAKE_CASES', '{\"cases\": []}'))\n"


class FinalByRegressionTest(FlowReviewMixin, MergeCase):
    """Task 6, decision 11, acceptance 7."""

    def setUp(self):
        super().setUp()
        self.with_flow()
        self.set_flow({"b": "normal", "c": "bug"})

    def final(self, m, evidence):
        self.k = getattr(self, "k", 0) + 1
        text = self.finish(m, content=f"VALUE = {self.k}\n")
        return text.replace("验收标准与证据：\n1：test_value 通过\n2：无\n", "验收结果：\n" + evidence)

    def with_view(self, cases):
        import os
        from pathlib import Path
        root = Path(self.plugins.entries["spec-guard@m"][-1]["installPath"])
        doc = json.loads((root / "interface.json").read_text())
        doc["regressionView"] = {"command": ["python3", "-B", "hooks/regression_view.py", "--json", "--project",
                                             "<project-root>", "--module", "<module-id>"]}
        (root / "interface.json").write_text(json.dumps(doc))
        (root / "hooks" / "regression_view.py").write_text(FAKE_VIEW)
        os.environ["FAKE_CASES"] = json.dumps({"cases": cases})
        self.addCleanup(lambda: os.environ.pop("FAKE_CASES", None))

    def test_needs_case_lines(self):
        out = self.add(self.final("b", "1：test_value 通过\n"))
        self.assertEqual(out.code, 3)
        self.assertIn("每行以用例编号开头", "\n".join(out.lines))
        self.assertEqual(self.add(self.final("b", "R1：test_value 通过\n"), rid=2).code, 0)

    def test_lists_missing_cases_manual_excluded(self):
        self.with_view([{"id": "R1", "method": "command"}, {"id": "R2", "method": "manual"},
                        {"id": "R3", "method": "script"}])
        out = self.add(self.final("c", "R1：通过\n"), m="c")
        self.assertEqual(out.code, 3)
        self.assertIn("缺这些回归用例：R3", "\n".join(out.lines))
        self.assertEqual(self.add(self.final("c", "- R1：通过\nR3：通过\n"), m="c", rid=2).code, 0)

    def test_old_module_unchanged(self):
        self.set_flow({})
        self.assertEqual(self.add(self.finish("b")).code, 0)

    def test_case_ids(self):
        self.assertEqual(flow.case_ids(["验收结果：", "R1：过", "- R12: 过", "S1：无"]), ["R1", "R12"])


class DisplayTest(FlowMixin, ReviewCase):
    """Task 7, decisions 4, 10, acceptance 9."""

    def items(self, tier, *rows):
        out = {}
        for k, (kind, node, state) in enumerate(rows, 1):
            if kind == "review":
                out[str(k)] = {"kind": "review", "module": "b", "node": node, "state": state, "tier": tier}
            else:
                out[str(k)] = {"kind": kind, "reviews": [node]}
        return out

    def test_hook_stage_by_tier(self):
        from module_crew import hooks
        self.assertIn("写需求文档 spec/b.md", hooks._stage(self.items("normal", ("review", "spec", "open")), "b"))
        spec_ok = [("review", "spec", "closed"), ("review-approval", 1, None)]
        self.assertIn("写技术方案与回归", hooks._stage(self.items("normal", *spec_ok), "b"))
        waiting = self.items("normal", *spec_ok, ("review", "design", "open"))
        self.assertIn("技术方案已交审（交审事项 C3）", hooks._stage(waiting, "b"))
        released = self.items("normal", *spec_ok, ("review", "design", "closed"), ("codex-approval", 3, None))
        self.assertIn("先写 Plan、todo（只留任务，不交审）", hooks._stage(released, "b"))
        self.assertIn("先写 Plan、todo", hooks._stage(self.items("bug", *spec_ok), "b"))

    def test_old_module_stage_unchanged(self):
        from module_crew import hooks
        items = {"1": {"kind": "review", "module": "b", "node": "spec", "state": "closed"},
                 "2": {"kind": "review", "module": "b", "node": "plan", "state": "closed"},
                 "3": {"kind": "review-approval", "reviews": [1, 2]}}
        self.assertEqual(hooks._stage(items, "b"), hooks.STAGE_BUILD)
        self.assertEqual(hooks._stage({}, "b"), hooks.STAGE_WRITE)

    def test_kickoff_first_step(self):
        from module_crew import start
        self.assertFalse(start.flow_available(self.repo))          # the plain fake spec-guard 1.7
        self.with_flow()
        self.assertTrue(start.flow_available(self.repo))
        self.assertIn("节点 技术方案", start._first_step("b", "separate", True))
        self.assertNotIn("技术方案", start._first_step("b", "separate"))

    def test_start_plan_step_words(self):
        from module_crew import start
        self.with_flow()
        self.set_flow({"b": "normal"}, steps={"b": "design"})
        db = self.db()
        m = dict(flow.row_of(json.loads(self.map_file.read_text()), "b"), status="in_progress")
        self.assertEqual(start._why_not(m, {}, set(), set(), 3, db), "spec-guard 的当前模块（写技术方案），不在可开工列表")


if __name__ == "__main__":
    unittest.main()
