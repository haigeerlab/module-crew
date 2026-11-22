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
        git(self.wt["b"], "checkout", "refs/heads/main", "--", "spec/b.md", "tasks/b/plan.md")   # as after a sync
        git(self.wt["b"], "commit", "-q", "-m", "b: approval marks from main")
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


class AutoMergeCase(FinalCase):
    def passed(self, **kw) -> int:
        """A final acceptance of b that Codex passed (one suggestion)."""
        n = self.submit_final(**kw).number
        code, out = self.note(n, final_report(self.wt["b"], self.base(n), self.x(n),
                                              [finding("可以更短", severity="suggestion")]))
        assert code == 0, out
        return n

    def kinds(self, kind: str) -> list[dict]:
        return [v for v in store.records(self.db, "item").values() if v.get("kind") == kind]


class MergeAutoTest(AutoMergeCase):
    """Task 3 (acceptance 5) and Task 4 (acceptance 6)."""

    def test_release_merge_and_first_stage(self):
        n = self.passed()
        x = self.x(n)
        code, out = self.cli("merge", "auto", f"C{n}")
        self.assertEqual(code, 0, out)
        self.assertNotIn("【用户答复】", out)
        release = self.kinds("auto-release")
        self.assertEqual(len(release), 1)
        self.assertEqual((release[0]["review"], release[0]["commit"], release[0]["codex"]["suggestions"]), (n, x, 1))
        approval = self.kinds("merge-approval")[0]
        k = next(int(key) for key, v in store.records(self.db, "item").items() if v.get("kind") == "auto-release")
        self.assertEqual((approval["auto"], approval["closedReason"]), (k, "merged"))
        self.assertIn(f"自动放行事项 C{k}", approval["answer"]["original"])
        rec = store.get(self.db, "item", str(n))
        self.assertEqual((rec["state"], rec["closedReason"]), ("closed", "answered"))
        self.assertEqual(self.calls("full"), 1)                 # decision 5: no extra check before the merge
        first = approval["firstStage"]
        tree = git(self.repo, "rev-parse", f"{approval['mergeCommit']}^{{tree}}").strip()
        self.assertEqual((first["integrationBranch"], first["mergeCommit"], first["moduleCommit"], first["tree"]),
                         ("main", approval["mergeCommit"], x, tree))
        self.assertEqual(first["check"], f"{tree}.full")
        self.assertEqual(store.get(self.db, "check", first["check"])["by"], "merge-run")
        self.assertIn("合并第一段完成", out)
        src = Path(review.__file__).parent
        self.assertFalse(any(".autopilot" in f.read_text(encoding="utf-8") for f in src.glob("*.py")))
        self.assertFalse(any(m.get("target") == "acceptance" for m in self.marks()))

    def marks(self):
        log = self.tmp / "marks.jsonl"
        return [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []

    def test_refused_before_codex_passed(self):
        n = self.submit_final().number
        before = store.records(self.db, "item")
        self.assertEqual(self.cli("merge", "auto", f"C{n}")[0], 3)
        self.assertEqual(store.records(self.db, "item"), before)

    def test_refused_after_a_new_commit(self):
        n = self.passed()
        (self.wt["b"] / "src" / "late.py").write_text("X = 1\n")
        git(self.wt["b"], "add", "-A")
        git(self.wt["b"], "commit", "-q", "-m", "late")
        before = store.records(self.db, "item")
        code, out = self.cli("merge", "auto", f"C{n}")
        self.assertEqual(code, 3, out)
        self.assertIn("交审之后又有提交", out)
        self.assertEqual(store.records(self.db, "item"), before)

    def test_refused_when_the_report_changed(self):
        n = self.passed()
        report = Path(store.get(self.db, "item", str(n))["codex"]["report"])
        doc = json.loads(report.read_text())
        doc["scope"]["files"] = {"src/b.py": "0" * 64}
        report.write_text(json.dumps(doc))
        self.assertEqual(self.cli("merge", "auto", f"C{n}")[0], 3)
        self.assertEqual(self.kinds("auto-release"), [])

    def test_failed_check_returns_without_first_stage(self):
        self.switch_on(full=self.counting_script("full", fail_if="src/b.py"))
        n = self.passed()
        code, out = self.cli("merge", "auto", f"C{n}")
        self.assertEqual(code, 5, out)
        approval = self.kinds("merge-approval")[0]
        self.assertEqual(approval["closedReason"], "returned")
        self.assertNotIn("firstStage", approval)
        self.assertEqual(len(self.kinds("auto-release")), 1)     # the release stays on record


class QueueHeadTest(AutoMergeCase):
    def test_other_head_is_merged_first(self):
        from helpers import START_MAP
        doc = json.loads(json.dumps(START_MAP))
        doc["buildOrderGroups"] = [["a"], ["c"], ["b", "d"], ["e"]]
        doc["modules"].sort(key=lambda m: "acbde".index(m["id"]))     # the queue follows the order of modules
        for m in doc["modules"]:
            m.update(takeover_row(merge="auto") if m["id"] == "b" else takeover_row(source="default"))
        self.set_map(doc)
        (self.repo / ".agent" / "config.json").touch()
        c = self.approve_final("c", 50)
        n = self.passed()
        code, out = self.cli("merge", "auto", f"C{n}")
        self.assertEqual(code, 0, out)
        self.assertIn(f"C{c}（c）已合入", out)
        self.assertIn("队列里还有", out)
        self.assertEqual([r["module"] for _, r in __import__("module_crew.merge", fromlist=["queue"]).queue(self.repo)], ["b"])


if __name__ == "__main__":
    unittest.main()
