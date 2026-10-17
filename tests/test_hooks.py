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


class TextTest(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def approve_spec_plan(self, m, base):
        from module_crew import review
        s = review.add(self.db, self.spec_review(m), f"shop-{m}", base).number
        p = review.add(self.db, self.plan_review(m), f"shop-{m}", base + 1).number
        assert review.approve(self.repo, [s, p], "批").code == 0
        # the module syncs the baseline as the start notice asks; the approved copies (with markers) win
        git(self.wt[m], "merge", "-q", "-X", "theirs", "--no-edit", "main")

    def stage(self, m):
        return hooks.session_start(self.wt[m], "startup")

    def test_dev_text_and_stages(self):
        text = self.stage("b")
        for words in ("模块 b", "shop-b", "shop-coord", "crew-dev", "【等待其他会话】", "写 Spec 与 Plan"):
            self.assertIn(words, text)
        self.approve_spec_plan("b", 100)
        self.assertIn("可以构建", self.stage("b"))
        from module_crew import merge
        self.approve_final("b", 200)
        self.assertIn("等协调会话合并", self.stage("b"))
        self.assertEqual(merge.run(self.repo, check_command="python3 -c pass").code, 0)
        self.assertIn("已合入集成分支", self.stage("b"))

    def test_returned_note(self):
        from module_crew import merge
        self.approve_spec_plan("b", 100)
        self.approve_final("b", 200)
        merge.run(self.repo, check_command=self.check_script(fail_if="src/b.py"))
        text = self.stage("b")
        self.assertIn("可以构建", text)
        self.assertIn("上次最终验收被退回：完整检查失败", text)

    def test_dev_open_tickets(self):
        from module_crew import inbox
        n = inbox.add(self.db, "【等待其他会话】\n结束：无\n在等谁：API\n等什么：数据\n", "shop-b", 9).number
        self.assertIn(f"#{n}", self.stage("b"))
        self.assertIn("无", self.stage("c").split("未关的等待单：")[1])

    def test_prompt_lines(self):
        line = hooks.prompt_line(self.wt["b"])
        self.assertEqual(line.count("\n"), 0)
        self.assertIn("b 的模块会话（shop-b）", line)
        coord = hooks.prompt_line(self.repo)
        self.assertEqual(coord.count("\n"), 0)
        self.assertIn("未关 事项", coord)

    def test_coordinator_text(self):
        self.approve_final("b", 1)
        text = hooks.session_start(self.repo, "resume")
        for words in ("协调会话", "shop-coord", "待合并 1", "module-crew status", "等待审批", "crew-coordinator"):
            self.assertIn(words, text)

    def test_compact_adds_check_first(self):
        for cwd in (self.wt["b"], self.repo):
            text = hooks.session_start(cwd, "compact")
            for words in ("先跑 `module-crew status`", "以状态库为准", "不按压缩前的记忆重做"):
                self.assertIn(words, text)
        self.assertNotIn("压缩", hooks.session_start(self.repo, "startup"))
