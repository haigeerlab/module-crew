"""crew-background-checks: one merge at a time while it runs in the background (see spec/crew-background-checks.md)."""

from __future__ import annotations

import fcntl
import json
import os
import socket
import subprocess
import sys
import time
import unittest

from helpers import PLUGIN_ROOT, MergeCase, git

from module_crew import merge, mergelock, store


def dead_pid() -> int:
    pid = 999_999
    while True:
        try:
            os.kill(pid, 0)
            pid -= 1
        except ProcessLookupError:
            return pid
        except PermissionError:
            pid -= 1


class LockTest(MergeCase):
    """Acceptance 1 (the lock itself), 3."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def test_acquire_release(self):
        lock = mergelock.acquire(self.db, 12, "b")
        info = mergelock.read(self.db)
        self.assertEqual((info["approval"], info["unit"], info["pid"]), (12, "b", os.getpid()))
        self.assertTrue(mergelock.locked(self.db))
        self.assertIsInstance(mergelock.acquire(self.db, 13, "c"), mergelock.Held)
        mergelock.release(self.db, lock)
        self.assertIsNone(mergelock.read(self.db))
        self.assertFalse(mergelock.locked(self.db))
        mergelock.release(self.db, lock)              # releasing twice is harmless
        self.assertTrue((self.db.path / "merge.lock").exists())      # nothing is deleted

    def test_guard_live_lock(self):
        lock = mergelock.acquire(self.db, 9, "b")
        self.addCleanup(mergelock.release, self.db, lock)
        reason, note = mergelock.guard(self.db, self.repo)
        self.assertIn("合并 C9（b）正在后台跑", reason)

    def stale_record(self):
        info = {"running": True, "approval": 9, "unit": "b", "pid": dead_pid(), "host": socket.gethostname(),
                "startedAt": store.now()}
        (self.db.path / "merge-running.json").write_text(json.dumps(info), encoding="utf-8")

    def test_stale_lock_cleared_when_clean(self):
        self.stale_record()
        reason, note = mergelock.guard(self.db, self.repo)
        self.assertIsNone(reason)
        self.assertIn("失效", note)
        self.assertIsNone(mergelock.read(self.db))

    def test_stale_lock_kept_when_dirty_or_mid_merge(self):
        self.stale_record()
        (self.repo / "half.txt").write_text("x")
        reason, _ = mergelock.guard(self.db, self.repo)
        self.assertIn("不干净", reason)
        self.assertIsNotNone(mergelock.read(self.db))

    def test_lock_goes_with_the_process(self):
        child = subprocess.run([sys.executable, "-c", (
            "import sys; sys.path.insert(0, %r)\n"
            "from module_crew import mergelock, store\n"
            "mergelock.acquire(store.open_store(%r), 7, 'c')\n") % (str(PLUGIN_ROOT), str(self.repo))])
        self.assertEqual(child.returncode, 0)
        self.assertFalse(mergelock.locked(self.db))                   # the system let go when the process ended
        self.assertTrue(mergelock.stale(self.db, mergelock.read(self.db)))


class MergeRunLockTest(MergeCase):
    """Acceptance 1, 2: merge run holds the lock while it runs and always lets it go."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def background_run(self, check):
        """`merge run` in another process; returns once its lock file exists."""
        proc = subprocess.Popen([str(PLUGIN_ROOT / "bin" / "module-crew"), "merge", "run", "--check-command", check],
                                cwd=self.repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        deadline = time.time() + 30
        while mergelock.read(self.db) is None and time.time() < deadline:
            time.sleep(0.05)
        self.assertIsNotNone(mergelock.read(self.db), "the background merge never took the lock")
        return proc

    def test_lock_held_and_released(self):
        approval = self.approve_final("b", 5100)
        proc = self.background_run(self.check_script(sleep=4))
        info = mergelock.read(self.db)
        self.assertEqual((info["approval"], info["unit"]), (approval, "b"))
        second = self.run_cli("merge", "run")
        self.assertEqual(second.returncode, 6, second.stdout + second.stderr)
        self.assertIn("正在后台跑", second.stdout + second.stderr)
        out, err = proc.communicate(timeout=120)
        self.assertEqual(proc.returncode, 0, out + err)
        self.assertIsNone(mergelock.read(self.db))

    def test_released_on_every_ending(self):
        self.approve_final("b", 5101, path="BROKEN")
        self.assertEqual(merge.run(self.repo, check_command=self.check_script(fail_if="BROKEN")).code, 5)   # returned
        self.assertIsNone(mergelock.read(self.db))
        self.approve_final("c", 5102)
        original = merge._run_check
        def boom(*a, **k):
            raise RuntimeError("检查进程崩了")
        merge._run_check = boom
        self.addCleanup(setattr, merge, "_run_check", original)
        with self.assertRaises(RuntimeError):
            merge.run(self.repo)
        self.assertIsNone(mergelock.read(self.db))


class GuardedCommandsTest(MergeCase):
    """Acceptance 2, 3: the other writing commands refuse while a merge runs; reading commands do not."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        lock = mergelock.acquire(self.db, 9, "b")
        self.addCleanup(mergelock.release, self.db, lock)
        self.words = self.tmp / "w.txt"
        self.words.write_text("同意", encoding="utf-8")

    def test_writing_commands_refused(self):
        before = (len(store.events(self.db)), git(self.repo, "rev-parse", "HEAD"))
        for args in (("change", "land", "1"), ("review", "approve", "1", "--original-file", str(self.words)),
                     ("merge", "tick", "b", "--original-file", str(self.words)),
                     ("merge", "cleanup", "b", "--original-file", str(self.words)),
                     ("unqueued", "--notify"), ("coordinator", "down", "--original-file", str(self.words))):
            with self.subTest(args=args):
                out = self.run_cli(*args)
                self.assertEqual(out.returncode, 6, out.stdout + out.stderr)
                self.assertIn("正在后台跑", out.stdout + out.stderr)
        self.assertEqual((len(store.events(self.db)), git(self.repo, "rev-parse", "HEAD")), before)

    def test_reading_commands_work(self):
        for args in (("status",), ("sessions",), ("review", "batch"), ("task", "list"), ("unqueued",), ("merge", "queue")):
            with self.subTest(args=args):
                self.assertNotEqual(self.run_cli(*args).returncode, 6)


class StatusLockTest(MergeCase):
    """Acceptance 4."""

    def test_status_shows_lock(self):
        db = store.open_store(self.repo)
        held = mergelock.acquire(db, 9, "b")
        self.assertIn("合并 C9（b）正在后台跑", self.run_cli("status").stdout)
        lock = json.loads(self.run_cli("status", "--json").stdout)["store"]["mergeLock"]
        self.assertEqual((lock["approval"], lock["unit"], lock["stale"]), (9, "b", False))
        fcntl.flock(held.fd, fcntl.LOCK_UN)                   # as if the merge process died without cleaning up
        self.assertIn("失效", self.run_cli("status").stdout)
        self.assertIsNotNone(mergelock.read(db))              # status only reads
        os.close(held.fd)

    def test_status_without_lock(self):
        doc = json.loads(self.run_cli("status", "--json").stdout)
        self.assertIsNone(doc["store"]["mergeLock"])


if __name__ == "__main__":
    unittest.main()
