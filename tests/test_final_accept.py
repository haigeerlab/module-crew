"""crew-final-accept-split: accepting a final acceptance without authorizing the merge (spec/crew-final-accept-split.md)."""

import unittest
from pathlib import Path

from helpers import MergeCase, git

from module_crew import failure, hooks, merge, protocol, review, store


class AcceptCase(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def final(self, m: str, rid: int) -> int:
        out = review.add(self.db, self.finish(m), f"shop-{m}", rid)
        assert out.code == 0, out.lines
        return out.number


class AcceptTest(AcceptCase):
    """AC1, AC3."""

    def test_accept_keeps_item_open_and_unqueued(self):
        n = self.final("b", 4800)
        head = git(self.repo, "rev-parse", "HEAD").strip()
        res = merge.accept(self.db, n, "有限验收通过，暂不合并")
        rec = store.get(self.db, "item", str(n))
        self.assertEqual(rec["state"], "accepted")
        self.assertEqual(rec["acceptance"]["original"], "有限验收通过，暂不合并")
        self.assertEqual(merge.queue(self.repo), [])
        self.assertFalse(any(v.get("kind") == "merge-approval" for v in store.records(self.db, "item").values()))
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), head)
        reply = protocol.parse(store.read_body(self.db, res.body))
        self.assertTrue(reply.ok, reply.problems)
        self.assertEqual(reply.kind, "user-reply")
        self.assertEqual(res.reply_to, 4800)
        self.assertEqual(rec["acceptance"]["body"], res.body)

    def test_refusals_write_nothing(self):
        spec = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        with self.assertRaises(merge.AnswerRefused):
            merge.accept(self.db, spec, "验收")
        n = self.final("b", 2)
        merge.accept(self.db, n, "验收")
        with self.assertRaises(merge.AnswerRefused) as cm:
            merge.accept(self.db, n, "再验收")
        self.assertIn("merge approve", str(cm.exception))
        c = self.final("c", 3)
        merge.approve(self.db, c, "批")
        with self.assertRaises(merge.AnswerRefused):          # closed
            merge.accept(self.db, c, "验收")

    def test_many_all_or_nothing(self):
        b = self.final("b", 1)
        spec = review.add(self.db, self.spec_review("c"), "shop-c", 2).number
        with self.assertRaises(merge.AnswerRefused):
            merge.accept_many(self.db, [b, spec], "验收")
        self.assertEqual(store.get(self.db, "item", str(b))["state"], "open")

    def test_unanswered_question_refused(self):
        n = self.final("b", 1)
        with self.db.transaction(actor="t") as tx:            # a timed-out review asks the user D1
            tx.put("item", str(n), dict(tx.get("item", str(n)), sentAt="2026-01-01T00:00:00+08:00"), action="aged")
        out = self.run_cli("merge", "accept", f"C{n}", "--original", "只验收", cwd=self.repo)
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn("没答全", out.stdout)
        self.assertEqual(store.get(self.db, "item", str(n))["state"], "open")
        out = self.run_cli("merge", "accept", f"C{n}", "--original", f"只验收；C{n}-1 A", cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(store.get(self.db, "item", str(n))["state"], "accepted")

    def test_cli(self):
        n = self.final("b", 1)
        out = self.run_cli("merge", "accept", f"C{n}", "--original", "只验收不合并", cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn(f"C{n} 已接受验收，暂不合并", out.stdout)
        self.assertIn("收件人：shop-b", out.stdout)
        self.assertEqual(store.get(self.db, "item", str(n))["state"], "accepted")
        again = self.run_cli("merge", "accept", f"C{n}", "--original", "再验收", cwd=self.repo)
        self.assertEqual(again.returncode, 3)


class AuthorizeTest(AcceptCase):
    """AC2: a later merge authorization on the accepted item, no resubmission."""

    def check(self):
        script = self.tmp / "check.py"
        script.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
        return f"python3 {script}"

    def test_approve_after_accept_merges(self):
        n = self.final("b", 4800)
        acc = merge.accept(self.db, n, "有限验收通过，暂不合并")
        res = merge.approve(self.db, n, "授权合并 C%d" % n)
        ap = store.get(self.db, "item", str(res.approval))
        self.assertEqual((ap["kind"], ap["state"], ap["review"]), ("merge-approval", "open", n))
        self.assertEqual(ap["acceptedBy"]["body"], acc.body)
        self.assertEqual(ap["answer"]["original"], "授权合并 C%d" % n)
        rec = store.get(self.db, "item", str(n))
        self.assertEqual((rec["state"], rec["closedReason"]), ("closed", "answered"))
        self.assertEqual(rec["answer"]["acceptance"]["original"], "有限验收通过，暂不合并")
        self.assertEqual(rec["answer"]["original"], "授权合并 C%d" % n)
        out = merge.run(self.repo, check_command=self.check())
        self.assertEqual(out.code, 0, out.lines)
        self.assertTrue((self.repo / "src" / "b.py").exists())

    def test_one_step_approve_has_no_accepted_by(self):
        n = self.final("b", 1)
        res = merge.approve(self.db, n, "批准")
        self.assertIsNone(store.get(self.db, "item", str(res.approval))["acceptedBy"])

    def test_cli_does_not_ask_questions_again(self):
        n = self.final("b", 1)
        with self.db.transaction(actor="t") as tx:
            tx.put("item", str(n), dict(tx.get("item", str(n)), sentAt="2026-01-01T00:00:00+08:00"), action="aged")
        self.assertEqual(self.run_cli("merge", "accept", f"C{n}", "--original", f"只验收；C{n}-1 A").returncode, 0)
        out = self.run_cli("merge", "approve", f"C{n}", "--original", "授权合并")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("已排入本地合并队列", out.stdout)


class ReadersTest(AcceptCase):
    """AC4, AC5: batch, sync, resubmission and review answer see the accepted item."""

    def test_not_in_batch_or_for_hub(self):
        n = self.final("b", 1)
        merge.accept(self.db, n, "只验收")
        self.assertNotIn(n, [i["number"] for i in review.batch(self.repo)["items"]])
        self.assertEqual(review.for_hub(self.repo), [])

    def test_no_sync_notice(self):
        n = self.final("b", 1)
        merge.accept(self.db, n, "只验收")
        with self.db.transaction(actor="t") as tx:
            self.assertIn("b", merge.no_sync(tx))
            self.assertNotIn("b", [name.removeprefix("shop-") for name, _ in merge.sync_targets(tx)])

    def test_resubmission_supersedes(self):
        n = self.final("b", 1)
        merge.accept(self.db, n, "只验收")
        out = review.add(self.db, self.finish("b", content="VALUE = 2\n"), "shop-b", 2)
        self.assertIn(n, out.closed)
        rec = store.get(self.db, "item", str(n))
        self.assertEqual((rec["state"], rec["closedReason"]), ("closed", "superseded"))
        with self.assertRaises(merge.AnswerRefused):
            merge.approve(self.db, n, "授权合并")

    def test_review_answer_sends_back(self):
        n = self.final("b", 1)
        merge.accept(self.db, n, "只验收")
        reply = review.answer(self.db, n, "还是要改：补错误提示")
        rec = store.get(self.db, "item", str(n))
        self.assertEqual((rec["state"], rec["closedReason"]), ("closed", "answered"))
        self.assertEqual(reply.to, "shop-b")


class StageTest(AcceptCase):
    """AC6: the module's stage, the export, status and the stall facts."""

    def test_stage_and_export(self):
        n = self.final("b", 1)
        merge.accept(self.db, n, "只验收")
        text = hooks._stage(store.records(self.db, "item"), "b", store.records(self.db, "session"))
        self.assertEqual(text, hooks.STAGE_ACCEPTED.format(n=n))
        self.assertIn("不要再提交", text)
        row = {r["module"]: r for r in failure.sessions(self.db)}["b"]
        self.assertEqual(row["stage"], failure.stage_code(hooks.STAGE_WAIT_FINAL.format(n=n)))

    def test_status_line(self):
        n = self.final("b", 1)
        merge.accept(self.db, n, "只验收")
        out = self.run_cli("status")
        self.assertIn(f"b 已接受验收、待授权合并（C{n}，接受于 ", out.stdout)

    def test_stall_counts_the_acceptance_as_an_answer(self):
        n = self.final("b", 1)
        merge.accept(self.db, n, "只验收")
        at = store.get(self.db, "item", str(n))["acceptance"]["answeredAt"]
        row = {r["module"]: r for r in failure.sessions(self.db)}["b"]
        self.assertEqual([(a["node"], a["refs"], a["lastAt"]) for a in row["asks"]], [("final", [f"C{n}"], at)])
        self.assertIn(at, [a["at"] for a in row["answers"]])


class CleanupTest(AcceptCase):
    """AC9 (D2 A): an accepted, unauthorized module keeps its worktree."""

    def test_cleanup_refused(self):
        n = self.final("b", 1)
        merge.accept(self.db, n, "只验收")
        res = merge.cleanup(self.repo, "b", "收回 b")
        self.assertEqual(res.code, 3, res.lines)
        self.assertIn(f"已接受验收、待授权合并（C{n}）", " ".join(res.lines))
        self.assertTrue(self.wt["b"].is_dir())


class HintsTest(AcceptCase):
    """AC7, AC8 (D1 A)."""

    def test_review_approve_refusal_names_three_commands(self):
        n = self.final("b", 1)
        res = review.approve(self.repo, [n], "批")
        self.assertEqual(res.code, 3)
        text = " ".join(res.lines)
        for cmd in ("merge approve", "merge accept", "review answer"):
            self.assertIn(cmd, text)

    def test_review_answer_on_final_hints(self):
        n = self.final("b", 1)
        out = self.run_cli("review", "answer", f"C{n}", "--original", "补错误提示")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("已按要求修改退回", out.stdout)
        self.assertIn("merge accept", out.stdout)
        spec = review.add(self.db, self.spec_review("c"), "shop-c", 2).number
        out = self.run_cli("review", "answer", f"C{spec}", "--original", "Spec 再改")
        self.assertNotIn("merge accept", out.stdout)

    def test_final_card_has_option_c(self):
        self.final("b", 1)
        [(_, _, text)] = review.for_hub(self.repo)
        msg = protocol.parse(text)
        self.assertTrue(msg.ok, msg.problems)
        options = msg.fields["选项与我的建议"]
        self.assertIn("C：只接受验收，暂不授权合并", options)
        self.assertIn("之后你说一句授权合并就排进合并队列", options)
        self.assertEqual(msg.fields["你该回"].strip(), "A")

    def test_spec_card_unchanged(self):
        review.add(self.db, self.spec_review("b"), "shop-b", 1)
        [(_, _, text)] = review.for_hub(self.repo)
        self.assertNotIn("只接受验收", text)


ROOT = Path(__file__).resolve().parent.parent


class DocsTest(unittest.TestCase):
    """AC10, AC11: the four skills and the two docs."""

    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_coordinator_skills(self):
        for rel in ("skills/crew-coordinator/SKILL.md", "codex-skills/crew-coordinator/SKILL.md"):
            text = self.read(rel)
            self.assertNotIn("**批准一律走 `review approve`**", text, rel)
            self.assertNotIn("批准即授权合入", text, rel)
            self.assertIn("Spec、Plan、接口提案的批准一律走 `review approve`", text, rel)
            self.assertIn("module-crew merge accept <交审编号>… --original-file <原话文件>", text, rel)
            self.assertIn("只接受验收、不批合并", text, rel)
            self.assertIn("不往大里读", text, rel)
            self.assertIn("不用模块重新交审", text, rel)
            self.assertIn("对最终验收只用于要求修改", text, rel)

    def test_coordinator_skills_match(self):
        def part(rel):
            text = self.read(rel)
            return text[text.index("2. 按用户原话分三种"):text.index("   合入并通过检查后")]
        self.assertEqual(part("skills/crew-coordinator/SKILL.md"), part("codex-skills/crew-coordinator/SKILL.md"))

    def test_codex_sandbox_list_has_accept(self):
        self.assertIn("merge approve|accept|run", self.read("codex-skills/crew-coordinator/SKILL.md"))

    def test_dev_skills(self):
        for rel in ("skills/crew-dev/SKILL.md", "codex-skills/crew-dev/SKILL.md"):
            self.assertIn("只接受验收、暂不授权合并", self.read(rel), rel)

    def test_docs(self):
        self.assertIn("`merge accept <交审号>… --original(-file)`", self.read("docs/commands.md"))
        self.assertIn("要求修改（退回）", self.read("docs/commands.md"))
        self.assertIn("只接受验收、暂不合并", self.read("docs/guide.md"))


if __name__ == "__main__":
    unittest.main()
