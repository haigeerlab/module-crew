"""crew-merge decision 10 (0.11.1): a Spec revised during the build gets its approval recorded when it is merged."""

import os
import unittest

from helpers import MergeCase, git

from module_crew import merge, review, store


class SpecRevisionTest(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        s = review.add(self.db, self.spec_review("b"), "shop-b", 900).number
        assert review.approve(self.repo, [s], "批准 b 的 Spec").code == 0
        branch = store.get(self.db, "config", "main")["integrationBranch"]
        git(self.wt["b"], "merge", "-q", "--no-edit", "-X", "theirs", branch)       # the module syncs its baseline

    def revise(self):
        spec = self.wt["b"] / "spec" / "b.md"
        body = spec.read_text(encoding="utf-8").splitlines(keepends=True)[1:]
        spec.write_text("<!-- spec-guard: review pending -->\n" + "".join(body) + "## 构建中补的一条\n", encoding="utf-8")
        git(self.wt["b"], "commit", "-q", "-am", "b: revise spec")

    def final(self, rid=901):
        out = review.add(self.db, self.finish("b"), "shop-b", rid)
        self.assertEqual(out.code, 0, out.lines)
        return out

    def test_revised_spec_marked_after_merge(self):
        self.revise()
        out = self.final()
        self.assertTrue(any("spec/b.md" in x and "差异" in x for x in out.lines), out.lines)
        rec = store.get(self.db, "item", str(out.number))
        self.assertEqual(rec["specRevised"]["path"], "spec/b.md")
        self.assertIn("+## 构建中补的一条", rec["specRevised"]["diff"])
        n = merge.approve(self.db, out.number, "b 验收通过，修订后的 Spec 一并批准").approval
        self.assertTrue(store.get(self.db, "item", str(n))["specRevisionApproved"])
        res = merge.run(self.repo, check_command=self.check_script())
        self.assertEqual(res.code, 0, res.lines)
        top = git(self.repo, "log", "-1", "--format=%s").strip()
        self.assertIn(f"合并批准事项 C{n}：记下 b 修订后 Spec 的批准", top)
        self.assertEqual(git(self.repo, "diff", "--name-only", "HEAD^", "HEAD").split(), ["spec/b.md"])
        self.assertEqual(git(self.repo, "rev-parse", "HEAD^").strip(), res.merge_commit)
        first = (self.repo / "spec" / "b.md").read_text(encoding="utf-8").splitlines()[0]
        self.assertIn("review approved", first)
        self.assertTrue(any("修订后 Spec 的批准" in x for x in res.lines), res.lines)
        self.assertEqual(git(self.repo, "status", "--porcelain").strip(), "")

    def test_unrevised_spec_no_extra_commit(self):
        out = self.final()
        self.assertNotIn("specRevised", store.get(self.db, "item", str(out.number)))
        merge.approve(self.db, out.number, "b 验收通过")
        res = merge.run(self.repo, check_command=self.check_script())
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), res.merge_commit)

    def test_mark_failure_only_reported(self):
        self.revise()
        out = self.final()
        n = merge.approve(self.db, out.number, "b 验收通过").approval
        os.environ["FAKE_REVIEW_FAIL"] = "b"
        self.addCleanup(os.environ.pop, "FAKE_REVIEW_FAIL", None)
        res = merge.run(self.repo, check_command=self.check_script())
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(store.get(self.db, "item", str(n))["closedReason"], "merged")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), res.merge_commit)
        self.assertTrue(any("没有记上" in x for x in res.lines), res.lines)
        self.assertEqual(git(self.repo, "status", "--porcelain").strip(), "")


if __name__ == "__main__":
    unittest.main()
