"""crew-takeover-merge: merge stage one for modules whose takeover says merge=auto — Codex reviews the final patch,
module-crew releases and merges it locally, records the first stage for autopilot (see spec/crew-takeover-merge.md)."""

import hashlib
import json
import os
import subprocess
import unittest
from pathlib import Path

from helpers import git

from module_crew import review, store
from test_autonomy_tier import TierMixin
from test_check_ledger import LedgerCase
from test_takeover_approve import FAKE_MARK_115, REVIEW_MARK_115, TakeoverMixin, finding, takeover_row


def final_report(worktree: Path, base: str, head: str, findings=(), status="completed", outcome=None,
                 backend="codex", files: dict | None = None, to: str | None = None) -> dict:
    """A /delegate:review report over base..head (commits mode) as delegate 1.5 writes it."""
    if files is None:
        names = subprocess.run(["git", "-C", str(worktree), "diff", "--name-only", base, head],
                               capture_output=True, text=True, check=True).stdout.split()
        files = {}
        for name in names:
            shown = subprocess.run(["git", "-C", str(worktree), "show", f"{head}:{name}"], capture_output=True)
            if shown.returncode == 0:
                files[name] = hashlib.sha256(shown.stdout).hexdigest()
    return {"schema_version": 1, "execution_status": status, "backend": backend,
            "review_outcome": outcome or ("findings" if findings else "no_findings_in_scope"),
            "scope": {"paths": [], "baseline": {"mode": "commits", "from": base, "to": to or head},
                      "fingerprint": "blob-pairs-v1:fake", "files": files},
            "unreviewed": [], "findings": list(findings), "recheck": None, "limitations": []}


class FinalCase(TierMixin, TakeoverMixin, LedgerCase):
    """Module b with merge=auto (Spec and Plan approved by the user), check ledger on."""

    merge_value = "auto"
    ledger = True

    def setUp(self):
        super().setUp()
        self.with_takeover()
        root = Path(self.plugins.entries["spec-guard@m"][-1]["installPath"])
        doc = json.loads((root / "interface.json").read_text())
        doc["reviewMark"] = {"command": REVIEW_MARK_115}
        (root / "interface.json").write_text(json.dumps(doc))
        (root / "hooks" / "review_mark.py").write_text(FAKE_MARK_115)
        os.environ["FAKE_MARK_LOG"] = str(self.tmp / "marks.jsonl")
        self.addCleanup(lambda: os.environ.pop("FAKE_MARK_LOG", None))
        self.set_takeover({"merge": self.merge_value}, {"b": takeover_row(merge=self.merge_value)})
        for text, rid in ((self.spec_review("b"), 1), (self.plan_review("b"), 2)):
            n = review.add(self.db, text, "shop-b", rid).number
            res = review.approve(self.repo, [n], "批")
            assert res.code == 0, res.lines
        if self.ledger:
            self.switch_on()
        self.rid = 10

    def submit_final(self, **kw):
        self.rid += 1
        out = review.add(self.db, self.finish("b", **kw), "shop-b", self.rid)
        assert out.code == 0, out.lines
        return out

    def x(self, n: int) -> str:
        return store.get(self.db, "item", str(n))["commit"]

    def base(self, n: int) -> str:
        return git(self.wt["b"], "merge-base", "refs/heads/main", self.x(n)).strip()

    def note(self, n: int, doc: dict) -> tuple[int, str]:
        path = self.tmp / f"final-{len(list(self.tmp.glob('final-*')))}.json"
        path.write_text(json.dumps(doc))
        return self.cli("review", "codex-note", f"C{n}", "--report", str(path))


class JudgeTest(FinalCase):
    """Task 1 (acceptance 1, 2): who handles the final acceptance."""

    def test_auto_goes_to_codex(self):
        out = self.submit_final()
        rec = store.get(self.db, "item", str(out.number))
        self.assertEqual((rec.get("reviewer"), rec.get("sentTo")), ("codex", ["codex"]))
        self.assertIn(f"自动合：下一步 review codex C{out.number}，不提请用户", "\n".join(out.lines))
        self.assertEqual(review.review_state(self.db, out.number), "reviewing")

    def test_plan_not_approved_stays_human(self):
        items = store.records(self.db, "item")
        with self.db.transaction(actor="t") as tx:
            for k, v in items.items():
                if v.get("kind") == "review-approval" and any(items[str(r)].get("node") == "plan" for r in v["reviews"]):
                    tx.put("item", k, dict(v, reviews=[]), action="t")
        out = self.submit_final()
        self.assertIsNone(store.get(self.db, "item", str(out.number)).get("reviewer"))
        self.assertIn("合并档位是自动，但这次照人合：Plan 还没批准", "\n".join(out.lines))


class JudgeLedgerOffTest(FinalCase):
    ledger = False

    def test_ledger_off_stays_human_with_reason(self):
        out = self.submit_final()
        self.assertIsNone(store.get(self.db, "item", str(out.number)).get("reviewer"))
        self.assertIn("合并档位是自动，但这次照人合：项目没开检查记账（checkLedger）", "\n".join(out.lines))


class JudgeHumanTest(FinalCase):
    merge_value = "human"

    def test_human_merge_unchanged(self):
        out = self.submit_final()
        self.assertIsNone(store.get(self.db, "item", str(out.number)).get("reviewer"))
        self.assertFalse(any("合并档位" in x or "自动合" in x for x in out.lines))


class FinalReviewTest(FinalCase):
    """Task 2 (acceptance 3, 4): Codex reviews the final patch."""

    def test_command_reviews_the_commit_range(self):
        n = self.submit_final().number
        code, out = self.cli("review", "codex", f"C{n}")
        self.assertEqual(code, 0, out)
        self.assertIn(f"--base {self.base(n)} --head {self.x(n)}", out)
        self.assertIn("--spec spec/b.md", out)
        self.assertNotIn("--paths", out)
        self.assertIn("验收标准", out)
        self.assertIn("最终验收", out)

    def test_blocking_reworks_then_pass_waits_for_merge_auto(self):
        n = self.submit_final().number
        code, out = self.note(n, final_report(self.wt["b"], self.base(n), self.x(n), [finding("AC3 没做")]))
        self.assertEqual(code, 0, out)
        self.assertIn("返工第 1 轮", out)
        body = [e for e in store.events(self.db, kind="item") if e["type"] == "item.rework-sent"][-1]["data"]["body"]
        self.assertNotIn("review-mark", store.read_body(self.db, body))
        m = self.submit_final(content="VALUE = 'b2'\n").number
        self.assertIn("--previous-report", self.cli("review", "codex", f"C{m}")[1])
        code, out = self.note(m, final_report(self.wt["b"], self.base(m), self.x(m),
                                              [finding("可以更短", severity="suggestion")]))
        self.assertEqual(code, 0, out)
        self.assertIn(f"module-crew merge auto C{m}", out)
        rec = store.get(self.db, "item", str(m))
        self.assertEqual(rec["state"], "open")
        self.assertEqual((rec["codex"]["verdict"], rec["codex"]["rounds"], rec["codex"]["suggestions"]), ("pass", 2, 1))
        self.assertEqual(rec["codex"]["fingerprint"], "blob-pairs-v1:fake")
        self.assertFalse(any(v.get("kind") in ("codex-approval", "merge-approval")
                             for v in store.records(self.db, "item").values()))
        self.assertNotIn("【用户答复】", out)

    def test_over_limit_asks_the_user(self):
        for i in range(3):
            n = self.submit_final(content=f"VALUE = {i}\n").number
            code, out = self.note(n, final_report(self.wt["b"], self.base(n), self.x(n), [finding("仍缺")]))
        self.assertEqual(code, 5, out)
        self.assertIn("你来验收这一版", out)
        self.assertIn("merge approve", out)

    def test_mismatch_refused(self):
        n = self.submit_final().number
        other = git(self.wt["b"], "rev-parse", f"{self.x(n)}^").strip()
        self.assertEqual(self.note(n, final_report(self.wt["b"], self.base(n), self.x(n), to=other))[0], 3)
        self.assertEqual(self.note(n, final_report(self.wt["b"], self.base(n), self.x(n), files={"src/b.py": "0" * 64}))[0], 3)
        self.assertEqual(self.note(n, final_report(self.wt["b"], self.x(n), self.x(n), files={}))[0], 3)
        self.assertIsNone(store.get(self.db, "item", str(n)).get("codex"))

    def test_unavailable_offers_user_acceptance(self):
        n = self.submit_final().number
        code, out = self.note(n, final_report(self.wt["b"], self.base(n), self.x(n), status="failed"))
        self.assertEqual(code, 5, out)
        self.assertIn("这一次由你验收", out)
        self.assertIn("不会改由 Claude 自己审", out)


if __name__ == "__main__":
    unittest.main()
