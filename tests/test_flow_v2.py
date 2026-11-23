"""crew-flow-v2: spec-guard flow v2 modules (interface 1.18 tier) -- review nodes, starting, approvers, display."""

import json
import unittest

from helpers import START_MAP, ReviewCase, git, review_text
from module_crew import flow, probe, review, store
from test_autonomy_tier import TierMixin
from test_declared_scope import DeclaredMixin
from test_takeover_approve import TakeoverMixin, takeover_row


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

    def test_hub_card_type_before_contract(self):
        from module_crew import protocol
        self.assertNotIn("技术方案", protocol.WAIT_KINDS)          # contract v2.9: Task 8 changes this
        self.set_flow({"b": "normal"})
        d = self.ok(self.design_review("b", node="Spec"))
        db = self.db()
        item = {"number": d, "node": "design", "round": 0, "reviews": [], "decisions": []}
        lines = review._card_fields(db, [item], [])
        self.assertEqual(lines[0], "类型：Spec")

    def test_release_next_step(self):
        self.assertIn("一起交审（节点 技术方案", flow.after_release("normal", "spec", "b"))
        self.assertEqual(flow.after_release("bug", "spec", "b"), "等开工通知")
        self.assertIsNone(flow.after_release(None, "spec", "b"))


if __name__ == "__main__":
    unittest.main()
