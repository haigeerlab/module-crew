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


PREVIEW_PREAMBLE = '''import os as _os, sys as _sys
if "--confirm" not in _sys.argv and _os.environ.get("FAKE_REVIEW_PREVIEW"):
    print(open(_os.environ["FAKE_REVIEW_PREVIEW"], encoding="utf-8").read())
    _sys.exit(0)
if "--confirm" in _sys.argv and _os.environ.get("FAKE_REVIEW_OUT"):
    print(_os.environ["FAKE_REVIEW_OUT"])
    _sys.exit(2)
'''

DIFF_OUT = """Changes since the review (show this diff to the user verbatim):
--- spec/b.md (reviewed, abc1234)
+++ spec/b.md (now)
@@ -1,2 +1,2 @@
 # Spec: b
-旧的一句
+新的一句

--- spec/b.md (current)
+++ spec/b.md (proposed)
@@ -1 +1,2 @@
+<!-- spec-guard: review approved x -->
Spec digest: x (text of spec/b.md without the marker line)
review state after: spec/b.md approved
"""


class PreviewMixin(GateMixin):
    def setUp(self):
        super().setUp()
        root = probe.find_plugin("spec-guard", self.repo).root
        script = root / "hooks" / "review_mark.py"
        script.write_text(PREVIEW_PREAMBLE + script.read_text(encoding="utf-8"), encoding="utf-8")
        self.preview_file = self.repo.parent / "preview.txt"
        for key in ("FAKE_REVIEW_PREVIEW", "FAKE_REVIEW_OUT"):
            self.addCleanup(lambda k=key: os.environ.pop(k, None))

    def preview(self, text: str):
        self.preview_file.write_text(text, encoding="utf-8")
        os.environ["FAKE_REVIEW_PREVIEW"] = str(self.preview_file)


class RequirementDisplayTest(PreviewMixin, ReviewCase):
    """Task 2, decision 5; AC4."""

    def reviewed(self, record):
        self.gate("normal", "reviewed", [record])

    def test_summary_line_per_reviewer(self):
        cases = [({"reviewer": "codex", "blocking": 2, "reason": None}, "需求审查：Codex（delegate），阻断 2 条"),
                 ({"reviewer": "host", "blocking": 0, "reason": None}, "需求审查：宿主子会话，阻断 0 条"),
                 ({"reviewer": "none", "blocking": None, "reason": "本机没有审查者"},
                  "需求审查：没有审查者（原因：本机没有审查者）")]
        self.preview("spec/b.md: nothing changed since the review.\n")
        for record, want in cases:
            with self.subTest(reviewer=record["reviewer"]):
                self.reviewed(record)
                self.assertEqual(review.requirement_lines(self.wt["b"], "b")[0], want)

    def test_diff_is_spec_guards_text(self):
        self.reviewed({"reviewer": "codex", "blocking": 1, "reason": None})
        self.preview(DIFF_OUT)
        got = review.requirement_diff(self.wt["b"], "b")
        self.assertEqual(got[0], "Changes since the review (show this diff to the user verbatim):")
        self.assertIn("+新的一句", got)
        self.assertNotIn("--- spec/b.md (current)", got)       # the marker preview is not the review diff
        self.assertNotIn("Spec digest", "\n".join(got))
        self.assertEqual(got[-1], "+新的一句")

    def test_unchanged_and_unavailable(self):
        self.reviewed({"reviewer": "host", "blocking": 0, "reason": None})
        for line in ("spec/b.md: nothing changed since the review.",
                     "spec/b.md: the changes since the review cannot be shown (git log failed); give the user the whole requirement."):
            with self.subTest(line=line):
                self.preview(line + "\nreview state after: spec/b.md approved\n")
                self.assertEqual(review.requirement_diff(self.wt["b"], "b"), [line])

    def test_batch_card_and_show(self):
        self.reviewed({"reviewer": "codex", "blocking": 1, "reason": None})
        self.preview(DIFF_OUT)
        out = self.add(self.spec_review("b"))
        self.assertEqual(out.code, 0, out.lines)
        b = review.batch(self.repo)
        [item] = b["items"]
        self.assertEqual(item["requirement"][0], "需求审查：Codex（delegate），阻断 1 条")
        self.assertIn("+新的一句", item["requirement"])
        [(_, _, card)] = review.for_hub(self.repo)
        self.assertIn("需求审查：Codex（delegate），阻断 1 条", card)
        self.assertIn("+新的一句", card)
        code, text = self.cli("review", "batch")
        self.assertIn("需求审查：Codex（delegate），阻断 1 条", text)
        self.assertEqual(review.show(self.db(), out.number, review_diff=True),
                         review.requirement_diff(self.wt["b"], "b"))
        code, text = self.cli("review", "show", f"C{out.number}", "--review-diff")
        self.assertEqual(code, 0, text)
        self.assertIn("+新的一句", text)

    def test_old_module_display_unchanged(self):
        self.set_flow({}, {"b": gate_row(None)})
        self.preview(DIFF_OUT)
        out = self.add(self.spec_review("b"))
        [item] = review.batch(self.repo)["items"]
        self.assertNotIn("requirement", item)
        [(_, _, card)] = review.for_hub(self.repo)
        self.assertNotIn("需求审查", card)
        self.assertEqual(review.show(self.db(), out.number, review_diff=True),
                         [f"C{out.number} 不是新流程需求，或 spec-guard 没有它的审查记录：没有审查后的改动差异"])
