import unittest

from helpers import MergeCase, RepoCase, git

from module_crew import hooks, store


class SilentTest(RepoCase):
    def test_unrelated_and_uninitialised(self):
        outside = self.tmp / "plain"
        outside.mkdir()
        for cwd in (outside, self.repo):
            with self.subTest(cwd=str(cwd)):
                self.assertIsNone(hooks.detect(cwd))
                self.assertIsNone(hooks.session_start(cwd, "startup"))
                self.assertIsNone(hooks.prompt_line(cwd))


class DetectTest(MergeCase):
    def test_module_worktree_and_subdir(self):
        (self.wt["b"] / "src").mkdir(exist_ok=True)
        for cwd in (self.wt["b"], self.wt["b"] / "src"):
            with self.subTest(cwd=str(cwd)):
                role = hooks.detect(cwd)
                self.assertEqual((role.kind, role.name, role.module), ("dev", "shop-b", "b"))

    def test_integration_checkout_is_coordinator(self):
        role = hooks.detect(self.repo)
        self.assertEqual((role.kind, role.name), ("coordinator", "shop-coord"))

    def test_unregistered_checkout_silent(self):
        from helpers import make_worktree
        other = make_worktree(self.repo, "other")
        self.assertIsNone(hooks.detect(other))

    def test_retired_session_silent(self):
        db = store.open_store(self.repo)
        with db.transaction(actor="t") as tx:
            tx.put("session", "shop-c", dict(tx.get("session", "shop-c"), status="retired"), action="retired")
        self.assertIsNone(hooks.detect(self.wt["c"]))
