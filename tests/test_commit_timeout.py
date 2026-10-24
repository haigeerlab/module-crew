"""S28 (0.14.1): commit-class git calls wait as long as checkTimeout, and a timed-out hook is killed with its children."""

import os
import subprocess
import unittest
import uuid

from helpers import MergeCase, git

from module_crew import changes, merge, review, store
from test_merge_pilot import todo


class TimeoutCase(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        self.token = f"crew-hook-{uuid.uuid4().hex}"
        self.addCleanup(lambda: subprocess.run(["pkill", "-f", self.token], capture_output=True))
        self.set_timeout(1)

    def set_timeout(self, seconds):
        with self.db.transaction(actor="test") as tx:
            tx.put("config", "main", dict(tx.get("config", "main"), checkTimeout=seconds), action="t")

    def slow_hook(self, name, seconds=5):
        """A hook whose child process sleeps; the token in its command line finds leftovers."""
        path = self.repo / ".git" / "hooks" / name
        path.write_text(f'#!/bin/sh\npython3 -c "import time; time.sleep({seconds})" {self.token}\n', encoding="utf-8")
        os.chmod(path, 0o755)

    def assert_no_leftover(self):
        found = subprocess.run(["pgrep", "-f", self.token], capture_output=True, text=True).stdout.strip()
        self.assertEqual(found, "", "hook processes left behind")
        self.assertFalse((self.repo / ".git" / "index.lock").exists())

    def land_request(self, rid):
        n = changes.add(self.db, "【公共变更请求】\n结束：无\n来自：b\n文件：\nx.json\n改什么：改\n为什么：要\n"
                        "是否完全停住：否\n", "shop-b", rid).number
        (self.repo / "x.json").write_text("{}\n")
        return n


class CommitTimeoutTest(TimeoutCase):
    def test_change_land_times_out(self):
        n = self.land_request(1)
        head = git(self.repo, "rev-parse", "HEAD").strip()
        self.slow_hook("pre-commit")
        res = changes.land(self.repo, n)
        self.assertEqual(res.code, 4, res.lines)
        text = "\n".join(res.lines)
        self.assertIn("超时（1 秒）", text)
        self.assertIn("已暂存的文件：x.json（仍是暂存状态）", text)
        self.assertIn("可以重试同一条 change land，不用先 unstage", text)
        self.assert_no_leftover()
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), head)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "A  x.json\n")
        self.assertEqual(store.get(self.db, "request", str(n))["state"], "open")
        # LIVE-SAAS C55: an unrelated docs commit lands on the integration branch while x.json stays staged
        self.set_timeout(30)                              # longer than the hook: the retry commits
        self.slow_hook("pre-commit", 0.5)
        (self.repo / "notes.md").write_text("docs\n")
        git(self.repo, "add", "notes.md")
        git(self.repo, "commit", "-q", "-m", "docs: 无关的文档", "--", "notes.md")
        self.assertEqual(git(self.repo, "status", "--porcelain"), "A  x.json\n")
        again = changes.land(self.repo, n)
        self.assertEqual(again.code, 0, again.lines)
        self.assertEqual(store.get(self.db, "request", str(n))["state"], "closed")
        self.assertEqual(git(self.repo, "show", "--name-only", "--format=", "HEAD").split(), ["x.json"])
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_review_approve_times_out_and_restores(self):
        s = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        head = git(self.repo, "rev-parse", "HEAD").strip()
        self.slow_hook("pre-commit")
        res = review.approve(self.repo, [s], "批")
        self.assertEqual(res.code, 4, res.lines)
        text = "\n".join(res.lines)
        self.assertIn("超时（1 秒）", text)
        self.assertIn("状态库与集成分支都没有变化", text)       # _restore ran
        self.assert_no_leftover()
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), head)
        self.assertEqual(store.get(self.db, "item", str(s))["state"], "open")

    def test_merge_commit_times_out_and_aborts(self):
        n = self.approve_final("b", 1)
        head = git(self.repo, "rev-parse", "HEAD").strip()
        self.slow_hook("pre-merge-commit")
        res = merge.run(self.repo, check_command="python3 -c pass")
        self.assertEqual(res.code, 4, res.lines)
        text = "\n".join(res.lines)
        self.assertIn("超时（1 秒）", text)
        self.assertIn("已中止合并，集成分支未变", text)
        self.assert_no_leftover()
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), head)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        self.assertFalse((self.repo / ".git" / "MERGE_HEAD").exists())
        self.assertEqual(store.get(self.db, "item", str(n))["state"], "open")

    def test_wrap_up_tick_times_out_without_recording(self):
        todo(self.wt["b"], "b", (True, "Task 1"), (False, "最终验收（gate）"))
        n = self.approve_final("b", 1)
        self.slow_hook("pre-commit")                      # the merge commit runs pre-merge-commit, the tick pre-commit
        res = merge.run(self.repo, check_command="python3 -c pass")
        self.assertEqual(res.code, 4, res.lines)
        text = "\n".join(res.lines)
        short = res.merge_commit[:7]
        self.assertIn("超时（1 秒）", text)
        self.assertIn(f"合并提交 {short} 已在集成分支、检查已通过、状态库未记合并，不要重跑 merge run，交模块协调", text)
        self.assert_no_leftover()
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), res.merge_commit)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        self.assertEqual(store.get(self.db, "item", str(n))["state"], "open")


class LongTimeoutTest(TimeoutCase):
    def test_long_timeout_lets_slow_hooks_commit(self):
        self.set_timeout(30)
        self.slow_hook("pre-commit", 1.5)
        s = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        self.assertEqual(review.approve(self.repo, [s], "批").code, 0)


if __name__ == "__main__":
    unittest.main()
