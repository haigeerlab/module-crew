"""S28 follow-up (T136): record a merge after a wrap-up timeout, set checkTimeout, bounded output wait, commit durations."""

import os
import subprocess
import time
import unittest
from unittest import mock

from helpers import git
from test_commit_timeout import TimeoutCase
from test_merge_pilot import todo

from module_crew import changes, merge, probe, review, store


class RecordMergeTest(TimeoutCase):
    def timed_out_wrap_up(self):
        todo(self.wt["b"], "b", (True, "Task 1"), (False, "最终验收（gate）"))
        n = self.approve_final("b", 1)
        self.slow_hook("pre-commit")                      # the tick commit times out, the merge commit stands
        res = merge.run(self.repo, check_command="python3 -c pass")
        self.assertEqual(res.code, 4, res.lines)
        os.remove(self.repo / ".git" / "hooks" / "pre-commit")
        return n, res

    def test_timeout_names_record_and_record_closes_the_approval(self):
        n, res = self.timed_out_wrap_up()
        self.assertIn(f"module-crew merge record C{n} --original-file <原话文件>", "\n".join(res.lines))
        done = merge.record(self.repo, n, "合并已经做成了，补记")
        self.assertEqual(done.code, 0, done.lines)
        rec = store.get(self.db, "item", str(n))
        self.assertEqual((rec["state"], rec["closedReason"], rec["mergeCommit"]), ("closed", "merged", res.merge_commit))
        self.assertIn("wrap-up", [x["kind"] for x in done.sends])
        text = "\n".join(done.lines)
        self.assertIn(f"C{n}（b）已补记合并：合并提交 {res.merge_commit[:7]} 在集成分支上", text)
        self.assertIn("merge tick b", text)               # the tick did not happen: say how to finish it
        self.assertEqual(merge.queue(self.repo), [])
        again = merge.record(self.repo, n, "再补一次")
        self.assertEqual(again.code, 3, again.lines)

    def test_record_refused_when_not_merged(self):
        n = self.approve_final("b", 1)
        res = merge.record(self.repo, n, "补记")
        self.assertEqual(res.code, 3, res.lines)
        self.assertIn("上没有合入交审提交", "\n".join(res.lines))
        self.assertEqual(store.get(self.db, "item", str(n))["state"], "open")

    def test_record_refused_without_words(self):
        n, _ = self.timed_out_wrap_up()
        self.assertEqual(merge.record(self.repo, n, "  ").code, 3)
        self.assertEqual(store.get(self.db, "item", str(n))["state"], "open")

    def test_record_cli(self):
        n, _ = self.timed_out_wrap_up()
        words = self.tmp / "words.txt"
        words.write_text("补记合并", encoding="utf-8")
        out = self.run_cli("merge", "record", f"C{n}", "--original-file", str(words), cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(store.get(self.db, "item", str(n))["closedReason"], "merged")


class ConfigSetTimeoutTest(TimeoutCase):
    def test_set_check_timeout(self):
        out = self.run_cli("config", "set", "--check-timeout", "900", "--original", "检查时限改成 900 秒", cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        cfg = store.get(self.db, "config", "main")
        self.assertEqual(cfg["checkTimeout"], 900)
        self.assertEqual(merge.commit_timeout(cfg), 900)
        self.assertIn("900", out.stdout)

    def test_bad_timeout_refused(self):
        before = store.get(self.db, "config", "main")
        out = self.run_cli("config", "set", "--check-timeout", "0", "--original", "改", cwd=self.repo)
        self.assertNotEqual(out.returncode, 0)
        out = self.run_cli("config", "set", "--original", "改", cwd=self.repo)
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(store.get(self.db, "config", "main"), before)


class OutputWaitTest(TimeoutCase):
    def test_daemon_holding_the_pipe_does_not_block(self):
        # the daemon leaves git's process group (setsid) but keeps the hook's stderr, i.e. git's pipe, open
        path = self.repo / ".git" / "hooks" / "pre-commit"
        path.write_text(f'#!/bin/sh\npython3 -c "import os, time; os.setsid(); time.sleep(30)" {self.token} &\n'
                        f'python3 -c "import time; time.sleep(5)" {self.token}\n', encoding="utf-8")
        os.chmod(path, 0o755)
        start = time.monotonic()
        with mock.patch.object(probe, "OUTPUT_WAIT", 1):
            with self.assertRaises(subprocess.TimeoutExpired):
                probe._git(self.repo, "commit", "--allow-empty", "-q", "-m", "x", timeout=1)
        self.assertLess(time.monotonic() - start, 10)
        self.assertFalse((self.repo / ".git" / "index.lock").exists())


class CommitDurationTest(TimeoutCase):
    def test_land_and_approve_report_duration(self):
        self.set_timeout(30)
        n = self.land_request(1)
        res = changes.land(self.repo, n)
        self.assertEqual(res.code, 0, res.lines)
        self.assertRegex("\n".join(res.lines), r"提交用时 \d+\.\d 秒（时限 30 秒）")
        s = review.add(self.db, self.spec_review("b"), "shop-b", 2).number
        res = review.approve(self.repo, [s], "批")
        self.assertEqual(res.code, 0, res.lines)
        self.assertRegex("\n".join(res.lines), r"提交用时 \d+\.\d 秒（时限 30 秒）")

    def test_timeout_reports_duration(self):
        n = self.land_request(1)
        self.slow_hook("pre-commit")
        res = changes.land(self.repo, n)
        self.assertEqual(res.code, 4, res.lines)
        self.assertRegex("\n".join(res.lines), r"超时（1 秒），实际用时 \d+\.\d 秒")

    def test_approve_timeout_reports_duration(self):
        self.slow_hook("pre-commit")
        s = review.add(self.db, self.spec_review("b"), "shop-b", 2).number
        res = review.approve(self.repo, [s], "批")
        self.assertEqual(res.code, 4, res.lines)
        self.assertRegex("\n".join(res.lines), r"超时（1 秒），实际用时 \d+\.\d 秒")


if __name__ == "__main__":
    unittest.main()
