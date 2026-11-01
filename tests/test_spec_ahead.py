"""crew-spec-ahead: open a module whose dependencies are not done yet, for its Spec and Plan only."""

import copy
import unittest

from helpers import START_MAP, StartCase, git

from module_crew import start, store


def ahead_map(**status):
    """START_MAP with some statuses replaced (e depends on b and c and is not_ready by default)."""
    doc = copy.deepcopy(START_MAP)
    for m in doc["modules"]:
        m["status"] = status.get(m["id"], m["status"])
    return doc


class PrepareTest(StartCase):
    def dev(self, module):
        sessions = store.records(store.open_store(self.repo), "session")
        return next(v for v in sessions.values() if v.get("role") == "dev" and v.get("module") == module)

    def test_not_ready_module_opens_for_spec_and_plan(self):
        res = start.prepare(self.repo, ["e"], "先开 e 写 Spec", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        self.assertIn("e：提前开工（依赖 b、c 未完成），只写 Spec 与 Plan", res.lines)
        self.assertEqual(self.dev("e")["specAhead"], {"missing": ["b", "c"], "since": res.approval})
        item = store.get(store.open_store(self.repo), "item", str(res.approval))
        self.assertEqual(item["specAhead"], ["e"])

    def test_plain_module_carries_no_spec_ahead(self):
        res = start.prepare(self.repo, ["b"], "开 b", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        self.assertNotIn("specAhead", self.dev("b"))
        self.assertNotIn("specAhead", store.get(store.open_store(self.repo), "item", str(res.approval)))

    def test_missing_counts_only_unfinished_dependencies(self):
        self.set_map(ahead_map(b="done"))
        res = start.prepare(self.repo, ["e"], "先开 e", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(self.dev("e")["specAhead"]["missing"], ["c"])

    def assert_refused(self, modules, words, **kw):
        before = (git(self.repo, "branch", "--list"), git(self.repo, "worktree", "list"))
        res = start.prepare(self.repo, modules, "开吧", **{"short": "shop", **kw})
        self.assertEqual(res.code, 3, res.lines)
        self.assertIn(words, " ".join(res.lines))
        self.assertEqual((git(self.repo, "branch", "--list"), git(self.repo, "worktree", "list")), before)

    def test_blocked_module_still_refused(self):
        self.set_map(ahead_map(e="blocked"))
        self.assert_refused(["e"], "不在可开工列表")

    def test_other_blockers_unchanged(self):
        self.assert_refused(["b", "c", "e"], "空位", max_modules=2)
        (self.tmp / "repo-crew" / "e").mkdir(parents=True)
        self.assert_refused(["e"], "目录已存在")

    def test_existing_session_refused(self):
        self.assertEqual(start.prepare(self.repo, ["e"], "开 e", short="shop").code, 0)
        self.assert_refused(["e"], "已有在用的模块会话")

    def test_plan_does_not_propose(self):
        picked = [m["id"] for m in start.plan(self.repo, 3).modules]
        self.assertNotIn("e", picked)


if __name__ == "__main__":
    unittest.main()
