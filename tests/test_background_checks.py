"""crew-background-checks: one merge at a time while it runs in the background (see spec/crew-background-checks.md)."""

from __future__ import annotations

import json
import os
import socket
import unittest

from helpers import MergeCase, git

from module_crew import mergelock, store


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
        self.assertEqual((info["approval"], info["unit"], info["pid"], info["host"]), (12, "b", os.getpid(), socket.gethostname()))
        self.assertIsInstance(mergelock.acquire(self.db, 13, "c"), mergelock.Held)
        mergelock.release(self.db, lock)
        self.assertIsNone(mergelock.read(self.db))
        mergelock.release(self.db, lock)              # releasing twice is harmless

    def test_release_only_own(self):
        lock = mergelock.acquire(self.db, 12, "b")
        other = mergelock.Lock(12, "b", os.getpid() + 1, lock.started_at)
        mergelock.release(self.db, other)
        self.assertIsNotNone(mergelock.read(self.db))

    def write(self, **over):
        info = {"approval": 9, "unit": "b", "pid": os.getpid(), "host": socket.gethostname(), "startedAt": store.now(), **over}
        (self.db.path / "merge.lock").write_text(json.dumps(info), encoding="utf-8")

    def test_guard_live_lock(self):
        self.write()
        reason, note = mergelock.guard(self.db, self.repo)
        self.assertIn("合并 C9（b）正在后台跑", reason)

    def test_stale_lock_cleared_when_clean(self):
        self.write(pid=dead_pid())
        reason, note = mergelock.guard(self.db, self.repo)
        self.assertIsNone(reason)
        self.assertIn("失效", note)
        self.assertIsNone(mergelock.read(self.db))

    def test_stale_lock_kept_when_dirty_or_mid_merge(self):
        self.write(pid=dead_pid())
        (self.repo / "half.txt").write_text("x")
        reason, _ = mergelock.guard(self.db, self.repo)
        self.assertIn("不干净", reason)
        self.assertIsNotNone(mergelock.read(self.db))

    def test_other_host_not_cleared(self):
        self.write(pid=dead_pid(), host="another-mac")
        reason, _ = mergelock.guard(self.db, self.repo)
        self.assertIn("another-mac", reason)
        self.assertIsNotNone(mergelock.read(self.db))


if __name__ == "__main__":
    unittest.main()
