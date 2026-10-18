import unittest

from helpers import ReviewCase, git

from module_crew import protocol, review, store


class AnswerTest(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        self.n = review.add(self.db, self.spec_review("b"), "shop-b", 4600).number

    def test_answer_only_replies(self):
        head = git(self.repo, "rev-parse", "HEAD")
        reply = review.answer(self.db, self.n, "第 3 节的接口要改")
        text = store.read_body(self.db, reply.body)
        msg = protocol.parse(text)
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual(msg.fields["用户原话"], "第 3 节的接口要改")
        self.assertEqual((reply.to, reply.reply_to), ("shop-b", 4600))
        rec = store.get(self.db, "item", str(self.n))
        self.assertEqual((rec["state"], rec["closedReason"]), ("closed", "answered"))
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)

    def test_answer_refused(self):
        review.answer(self.db, self.n, "好")
        with self.assertRaises(review.AnswerRefused):
            review.answer(self.db, self.n, "再答")
        with self.assertRaises(review.AnswerRefused):
            review.answer(self.db, 999, "x")


if __name__ == "__main__":
    unittest.main()


def snapshot(case):
    files = {str(p): p.read_bytes() for p in case.repo.rglob("*") if p.is_file() and "/.git/" not in str(p)}
    db = store.open_store(case.repo)
    stored = {str(p): p.read_bytes() for p in db.path.rglob("*") if p.is_file() and p.name != ".lock"}
    return files, stored, git(case.repo, "rev-parse", "HEAD")


class ApproveTest(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def add(self, text, sender, rid):
        out = review.add(self.db, text, sender, rid)
        self.assertEqual(out.code, 0, out.lines)
        return out.number

    def test_approve_spec_and_plan(self):
        s = self.add(self.spec_review("b"), "shop-b", 4600)
        p = self.add(self.plan_review("b"), "shop-b", 4601)
        before = git(self.repo, "rev-parse", "HEAD").strip()
        res = review.approve(self.repo, [s, p], "b 的 Spec 和 Plan 都批准")
        self.assertEqual(res.code, 0, res.lines)
        log = git(self.repo, "log", "--format=%H %s", f"{before}..HEAD").strip().splitlines()
        self.assertEqual(len(log), 1)
        self.assertIn(f"C{res.approval}", log[0])
        changed = git(self.repo, "diff", "--name-only", before, "HEAD").split()
        self.assertEqual(sorted(changed), ["spec/b.md", "tasks/b/plan.md", "tasks/b/todo.md"])   # todo travels with the Plan
        spec = (self.repo / "spec" / "b.md").read_text()
        self.assertTrue(spec.startswith("<!-- spec-guard: review approved fakedigest -->\n# Spec: b"))
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        approval = store.get(self.db, "item", str(res.approval))
        self.assertEqual((approval["kind"], approval["reviews"], approval["baselineCommit"]),
                         ("review-approval", [s, p], res.commit))
        for n in (s, p):
            self.assertEqual(store.get(self.db, "item", str(n))["closedReason"], "answered")
        replies = [x for x in res.sends if x["kind"] == "user-reply"]
        notices = [x for x in res.sends if x["kind"] == "coordination-notice"]
        self.assertEqual(sorted(r["replyTo"] for r in replies), [4600, 4601])
        self.assertEqual(len(notices), 1)
        notice = protocol.parse(store.read_body(self.db, notices[0]["body"]))
        self.assertTrue(notice.ok, notice.problems)
        self.assertEqual(notice.contract()["notice"], {"kind": "start", "refs": [], "localRefs": [f"C{res.approval}"]})
        self.assertIn(f"C{res.approval}", notice.fields["依据"])                          # the coordinator's own approval
        self.assertEqual(notices[0]["to"], "shop-b")
        reply = protocol.parse(store.read_body(self.db, replies[0]["body"]))
        self.assertEqual(reply.fields["用户原话"], "b 的 Spec 和 Plan 都批准")

    def test_notice_only_when_both_approved(self):
        s = self.add(self.spec_review("c"), "shop-c", 1)
        res = review.approve(self.repo, [s], "c 的 Spec 批准")
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual([x["kind"] for x in res.sends], ["user-reply"])
        p = self.add(self.plan_review("c"), "shop-c", 2)
        res = review.approve(self.repo, [p], "c 的 Plan 也批准")
        self.assertEqual(sorted(x["kind"] for x in res.sends), ["coordination-notice", "user-reply"])

    def assert_refused(self, numbers, words):
        before = snapshot(self)
        res = review.approve(self.repo, numbers, "批准")
        self.assertEqual(res.code, 3, res.lines)
        self.assertIn(words, " ".join(res.lines))
        self.assertEqual(snapshot(self), before)

    def test_refusals(self):
        s = self.add(self.spec_review("b"), "shop-b", 10)
        review.answer(self.db, s, "要改")
        self.assert_refused([s], "已关闭")
        final = ("【交审】\n结束：无\n模块：b\n节点：最终验收\n文件：\n"
                 + self.spec_review("b").split("文件：\n")[1].split("要点：")[0]
                 + "要点：\n验收标准与证据：\n1：无\n\n- 一\n- 二\n改动统计：1 file\n越界检查：无越界\n")
        f = self.add(final, "shop-b", 11)
        self.assert_refused([f], "最终验收")
        s2 = self.add(self.spec_review("b"), "shop-b", 12)
        (self.repo / "dirty.txt").write_text("x")
        self.assert_refused([s2], "集成分支所在的 checkout 不干净")
        (self.repo / "dirty.txt").unlink()
        from helpers import spec_guard_interface
        self.plugins.entries.pop("spec-guard@m")
        self.plugins.install("spec-guard", spec_guard_interface("1.1", review_mark=["sh", "-c", "true"]), map_script=True)
        self.assert_refused([s2], "不安全")
        self.plugins.entries.pop("spec-guard@m")
        old_style = ["python3", "-B", "hooks/review_mark.py", "--project", "<project-root>", "--module", "<module-id>",
                     "--target", "<target>", "--state", "<state>"]
        self.plugins.install("spec-guard", spec_guard_interface("1.1", review_mark=old_style), map_script=True)
        self.assert_refused([s2], "不认识的占位符")

    def test_failure_part_way(self):
        import os
        b = self.add(self.spec_review("b"), "shop-b", 20)
        c = self.add(self.spec_review("c"), "shop-c", 21)
        _, stored, head = snapshot(self)
        os.environ["FAKE_REVIEW_FAIL"] = "c"
        try:
            res = review.approve(self.repo, [b, c], "都批准")
        finally:
            os.environ.pop("FAKE_REVIEW_FAIL")
        self.assertEqual(res.code, 4, res.lines)
        self.assertIn("spec/c.md", " ".join(res.lines))
        _, stored_after, head_after = snapshot(self)
        self.assertEqual((stored_after, head_after), (stored, head))
        self.assertIn("spec/", git(self.repo, "status", "--porcelain"))


class CliTest(ReviewCase):
    def test_add_batch_approve(self):
        f = self.tmp / "r.txt"
        f.write_text(self.spec_review("b"), encoding="utf-8")
        r = self.run_cli("review", "add", str(f), "--from", "shop-b", "--relay-id", "4600")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        f.write_text(self.plan_review("b"), encoding="utf-8")
        self.run_cli("review", "add", str(f), "--from", "shop-b", "--relay-id", "4601")
        r = self.run_cli("review", "batch")
        self.assertEqual(r.returncode, 0)
        self.assertIn("b 的 Spec", r.stdout)
        nums = [i["number"] for i in __import__("json").loads(self.run_cli("review", "batch", "--json").stdout)["items"]]
        r = self.run_cli("review", "approve", *map(str, nums), "--original", "都批准")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.count("发送 【用户答复】"), 2)
        self.assertEqual(r.stdout.count("发送 【协调通知】"), 1)
        self.assertEqual(self.run_cli("review", "batch").returncode, 3)

    def test_inbox_still_returns_4(self):
        f = self.tmp / "r.txt"
        f.write_text(self.spec_review("b"), encoding="utf-8")
        r = self.run_cli("inbox", "add", str(f), "--from", "shop-b", "--relay-id", "1")
        self.assertEqual(r.returncode, 4)


class SyncAfterApprovalTest(ReviewCase):
    """Regression: the approved copies carry a review marker, so syncing the baseline conflicts (add/add)
    unless the module takes the integration branch's version, as the start notice now says."""

    def test_notice_says_take_theirs_and_that_works(self):
        db = store.open_store(self.repo)
        s = review.add(db, self.spec_review("b"), "shop-b", 1).number
        p = review.add(db, self.plan_review("b"), "shop-b", 2).number
        res = review.approve(self.repo, [s, p], "批")
        notice = [x for x in res.sends if x["kind"] == "coordination-notice"][0]
        todo = protocol.parse(store.read_body(db, notice["body"])).fields["要你做什么"]
        self.assertIn("冲突时取集成分支的版本", todo)
        plain = __import__("subprocess").run(["git", "-C", str(self.wt["b"]), "merge", "--no-edit", "main"],
                                             capture_output=True, text=True)
        self.assertNotEqual(plain.returncode, 0)                       # the add/add conflict is real
        git(self.wt["b"], "checkout", "--theirs", "--", "spec/b.md", "tasks/b/plan.md")
        git(self.wt["b"], "add", "-A")
        git(self.wt["b"], "commit", "-q", "--no-edit")
        self.assertEqual((self.wt["b"] / "spec" / "b.md").read_text(), (self.repo / "spec" / "b.md").read_text())
