"""S39 (0.16.1): write-class git calls (worktree add/remove, branch -f, merge/abort/reset, sync) wait as long as
checkTimeout, a timeout ends in exit 4 with what was left half-done, and cleanup can finish a half-removed worktree."""

import subprocess
import unittest
from pathlib import Path
from unittest import mock

from helpers import MergeCase, ReviewCase, git
from test_commit_timeout import TimeoutCase
from test_light_task import new_task

from module_crew import hooks, merge, probe, start, store, sync, tasks


class Spy:
    """Wraps probe._git: records (args, timeout) and can make calls matching `fail` raise TimeoutExpired."""

    def __init__(self, fail=None):
        self.calls, self.fail, self.real = [], fail, probe._git

    def __call__(self, cwd, *args, timeout=probe.GIT_TIMEOUT):
        self.calls.append((args, timeout))
        if self.fail and self.fail(args):
            exc = subprocess.TimeoutExpired(["git", *args], timeout)
            exc.elapsed = timeout + 0.1
            raise exc
        return self.real(cwd, *args, timeout=timeout)

    def timeout_of(self, *prefix):
        return [t for a, t in self.calls if a[:len(prefix)] == prefix]


def merged_b(case):
    case.approve_final("b", 1)
    res = merge.run(case.repo, check_command="python3 -c pass")
    assert res.code == 0, res.lines


class CleanupTimeoutTest(TimeoutCase):
    def test_worktree_remove_uses_check_timeout(self):
        merged_b(self)
        self.set_timeout(1234)
        spy = Spy()
        with mock.patch.object(probe, "_git", spy):
            res = merge.cleanup(self.repo, "b", "收回 b")
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(spy.timeout_of("worktree", "remove"), [1234])

    def test_worktree_remove_timeout_is_exit_4(self):
        merged_b(self)
        self.set_timeout(7)
        with mock.patch.object(probe, "_git", Spy(lambda a: a[:2] == ("worktree", "remove"))):
            res = merge.cleanup(self.repo, "b", "收回 b")
        self.assertEqual(res.code, 4, res.lines)
        text = "\n".join(res.lines)
        self.assertIn("超时（7 秒）", text)
        self.assertIn("删了一半", text)
        self.assertIn("状态库没动", text)
        self.assertIn("git checkout -- .", text)
        self.assertEqual(store.get(self.db, "session", "shop-b")["status"], "active")

    def test_cli_timeout_no_traceback(self):
        merged_b(self)
        words = self.tmp / "w.txt"
        words.write_text("收回 b", encoding="utf-8")
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")
        import os
        import shutil
        fake = self.tmp / "bin"            # a fake git on PATH whose worktree remove outlasts checkTimeout (1 s)
        fake.mkdir()
        (fake / "git").write_text(f'#!/bin/sh\ncase "$*" in *"worktree remove"*) exec python3 -c "import time; '
                                  f'time.sleep(5)" {self.token};; esac\nexec {shutil.which("git")} "$@"\n')
        (fake / "git").chmod(0o755)
        env = dict(os.environ, CLAUDE_CODE_SESSION_ID="sid-coord", PATH=f"{fake}:{os.environ['PATH']}")
        out = self.run_cli("merge", "cleanup", "b", "--original-file", str(words), env=env)
        self.assertEqual(out.returncode, 4, out.stdout + out.stderr)
        self.assertNotIn("Traceback", out.stdout + out.stderr)
        self.assertIn("删了一半", out.stdout + out.stderr)
        self.assert_no_leftover()
        self.assertEqual(store.get(self.db, "session", "shop-b")["status"], "active")


class CleanupResumeTest(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        merged_b(self)

    def test_only_tracked_files_deleted_forces_remove(self):
        (self.wt["b"] / "README.md").unlink()       # what a half-done worktree remove leaves behind
        res = merge.cleanup(self.repo, "b", "收回 b")
        self.assertEqual(res.code, 0, res.lines)
        self.assertIn("只有已跟踪文件被删", "\n".join(res.lines))
        self.assertFalse(self.wt["b"].exists())
        self.assertNotIn(str(self.wt["b"]), git(self.repo, "worktree", "list"))
        self.assertEqual(store.get(self.db, "session", "shop-b")["status"], "retired")

    def test_directory_gone_but_registered_prunes(self):
        import shutil
        shutil.rmtree(self.wt["b"])
        self.assertIn(str(self.wt["b"]), git(self.repo, "worktree", "list"))
        res = merge.cleanup(self.repo, "b", "收回 b")
        self.assertEqual(res.code, 0, res.lines)
        self.assertIn("git worktree prune", "\n".join(res.lines))
        self.assertNotIn(str(self.wt["b"]), git(self.repo, "worktree", "list"))
        self.assertEqual(store.get(self.db, "session", "shop-b")["status"], "retired")

    def assert_refused(self, why):
        res = merge.cleanup(self.repo, "b", "收回 b")
        self.assertEqual(res.code, 3, res.lines)
        text = "\n".join(res.lines)
        self.assertIn(why, text)
        self.assertIn("git checkout -- .", text)
        self.assertTrue(self.wt["b"].exists())
        self.assertIn(str(self.wt["b"]), git(self.repo, "worktree", "list"))
        self.assertEqual(store.get(self.db, "session", "shop-b")["status"], "active")

    def test_resume_refused_when_not_only_deleted(self):          # precondition 1
        (self.wt["b"] / "README.md").unlink()
        (self.wt["b"] / "src" / "b.py").write_text("changed\n")
        self.assert_refused("已修改、已暂存或未跟踪")

    def test_resume_refused_with_untracked_or_staged(self):       # precondition 2
        (self.wt["b"] / "README.md").unlink()
        (self.wt["b"] / "new.txt").write_text("x")
        self.assert_refused("new.txt")
        (self.wt["b"] / "new.txt").unlink()
        git(self.wt["b"], "rm", "-q", "--cached", "src/b.py")      # staged deletion, file still on disk
        self.assert_refused("src/b.py")

    def test_resume_refused_when_head_not_merged(self):           # precondition 3
        (self.wt["b"] / "later.txt").write_text("x")
        git(self.wt["b"], "add", "later.txt")
        git(self.wt["b"], "commit", "-q", "-m", "b: after merge")
        (self.wt["b"] / "README.md").unlink()
        self.assert_refused("不在集成分支 main 上")

    def test_resume_refused_when_worktree_belongs_elsewhere(self):  # precondition 4
        from module_crew import role
        path = role.marker_path(self.wt["b"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("module c\n", encoding="utf-8")       # spec-guard's marker now says this checkout is c's
        (self.wt["b"] / "README.md").unlink()
        self.assert_refused("不归 shop-b")


class TaskResumeTest(MergeCase):
    """Precondition 3 applies to merged light tasks only: a cancelled task's branch is kept unmerged on purpose."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")

    def test_cancelled_task_skips_ancestor_check(self):
        n = new_task(self.db, self.repo)
        d = tasks.dispatch(self.db, self.repo, n)
        hooks.bind(self.db, d.relay, f"sid-t{n}", d.worktree)
        wt = Path(d.worktree)
        (wt / "docs").mkdir(exist_ok=True)
        (wt / "docs" / "t.md").write_text("x\n")
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", "t: unmerged work")
        tasks.cancel(self.db, n, "取消")
        (wt / "README.md").unlink()
        res = merge.cleanup(self.repo, f"T{n}", "收回")
        self.assertEqual(res.code, 0, res.lines)
        self.assertIn("--force 续做", "\n".join(res.lines))
        self.assertFalse(wt.exists())
        self.assertTrue(git(self.repo, "rev-parse", "--verify", f"task/t{n}").strip())


class WorktreeAddTimeoutTest(TimeoutCase):
    """worktree add runs post-checkout: a slow hook used to hit the read-only 30 / 60 second limits."""

    def test_start_prepare_worktree_add_times_out(self):
        self.slow_hook("post-checkout")
        res = start.prepare(self.repo, ["d"], "开 d", short="shop", max_modules=3)
        self.assertEqual(res.code, 4, res.lines)
        text = "\n".join(res.lines)
        self.assertIn("超时（1 秒）", text)
        self.assertIn("建了一半", text)
        self.assertIn("状态库没动", text)
        self.assertNotIn("d", {s.get("module") for s in store.records(self.db, "session").values()})
        self.assert_no_leftover()

    def test_start_prepare_uses_check_timeout(self):
        self.set_timeout(4321)
        spy = Spy()
        with mock.patch.object(probe, "_git", spy):
            res = start.prepare(self.repo, ["d"], "开 d", short="shop", max_modules=3)
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(spy.timeout_of("worktree", "add"), [4321])

    def test_task_dispatch_worktree_add_times_out(self):
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")
        n = new_task(self.db, self.repo, kind="bug")
        self.slow_hook("post-checkout")
        with self.assertRaises(tasks.TaskStopped) as caught:
            tasks.dispatch(self.db, self.repo, n)
        self.assertIn("建了一半", str(caught.exception))
        self.assertIn("状态库没动", str(caught.exception))
        self.assertEqual(store.get(self.db, "task", str(n))["state"], "ready")
        self.assert_no_leftover()

    def test_task_dispatch_uses_check_timeout(self):
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")
        n = new_task(self.db, self.repo, kind="bug")
        self.set_timeout(2468)
        spy = Spy()
        with mock.patch.object(probe, "_git", spy):
            tasks.dispatch(self.db, self.repo, n)
        self.assertEqual(spy.timeout_of("worktree", "add"), [2468])


class MergeAbortTimeoutTest(TimeoutCase):
    def test_abort_after_timed_out_merge_uses_check_timeout(self):
        self.approve_final("b", 1)
        self.set_timeout(99)
        spy = Spy(lambda a: a[:1] == ("merge",) and "--no-ff" in a)
        with mock.patch.object(probe, "_git", spy):
            res = merge.run(self.repo, check_command="python3 -c pass")
        self.assertEqual(res.code, 4, res.lines)
        self.assertEqual(spy.timeout_of("merge", "--abort"), [99])

    def test_abort_timing_out_too_is_exit_4(self):
        self.approve_final("b", 1)
        spy = Spy(lambda a: a[:1] == ("merge",) and ("--no-ff" in a or "--abort" in a))
        with mock.patch.object(probe, "_git", spy):
            res = merge.run(self.repo, check_command="python3 -c pass")
        self.assertEqual(res.code, 4, res.lines)
        self.assertIn("状态未知", "\n".join(res.lines))

    def test_reset_after_failed_check_uses_check_timeout(self):
        self.approve_final("b", 1)
        self.set_timeout(77)
        spy = Spy()
        with mock.patch.object(probe, "_git", spy):
            res = merge.run(self.repo, check_command="python3 -c 'raise SystemExit(1)'")
        self.assertEqual(res.code, 5, res.lines)
        self.assertEqual(spy.timeout_of("reset", "-q", "--hard"), [77])


class SyncTimeoutTest(TimeoutCase):
    def commit_on_main(self):
        (self.repo / "shared.txt").write_text("a\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "main: shared")

    def test_sync_merge_times_out(self):
        self.commit_on_main()
        before = git(self.wt["b"], "rev-parse", "HEAD")
        self.slow_hook("pre-merge-commit")
        res = sync.run(self.wt["b"])
        self.assertEqual(res.code, 4, res.lines)
        self.assertIn("超时（1 秒）", "\n".join(res.lines))
        self.assertEqual(git(self.wt["b"], "rev-parse", "HEAD"), before)
        self.assertEqual(git(self.wt["b"], "status", "--porcelain"), "")
        self.assert_no_leftover()

    def test_sync_uses_check_timeout(self):
        self.commit_on_main()
        self.set_timeout(555)
        spy = Spy()
        with mock.patch.object(probe, "_git", spy):
            res = sync.run(self.wt["b"])
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(spy.timeout_of("merge", "--no-edit"), [555])


if __name__ == "__main__":
    unittest.main()
