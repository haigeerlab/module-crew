import unittest

from helpers import START_MAP, StartCase, git

from module_crew import start, store


def snapshot(case):
    """Everything prepare could touch: repo files, branches, worktrees, sibling dirs, store files."""
    files = {str(p): p.read_bytes() for p in case.repo.rglob("*") if p.is_file() and ".git/index" not in str(p)}
    return (files, git(case.repo, "branch", "--list"), git(case.repo, "worktree", "list"),
            sorted(str(p) for p in case.tmp.iterdir()))


class ValidateTest(StartCase):
    def assert_refused(self, modules, words, original="开吧", **kw):
        before = snapshot(self)
        res = start.prepare(self.repo, modules, original, **{"short": "shop", **kw})
        self.assertEqual(res.code, 3, res.lines)
        self.assertIn(words, " ".join(res.lines))
        self.assertEqual(snapshot(self), before)

    def test_blocked_by_probe_store_not_created(self):
        (self.repo / "dirty.txt").write_text("x")
        self.assert_refused(["b"], "集成基线不干净")
        self.assertFalse((self.repo / ".git" / "module-crew").exists())

    def test_not_startable(self):
        self.assert_refused(["e"], "不在可开工列表")

    def test_over_slots(self):
        self.assert_refused(["b", "c", "d"], "空位", max_modules=2)

    def test_directory_or_branch_exists(self):
        (self.tmp / "repo-crew" / "b").mkdir(parents=True)
        self.assert_refused(["b"], "目录已存在")
        git(self.repo, "branch", "c")
        self.assert_refused(["c"], "分支已存在")

    def test_bad_short_name(self):
        for short in ("Shop", "s", "a" * 21, "shop_x"):
            with self.subTest(short):
                self.assert_refused(["b"], "项目简称", short=short)

    def test_missing_original(self):
        self.assert_refused(["b"], "原话", original="  ")

    def test_short_fixed_after_first_prepare(self):
        db, _ = store.init_store(self.repo)
        with db.transaction(actor="t") as tx:
            tx.put("config", "main", {"projectShort": "shop", "integrationBranch": "main", "maxModules": 3,
                                      "crewDir": str(self.tmp / "repo-crew")}, action="set")
        self.assert_refused(["b"], "项目简称", short="mall")


if __name__ == "__main__":
    unittest.main()
