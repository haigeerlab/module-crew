"""T855: review approve with spec-guard 0.99.0 (interface 1.27), whose reviewMark.command gained the optional parts
`[--blocking <N>]` and `[--reason <one line>]` and wider --target / --state placeholders."""
import unittest
from pathlib import Path

from helpers import ReviewCase, git, spec_guard_interface

from module_crew import review, store

REVIEW_MARK_127 = ["python3", "-B", "hooks/review_mark.py", "--project", "<project-root>", "--module", "<module-id>",
                   "--target", "<spec|plan|both|acceptance|design|overall>",
                   "--state", "<pending|approved|codex-approved|codex-reviewed|reviewer-approved|reviewer-reviewed"
                              "|host-reviewed|no-reviewer>",
                   "[--review <report file>]", "[--blocking <N>]", "[--reason <one line>]"]


class MarkArgsTest(unittest.TestCase):
    root = Path(__file__).resolve().parent
    doc = {"reviewMark": {"command": REVIEW_MARK_127}}

    def test_fills_127_command(self):
        out = review.mark_args(self.root, self.doc, Path("/p"), "m", "spec")
        self.assertEqual(out, ["python3", "-B", "hooks/review_mark.py", "--project", "/p", "--module", "m",
                               "--target", "spec", "--state", "approved"])

    def test_review_still_expanded(self):
        out = review.mark_args(self.root, self.doc, Path("/p"), "m", "plan", "codex-reviewed", review_file="r.json")
        self.assertEqual(out[-4:], ["--state", "codex-reviewed", "--review", "r.json"])
        self.assertNotIn("--blocking", out)
        self.assertNotIn("--reason", out)

    def test_unknown_placeholder_inside_optional_part_is_skipped(self):
        doc = {"reviewMark": {"command": REVIEW_MARK_127[:11] + ["[--future <x>]"]}}
        out = review.mark_args(self.root, doc, Path("/p"), "m", "spec")
        self.assertIsInstance(out, list, out)
        self.assertNotIn("--future", out)


class Approve127Test(ReviewCase):
    def test_approve_spec_with_127_command(self):
        self.plugins.entries.pop("spec-guard@m")
        self.plugins.install("spec-guard", spec_guard_interface("1.27", review_mark=REVIEW_MARK_127), map_script=True)
        db = store.open_store(self.repo)
        s = review.add(db, self.spec_review("b"), "shop-b", 4600)
        self.assertEqual(s.code, 0, s.lines)
        before = git(self.repo, "rev-parse", "HEAD").strip()
        res = review.approve(self.repo, [s.number], "b 的 Spec 批准")
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(git(self.repo, "diff", "--name-only", before, "HEAD").split(), ["spec/b.md"])
        spec = (self.repo / "spec" / "b.md").read_text()
        self.assertTrue(spec.startswith("<!-- spec-guard: review approved fakedigest -->\n"))


if __name__ == "__main__":
    unittest.main()
