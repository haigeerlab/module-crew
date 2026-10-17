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


class PrepareTest(StartCase):
    def run_prepare(self, modules=("b", "c"), **kw):
        res = start.prepare(self.repo, list(modules), "开这两个", **{"short": "shop", **kw})
        self.assertEqual(res.code, 0, res.lines)
        return res

    def test_full_prepare(self):
        res = self.run_prepare()
        db = store.open_store(self.repo)
        cfg = store.get(db, "config", "main")
        crew = self.tmp / "repo-crew"
        self.assertEqual(cfg, {"projectShort": "shop", "integrationBranch": "main", "maxModules": 3, "crewDir": str(crew)})
        for m in ("b", "c"):
            wt = crew / m
            self.assertTrue((wt / "README.md").exists())
            self.assertEqual(git(wt, "rev-parse", "--abbrev-ref", "HEAD").strip(), m)
            self.assertEqual(git(wt, "rev-parse", "HEAD"), git(self.repo, "rev-parse", "main"))
        sessions = store.records(db, "session")
        self.assertEqual(sessions["shop-coord"]["role"], "coordinator")
        self.assertEqual(sessions["shop-b"], {"role": "dev", "host": "claude-desktop", "status": "active",
                                              "module": "b", "worktree": str(crew / "b")})
        approval = store.get(db, "item", str(res.approval))
        self.assertEqual((approval["kind"], approval["state"], approval["closedReason"]), ("start", "closed", "answered"))
        self.assertEqual(approval["answer"]["original"], "开这两个")
        self.assertEqual(approval["modules"], ["b", "c"])
        self.assertEqual([p["id"] for p in res.prepared], ["b", "c"])
        self.assertTrue(all(str(p["worktree"]).startswith(str(self.tmp)) for p in res.prepared))
        self.assertIn("角色标记待 spec-guard 0.68.0", " ".join(res.lines))

    def test_kickoff_text(self):
        res = self.run_prepare()
        db = store.open_store(self.repo)
        b = res.prepared[0]
        text = store.read_body(db, b["kickoff"])
        self.assertTrue(str(db.path / "bodies" / f"{b['kickoff']}.txt"))
        crew = self.tmp / "repo-crew"
        for words in ("负责模块 b：支付页", "crew-dev skill", f"工作目录：{crew / 'b'}（分支 b，从集成分支 main 切出）",
                      "邮箱名：shop-b", "wake: \"auto\"", "协调会话：shop-coord", f"用户批准事项 #{res.approval}",
                      "spec/b.md", "tasks/b/plan.md", "【交审】", "收到开工类【协调通知】之前不要开始构建",
                      "接口：\nspec/a.md", "不要抄进这个 worktree 的 CLAUDE.md"):
            self.assertIn(words, text)
        d = store.read_body(db, self.run_prepare(modules=("d",)).prepared[0]["kickoff"])
        self.assertIn("接口：\n无", d)

    def test_second_prepare_uses_config(self):
        self.run_prepare(modules=("b",))
        res = start.prepare(self.repo, ["c"], "再开一个")
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(len([s for s in store.records(store.open_store(self.repo), "session").values()
                              if s["role"] == "coordinator"]), 1)
