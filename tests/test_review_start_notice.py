"""S53 (T390): the start notice goes out only when this approval includes the module's Plan, and its 依据 says
what was approved this time and where the rest was approved before."""
import unittest
from pathlib import Path

from helpers import ReviewCase, git
from test_codex_offload import TODO, OffloadCase

from module_crew import protocol, review, store


def notices(db, res):
    return [protocol.parse(store.read_body(db, x["body"])) for x in res.sends if x["kind"] == "coordination-notice"]


class SpecRevisionTest(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def add(self, text, sender, rid):
        out = review.add(self.db, text, sender, rid)
        self.assertEqual(out.code, 0, out.lines)
        return out.number

    def revise_spec(self, m):
        (self.wt[m] / "spec" / f"{m}.md").write_text(f"<!-- spec-guard: review pending -->\n# Spec: {m}\n\n修订\n",
                                                    encoding="utf-8")
        git(self.wt[m], "add", "-A")
        git(self.wt[m], "commit", "-q", "-m", f"{m}: revise spec")

    def test_spec_revision_alone_sends_no_start_notice(self):
        s = self.add(self.spec_review("b"), "shop-b", 1)
        p = self.add(self.plan_review("b"), "shop-b", 2)
        first = review.approve(self.repo, [s, p], "b 的 Spec 和 Plan 都批准")
        self.assertEqual(len(notices(self.db, first)), 1)
        self.revise_spec("b")
        s2 = self.add(self.spec_review("b"), "shop-b", 3)
        res = review.approve(self.repo, [s2], "只批 Spec，不批 Plan 与实施")
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual([x["kind"] for x in res.sends], ["user-reply"])
        text = "\n".join(res.lines)
        self.assertIn("以前批过的 Plan 仍是批准状态", text)
        self.assertIn("/spec-guard:review-mark", text)

    def test_plan_after_spec_says_where_spec_was_approved(self):
        s = self.add(self.spec_review("c"), "shop-c", 1)
        first = review.approve(self.repo, [s], "c 的 Spec 批准")
        p = self.add(self.plan_review("c"), "shop-c", 2)
        res = review.approve(self.repo, [p], "c 的 Plan 也批准")
        [msg] = notices(self.db, res)
        self.assertTrue(msg.ok, msg.problems)
        basis = msg.fields["依据"]
        self.assertIn(f"C{res.approval}（c 的 Plan", basis)
        self.assertIn(f"Spec 以前批准于 C{first.approval}", basis)
        self.assertNotIn("Spec 与 Plan", basis)

    def test_spec_and_plan_together_unchanged(self):
        s = self.add(self.spec_review("b"), "shop-b", 1)
        p = self.add(self.plan_review("b"), "shop-b", 2)
        res = review.approve(self.repo, [s, p], "都批准")
        [msg] = notices(self.db, res)
        self.assertIn(f"C{res.approval}（b 的 Spec 与 Plan）", msg.fields["依据"])


class DeclineBasisTest(OffloadCase):
    def test_decline_notice_basis(self):
        self.switch_on()
        (self.codex_home / "config.toml").write_text(f'[projects."{self.repo}"]\ntrust_level = "untrusted"\n')
        wt = self.wt["b"]
        (wt / "tasks" / "b" / "todo.md").write_text(TODO, encoding="utf-8")
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", "b: todo")
        s = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        first = review.approve(self.repo, [s], "批准 b 的 Spec")
        p = review.add(self.db, self.plan_review("b"), "shop-b", 2).number
        second = review.approve(self.repo, [p], "批准 b 的 Plan")
        self.assertEqual(notices(self.db, second), [])          # held: offload conditions not met
        out = self.run_cli("offload", "decline", "b", "--original", "让模块会话自己做")
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        msg = protocol.parse(Path(out.stdout.split("正文文件：")[1].strip()).read_text(encoding="utf-8"))
        basis = msg.fields["依据"]
        self.assertIn(f"C{second.approval}（b 的 Plan", basis)
        self.assertIn(f"Spec 以前批准于 C{first.approval}", basis)
        self.assertNotIn("Spec 与 Plan", basis)


if __name__ == "__main__":
    unittest.main()
