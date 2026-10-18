import unittest

from helpers import START_MAP, MergeCase, git

from module_crew import merge, protocol, review, store


class ApproveQueueTest(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def test_approve_records_and_replies(self):
        n = review.add(self.db, self.finish("b"), "shop-b", 4800).number
        res = merge.approve(self.db, n, "b 验收通过")
        rec = store.get(self.db, "item", str(res.approval))
        self.assertEqual((rec["kind"], rec["state"], rec["module"], rec["review"]), ("merge-approval", "open", "b", n))
        self.assertEqual(rec["commit"], git(self.wt["b"], "rev-parse", "HEAD").strip())
        self.assertEqual(rec["answer"]["original"], "b 验收通过")
        self.assertEqual(store.get(self.db, "item", str(n))["closedReason"], "answered")
        reply = protocol.parse(store.read_body(self.db, res.reply.body))
        self.assertTrue(reply.ok)
        self.assertEqual(res.reply.reply_to, 4800)

    def test_approve_refusals(self):
        spec = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        with self.assertRaises(merge.AnswerRefused):
            merge.approve(self.db, spec, "批")
        n = review.add(self.db, self.finish("b"), "shop-b", 2).number
        merge.approve(self.db, n, "批")
        with self.assertRaises(merge.AnswerRefused):
            merge.approve(self.db, n, "再批")

    def test_queue_in_build_order(self):
        self.approve_final("c", 10)
        self.approve_final("b", 11)
        self.assertEqual([r["module"] for _, r in merge.queue(self.repo)], ["b", "c"])


def tree(repo, rev="HEAD"):
    return git(repo, "rev-parse", f"{rev}^{{tree}}").strip()


class RunCase(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def state(self):
        files = {str(p): p.read_bytes() for p in self.db.path.rglob("*") if p.is_file() and p.name != ".lock"}
        return git(self.repo, "rev-parse", "HEAD"), files


class PreconditionTest(RunCase):
    def test_no_check_command(self):
        self.approve_final("b", 1)
        self.assertEqual(merge.run(self.repo).code, 2)

    def test_check_command_stored_and_fixed(self):
        self.approve_final("b", 1)
        cmd = self.check_script()
        self.assertEqual(merge.run(self.repo, check_command=cmd).code, 0)
        self.assertEqual(store.get(self.db, "config", "main")["checkCommand"], cmd)
        self.approve_final("c", 2)
        res = merge.run(self.repo, check_command="python3 -c pass")
        self.assertEqual(res.code, 2)
        self.assertIn(cmd, " ".join(res.lines))
        self.assertEqual(merge.run(self.repo, check_command="python3 -c pass", replace=True).code, 0)
        self.assertEqual(store.get(self.db, "config", "main")["checkCommand"], "python3 -c pass")

    def test_empty_queue(self):
        self.assertEqual(merge.run(self.repo, check_command="python3 -c pass").code, 3)
        self.assertNotIn("checkCommand", store.get(self.db, "config", "main"))

    def test_checklist(self):
        cases = {
            "commit after review": lambda: (self.wt["b"] / "late.txt").write_text("x") or git(self.wt["b"], "add", "-A")
            or git(self.wt["b"], "commit", "-q", "-m", "late"),
            "dirty module worktree": lambda: (self.wt["b"] / "dirty.txt").write_text("x"),
            "dirty baseline": lambda: (self.repo / "dirty.txt").write_text("x"),
        }
        for name, spoil in cases.items():
            with self.subTest(name):
                self.setUp()
                self.approve_final("b", 1)
                spoil()
                before = self.state()
                res = merge.run(self.repo, check_command="python3 -c pass")
                self.assertEqual(res.code, 3, res.lines)
                self.assertEqual(self.state(), before)


class MergeTest(RunCase):
    def test_success(self):
        n = self.approve_final("b", 1)
        self.approve_final("c", 2)
        before = git(self.repo, "rev-parse", "HEAD").strip()
        res = merge.run(self.repo, check_command=self.check_script())
        self.assertEqual(res.code, 0, res.lines)
        parents = git(self.repo, "rev-list", "--parents", "-n", "1", "HEAD").split()
        self.assertEqual(len(parents), 3)                       # --no-ff: commit + two parents
        self.assertEqual(parents[1], before)
        self.assertEqual(git(self.repo, "rev-list", "--count", f"{before}..HEAD").strip(), "3")  # merge + b's two commits
        self.assertTrue((self.repo / "src" / "b.py").exists())
        self.assertFalse((self.repo / "src" / "c.py").exists())  # only the head of the queue
        rec = store.get(self.db, "item", str(n))
        self.assertEqual((rec["state"], rec["closedReason"], rec["mergeCommit"]), ("closed", "merged", res.merge_commit))
        kinds = {(x["to"], protocol.parse(store.read_body(self.db, x["body"])).contract()["notice"]["kind"])
                 for x in res.sends}
        self.assertEqual(kinds, {("shop-b", "wrap-up")})  # c is still queued: no sync (pilot fix C)
        for x in res.sends:
            self.assertTrue(protocol.parse(store.read_body(self.db, x["body"])).ok)

    def assert_returned(self, res, n, words):
        self.assertEqual(res.code, 5, res.lines)
        rec = store.get(self.db, "item", str(n))
        self.assertEqual((rec["state"], rec["closedReason"]), ("closed", "returned"))
        self.assertIn(words, rec["reason"])
        notice = [x for x in res.sends if x["to"] == "shop-b"]
        self.assertEqual(len(notice), 1)
        msg = protocol.parse(store.read_body(self.db, notice[0]["body"]))
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual(msg.contract()["notice"], {"kind": "returned", "refs": [n]})
        self.assertIn("重新发最终验收【交审】", msg.fields["要你做什么"])
        return rec, msg

    def test_check_fails_reset(self):
        n = self.approve_final("b", 1)
        before = git(self.repo, "rev-parse", "HEAD").strip()
        res = merge.run(self.repo, check_command=self.check_script(fail_if="src/b.py"))
        rec, msg = self.assert_returned(res, n, "检查失败")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), before)   # no merge, no revert commit (pilot K)
        self.assertEqual((rec["resetTo"], rec.get("revertCommit")), (before, None))
        self.assertIn(before[:7], msg.fields["依据"])

    def test_failed_lines_in_notice(self):
        n = self.approve_final("b", 1)
        script = self.tmp / "fail.py"
        script.write_text("import sys\nprint('..F.')\nprint('FAIL: test_gate (tests.test_gate.T)', file=sys.stderr)\n"
                          "print('ERROR: test_io (tests.test_io.T)', file=sys.stderr)\nsys.exit(1)\n", encoding="utf-8")
        res = merge.run(self.repo, check_command=f"python3 {script}")
        _, msg = self.assert_returned(res, n, "检查失败")
        self.assertIn("FAIL: test_gate", msg.fields["依据"])
        self.assertIn("ERROR: test_io", msg.fields["依据"])

    def test_remerge_after_return_brings_changes(self):
        flag = self.tmp / "gate.flag"
        flag.write_text("x")
        script = self.tmp / "gate.py"
        script.write_text(f"import os, sys\nsys.exit(1 if os.path.exists({str(flag)!r}) else 0)\n", encoding="utf-8")
        n = self.approve_final("b", 1)
        self.assertEqual(merge.run(self.repo, check_command=f"python3 {script}").code, 5)
        git(self.wt["b"], "merge", "-q", "--no-edit", "main")                   # module syncs the baseline
        self.assertTrue((self.wt["b"] / "src" / "b.py").exists())               # sync did not delete its own file
        flag.unlink()
        out = review.add(self.db, self.finish("b", path="src/b2.py"), "shop-b", 2)
        merge.approve(self.db, out.number, "再验收")
        self.assertEqual(merge.run(self.repo).code, 0)
        self.assertTrue((self.repo / "src" / "b.py").exists())
        self.assertTrue((self.repo / "src" / "b2.py").exists())

    def test_head_moved_during_check_not_reset(self):
        n = self.approve_final("b", 1)
        script = self.tmp / "move.py"
        script.write_text("import subprocess, sys\nsubprocess.run(['git', 'commit', '-q', '--allow-empty', '-m', 'moved'])\n"
                          "sys.exit(1)\n", encoding="utf-8")
        res = merge.run(self.repo, check_command=f"python3 {script}")
        self.assertEqual(res.code, 4, res.lines)
        self.assertEqual(git(self.repo, "log", "-1", "--format=%s").strip(), "moved")
        self.assertEqual(store.get(self.db, "item", str(n))["state"], "open")

    def test_check_timeout_reverted(self):
        n = self.approve_final("b", 1)
        with self.db.transaction(actor="t") as tx:
            tx.put("config", "main", dict(tx.get("config", "main"), checkTimeout=1), action="set")
        before = tree(self.repo)
        res = merge.run(self.repo, check_command=self.check_script(sleep=3))
        self.assert_returned(res, n, "超时")
        self.assertEqual(tree(self.repo), before)

    def test_conflict_aborted(self):
        (self.repo / "README.md").write_text("main changed\n")
        git(self.repo, "commit", "-q", "-am", "main edit")
        n = self.approve_final("b", 1, path="README.md", content="b changed\n")
        head = git(self.repo, "rev-parse", "HEAD")
        res = merge.run(self.repo, check_command="python3 -c pass")
        rec, msg = self.assert_returned(res, n, "冲突")
        self.assertIn("README.md", msg.fields["依据"])
        self.assertIsNone(rec["resetTo"])
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
