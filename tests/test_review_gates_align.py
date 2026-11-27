"""crew-review-gates-align: review gates follow spec-guard 1.27 (sg-review-rules) -- a flow v2 requirement is reviewed
once before the user confirms it, and a design with no second reviewer goes to the user."""

from __future__ import annotations

import os

from helpers import ReviewCase, review_text
from module_crew import flow, probe, review, store
from test_flow_v2 import FlowReviewMixin
from test_takeover_approve import takeover_row


def gate_row(status=None, records=None, **kw):
    """A /map module row with a requirementReview object (status None leaves the field out: spec-guard < 1.27)."""
    row = takeover_row(**kw)
    if status == "null":
        row["requirementReview"] = None
    elif status is not None:
        row["requirementReview"] = {"required": status != "not-required", "status": status, "records": records or []}
    return row


class GateMixin(FlowReviewMixin):
    def setUp(self):
        super().setUp()
        self.with_flow(version="1.27")

    def gate(self, tier: str | None, status=None, records=None, m: str = "b"):
        self.set_flow({m: tier} if tier else {}, {m: gate_row(status, records)})

    def interface_review(self, m: str) -> str:
        return review_text(m, "接口提案", [(f"spec/{m}.md", self.wt[m] / "spec" / f"{m}.md")])

    def items(self) -> int:
        return len([k for k, v in store.records(self.db(), "item").items() if v.get("kind") == "review"])


class RequirementGateTest(GateMixin, ReviewCase):
    """Task 1, decisions 3, 4; AC1-AC3."""

    def test_missing_is_refused_with_three_ways(self):
        for node, text in (("spec", self.spec_review), ("interface", self.interface_review)):
            with self.subTest(node=node):
                self.gate("normal", "missing")
                before = self.items()
                out = self.add(text("b"), rid=10 + len(node))
                lines = "\n".join(out.lines)
                self.assertEqual(out.code, 3, lines)
                self.assertEqual(self.items(), before)
                self.assertIn("还没有审查记录（spec-guard requirementReview: missing）", lines)
                for word in ("--state codex-reviewed --review", "--state host-reviewed --blocking",
                             "--state no-reviewer --reason", "重新发【交审】"):
                    self.assertIn(word, lines)

    def test_other_states_are_taken_as_today(self):
        for status in ("reviewed", "not-required", "null", None):
            with self.subTest(status=status):
                self.gate("important", status, [{"reviewer": "codex", "blocking": 1}] if status == "reviewed" else None)
                out = self.add(self.spec_review("b"), rid=hash(str(status)) % 1000 + 100)
                self.assertEqual(out.code, 0, out.lines)
                self.assertNotIn("需求审查状态", "\n".join(out.lines))

    def test_design_node_is_not_the_requirement_gate(self):
        self.gate("normal", "missing")
        self.write_design("b")
        out = self.add(self.design_review("b"), rid=5)
        self.assertEqual(out.code, 0, out.lines)        # the design node is not the requirement gate

    def test_unreadable_map_is_taken_with_a_hint(self):
        self.gate("normal", "missing")
        got = flow.requirement_review(self.wt["b"], "b")
        self.assertEqual(got["status"], "missing")
        os.environ["FAKE_MAP_MODE"] = "garbage"
        os.environ.pop("FAKE_MAP_FILE", None)
        self.assertIsInstance(flow.requirement_review(self.wt["b"], "b"), str)
        reasons, hints = flow.requirement_gate(self.wt["b"], "b")
        self.assertEqual(reasons, [])
        self.assertIn("读不到 spec-guard 的需求审查状态", hints[0])
        self.assertIn("批准时由 spec-guard 判", hints[0])

    def test_reads_the_worktree_fresh_after_a_record(self):
        self.gate("normal", "missing")
        self.assertEqual(self.add(self.spec_review("b"), rid=1).code, 3)
        self.gate("normal", "reviewed", [{"reviewer": "none", "blocking": None, "reason": "本机没有审查者"}])
        out = self.add(self.spec_review("b"), rid=2)
        self.assertEqual(out.code, 0, out.lines)

    def test_reads_the_module_worktree_not_the_integration_checkout(self):
        seen = []
        real = probe.run_map

        def spy(root, doc, project, *a, **kw):
            seen.append(os.path.realpath(project))
            return real(root, doc, project, *a, **kw)
        probe.run_map = spy
        self.addCleanup(lambda: setattr(probe, "run_map", real))
        self.gate("normal", "missing")
        flow.requirement_review(self.wt["b"], "b")
        self.assertEqual(seen, [os.path.realpath(self.wt["b"])])
