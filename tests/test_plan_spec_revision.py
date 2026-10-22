"""crew-review-batch decision 7 (0.11.2): a Plan review that carries a revised Spec gets both approvals recorded."""

import unittest

from helpers import ReviewCase, git, review_text

from module_crew import review, store

MARK = "<!-- spec-guard: review approved "


class PlanCarriesSpecTest(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        s = review.add(self.db, self.spec_review("b"), "shop-b", 700).number
        assert review.approve(self.repo, [s], "批准 b 的 Spec").code == 0
        branch = store.get(self.db, "config", "main")["integrationBranch"]
        git(self.wt["b"], "merge", "-q", "--no-edit", "-X", "theirs", branch)    # the module syncs its baseline
        self.approved = (self.repo / "spec" / "b.md").read_bytes()

    def spec_with(self, marker, extra=""):
        spec = self.wt["b"] / "spec" / "b.md"
        body = spec.read_text(encoding="utf-8").splitlines(keepends=True)[1:]
        spec.write_text(marker + "\n" + "".join(body) + extra, encoding="utf-8")
        git(self.wt["b"], "commit", "-qam", "b: spec as the module has it")

    def plan_with_spec(self, rid=701):
        files = [(f"tasks/b/{n}", self.wt["b"] / "tasks" / "b" / n) for n in ("plan.md", "todo.md")]
        files.append(("spec/b.md", self.wt["b"] / "spec" / "b.md"))
        out = review.add(self.db, review_text("b", "Plan", files), "shop-b", rid)
        self.assertEqual(out.code, 0, out.lines)
        return out

    def test_revised_spec_approved_with_the_plan(self):
        self.spec_with("<!-- spec-guard: review approved olddigest -->", "## 按批准时的要求改的一处\n")
        out = self.plan_with_spec()
        self.assertTrue(any("spec/b.md" in x and "差异" in x for x in out.lines), out.lines)
        self.assertIn("+## 按批准时的要求改的一处", store.get(self.db, "item", str(out.number))["specRevised"]["diff"])
        before = git(self.repo, "rev-parse", "HEAD").strip()
        res = review.approve(self.repo, [out.number], "批准 Plan，同时批准修订后的 Spec")
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(git(self.repo, "rev-list", "--count", f"{before}..HEAD").strip(), "1")
        spec = (self.repo / "spec" / "b.md").read_text(encoding="utf-8")
        self.assertTrue(spec.startswith(MARK + "fakedigest"), spec)
        self.assertIn("## 按批准时的要求改的一处", spec)
        self.assertTrue((self.repo / "tasks" / "b" / "plan.md").read_text(encoding="utf-8").startswith(MARK))
        self.assertEqual(git(self.repo, "status", "--porcelain").strip(), "")

    def test_marker_only_difference_not_copied(self):
        self.spec_with("<!-- spec-guard: review approved olddigest -->")
        out = self.plan_with_spec()
        self.assertNotIn("specRevised", store.get(self.db, "item", str(out.number)))
        res = review.approve(self.repo, [out.number], "批准 Plan")
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual((self.repo / "spec" / "b.md").read_bytes(), self.approved)
        self.assertTrue((self.repo / "tasks" / "b" / "plan.md").read_text(encoding="utf-8").startswith(MARK))
        self.assertEqual(git(self.repo, "status", "--porcelain").strip(), "")


if __name__ == "__main__":
    unittest.main()
