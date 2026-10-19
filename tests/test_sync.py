import unittest

from helpers import ReviewCase, git

from module_crew import store, sync


class SyncTest(ReviewCase):
    """`module-crew sync` in a module worktree (spec/crew-pilot-fixes.md key decision 1)."""

    def commit_on_main(self, rel: str, text: str) -> str:
        f = self.repo / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", f"main: {rel}")
        return git(self.repo, "rev-parse", "HEAD").strip()

    def commit_in(self, m: str, rel: str, text: str) -> None:
        f = self.wt[m] / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        git(self.wt[m], "add", "-A")
        git(self.wt[m], "commit", "-q", "-m", f"{m}: {rel}")

    def contains_main(self, m: str) -> bool:
        return git(self.repo, "rev-parse", "main").strip() in git(self.wt[m], "rev-list", "HEAD")

    def test_merges_then_up_to_date(self):
        self.commit_on_main("shared/a.txt", "a\n")
        self.commit_on_main("shared/b.txt", "b\n")
        res = sync.run(self.wt["b"])
        self.assertEqual(res.code, 0, res.lines)
        self.assertTrue(self.contains_main("b"))
        self.assertIn("合入 2 个提交", "\n".join(res.lines))
        again = sync.run(self.wt["b"])
        self.assertEqual(again.code, 0)
        self.assertIn("已是最新", "\n".join(again.lines))

    def test_own_files_conflict_take_integration_version(self):
        self.commit_on_main("spec/b.md", "<!-- spec-guard: review approved x -->\n# Spec: b\n")
        self.commit_on_main("tasks/b/plan.md", "<!-- spec-guard: review approved -->\n# Plan: b\n")
        res = sync.run(self.wt["b"])
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual((self.wt["b"] / "spec" / "b.md").read_text(encoding="utf-8"),
                         (self.repo / "spec" / "b.md").read_text(encoding="utf-8"))
        self.assertEqual((self.wt["b"] / "tasks" / "b" / "plan.md").read_text(encoding="utf-8"),
                         (self.repo / "tasks" / "b" / "plan.md").read_text(encoding="utf-8"))
        self.assertEqual(git(self.wt["b"], "status", "--porcelain"), "")
        self.assertTrue(self.contains_main("b"))

    def test_other_conflict_left_for_module(self):
        self.commit_in("b", "shared/x.txt", "mine\n")
        self.commit_on_main("shared/x.txt", "theirs\n")
        self.commit_on_main("spec/b.md", "<!-- spec-guard: review approved x -->\n# Spec: b\n")
        res = sync.run(self.wt["b"])
        self.assertEqual(res.code, 2, res.lines)
        others = "\n".join(res.lines).split("其他冲突")[1]
        self.assertIn("shared/x.txt", others)
        self.assertNotIn("spec/b.md", others)
        merge_head = git(self.wt["b"], "rev-parse", "-q", "--verify", "MERGE_HEAD").strip()
        self.assertTrue(merge_head, "merge must not be aborted")
        self.assertEqual((self.wt["b"] / "spec" / "b.md").read_text(encoding="utf-8"),
                         (self.repo / "spec" / "b.md").read_text(encoding="utf-8"))
        # the module resolves the rest, commits, and syncs again
        (self.wt["b"] / "shared" / "x.txt").write_text("resolved\n", encoding="utf-8")
        git(self.wt["b"], "add", "shared/x.txt")
        git(self.wt["b"], "commit", "-q", "--no-edit")
        again = sync.run(self.wt["b"])
        self.assertEqual(again.code, 0, again.lines)
        self.assertIn("已是最新", "\n".join(again.lines))

    def test_refusals_change_nothing(self):
        self.commit_on_main("shared/a.txt", "a\n")
        (self.wt["b"] / "dirty.txt").write_text("x\n", encoding="utf-8")
        before = git(self.wt["b"], "rev-parse", "HEAD")
        res = sync.run(self.wt["b"])
        self.assertEqual(res.code, 3)
        self.assertIn("先提交或收起改动", "\n".join(res.lines))
        self.assertEqual(git(self.wt["b"], "rev-parse", "HEAD"), before)
        self.assertEqual(sync.run(self.repo).code, 3)                 # integration checkout
        other = self.tmp / "elsewhere"
        git(self.repo, "worktree", "add", "-q", "-b", "elsewhere", str(other))
        self.assertEqual(sync.run(other).code, 3)                     # not a registered module worktree

    def test_cli(self):
        self.commit_on_main("shared/a.txt", "a\n")
        out = self.run_cli("sync", cwd=self.wt["c"])
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("合入 1 个提交", out.stdout)


if __name__ == "__main__":
    unittest.main()
