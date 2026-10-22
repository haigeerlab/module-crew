"""crew-review-batch decision 4 (0.11.2): a failed `review approve` puts the integration checkout back."""

import os
import unittest

from helpers import ReviewCase, git

from module_crew import review, store

REJECT = "#!/bin/sh\necho \"husky - commit-msg script failed (code 1)\" >&2\nexit 1\n"


class RestoreCase(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        s = review.add(self.db, self.spec_review("b"), "shop-b", 800).number
        assert review.approve(self.repo, [s], "批准 b 的 Spec").code == 0
        self.spec_before = (self.repo / "spec" / "b.md").read_bytes()
        self.head = git(self.repo, "rev-parse", "HEAD").strip()

    def revise_spec(self):
        spec = self.wt["b"] / "spec" / "b.md"
        spec.write_text(spec.read_text(encoding="utf-8") + "## 再改一处\n", encoding="utf-8")
        git(self.wt["b"], "commit", "-qam", "b: revise spec")
        return review.add(self.db, self.spec_review("b"), "shop-b", 801).number

    def approve(self, n, original):
        self.events = len(list(store.events(self.db)))
        return review.approve(self.repo, [n], original)

    def assert_restored(self, res, new_files=()):
        self.assertEqual(res.code, 4, res.lines)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), self.head)
        self.assertEqual(len(list(store.events(self.db))), self.events)
        self.assertEqual((self.repo / "spec" / "b.md").read_bytes(), self.spec_before)
        status = git(self.repo, "status", "--porcelain", "--untracked-files=all").splitlines()
        self.assertEqual(sorted(status), sorted(f"?? {f}" for f in new_files), status)   # new files kept, not staged
        for f in new_files:
            self.assertIn(f, " ".join(res.lines))


class RestoreTest(RestoreCase):
    def test_mark_failure_restores_existing_file(self):
        n = self.revise_spec()
        os.environ["FAKE_REVIEW_FAIL"] = "b"
        self.addCleanup(os.environ.pop, "FAKE_REVIEW_FAIL", None)
        self.assert_restored(self.approve(n, "批准修订后的 Spec"))

    def test_commit_refused_restores_and_lists_new_files(self):
        hook = self.repo / ".git" / "hooks" / "commit-msg"
        hook.write_text(REJECT, encoding="utf-8")
        os.chmod(hook, 0o755)
        p = review.add(self.db, self.plan_review("b"), "shop-b", 802).number
        self.assert_restored(self.approve(p, "批准 b 的 Plan"),
                             new_files=("tasks/b/plan.md", "tasks/b/todo.md"))


if __name__ == "__main__":
    unittest.main()
