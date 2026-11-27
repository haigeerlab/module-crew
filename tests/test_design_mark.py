"""crew-design-mark-sync: landing a flow v2 design writes spec-guard's design mark (reviewMark --target design,
interface 1.20; the 1.27 command form) -- approved for the user's approval, reviewer-approved with the saved report for
a second reviewer's pass, nothing for a design spec-guard says needs no review."""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path

from helpers import ReviewCase, git
from module_crew import review, store
from test_flow_v2 import FlowReviewMixin, flow_row, notices
from test_review_mark_compat import REVIEW_MARK_127
from test_takeover_approve import finding, report

# A reviewMark stand-in that logs its command line, takes --review / --blocking / --reason, knows --target design
# and fails a design on FAKE_DESIGN_FAIL (printing a spec-guard style refusal).
LOGGING_REVIEW_MARK = '''import argparse, os, shlex, sys
from pathlib import Path
p = argparse.ArgumentParser()
for a in ("--project", "--module", "--target", "--state"):
    p.add_argument(a, required=True)
for a in ("--review", "--blocking", "--reason"):
    p.add_argument(a)
p.add_argument("--confirm", action="store_true")
a = p.parse_args()
with open(os.environ["FAKE_MARK_LOG"], "a", encoding="utf-8") as log:
    log.write(" ".join(shlex.quote(x) for x in sys.argv[1:]) + "\\n")
if not a.confirm:
    sys.exit(2)
if a.target == "design" and os.environ.get("FAKE_DESIGN_FAIL"):
    print("design-blocking: the report has 1 blocking item(s)")
    sys.exit(2)
targets = {"spec": ["spec/%s.md"], "plan": ["tasks/%s/plan.md"], "both": ["spec/%s.md", "tasks/%s/plan.md"],
           "design": ["tasks/%s/design.md"]}[a.target]
for t in targets:
    f = Path(a.project) / (t % a.module)
    lines = f.read_text(encoding="utf-8").splitlines(keepends=True)
    mark = "<!-- spec-guard: review %s fakedigest -->\\n" % a.state
    if lines and lines[0].startswith("<!-- spec-guard: review"):
        lines[0] = mark
    else:
        lines.insert(0, mark)
    f.write_text("".join(lines), encoding="utf-8")
'''


class DesignMarkMixin(FlowReviewMixin):
    def use_127_marks(self, command=None):
        """The installed fake spec-guard gets the 1.27 reviewMark command and the logging review_mark.py."""
        entry = self.plugins.entries["spec-guard@m"][-1]
        root = Path(entry["installPath"])
        doc = json.loads((root / "interface.json").read_text())
        doc["reviewMark"] = {"command": command or REVIEW_MARK_127}
        (root / "interface.json").write_text(json.dumps(doc))
        (root / "hooks" / "review_mark.py").write_text(LOGGING_REVIEW_MARK)
        self.log = self.tmp / "marks.log"
        self.log.write_text("")
        os.environ["FAKE_MARK_LOG"] = str(self.log)
        self.addCleanup(lambda: os.environ.pop("FAKE_MARK_LOG", None))

    def calls(self, target: str | None = None) -> list[list[str]]:
        rows = [shlex.split(x) for x in self.log.read_text().splitlines() if x.strip()]
        return [r for r in rows if target is None or r[r.index("--target") + 1] == target]

    def arg(self, call: list[str], name: str) -> str | None:
        return call[call.index(name) + 1] if name in call else None

    def ok(self, text, m="b", rid=1):
        out = self.add(text, m=m, rid=rid)
        self.assertEqual(out.code, 0, out.lines)
        return out.number


class UserApprovesDesignTest(DesignMarkMixin, ReviewCase):
    """Decisions 1, 8; AC1, AC6: the user's approval of a design writes approved, without a report."""

    def setUp(self):
        super().setUp()
        self.with_flow()
        self.write_design("b")
        self.use_127_marks()
        self.set_flow({"b": "normal"}, {"b": flow_row(design="human")})

    def test_user_approval_writes_approved(self):
        s = self.ok(self.spec_review("b"))
        self.assertEqual(review.approve(self.repo, [s], "b 的需求批准").code, 0)
        d = self.ok(self.design_review("b"), rid=2)
        before = git(self.repo, "rev-parse", "HEAD").strip()
        res = review.approve(self.repo, [d], "b 的技术方案批准")
        self.assertEqual(res.code, 0, res.lines)
        [call] = self.calls("design")
        self.assertEqual((self.arg(call, "--module"), self.arg(call, "--state")), ("b", "approved"))
        self.assertIn("--confirm", call)
        for absent in ("--review", "--blocking", "--reason"):
            self.assertNotIn(absent, call)
        changed = git(self.repo, "diff", "--name-only", before, "HEAD").split()
        self.assertEqual(sorted(changed), ["tasks/b/design.md", "tasks/b/regression.md"])
        design = (self.repo / "tasks" / "b" / "design.md").read_text()
        self.assertTrue(design.startswith("<!-- spec-guard: review approved"), design)
        self.assertEqual(git(self.repo, "status", "--porcelain").strip(), "")

    def test_requirement_mark_before_design_mark(self):
        d_first = [self.ok(self.design_review("b"), rid=2), self.ok(self.spec_review("b"), rid=3)]
        res = review.approve(self.repo, d_first, "都批准")
        self.assertEqual(res.code, 0, res.lines)
        targets = [self.arg(c, "--target") for c in self.calls()]
        self.assertEqual(targets, ["spec", "design"])


class SecondReviewerMarkTest(DesignMarkMixin, ReviewCase):
    """Decisions 1, 2; AC1, AC2: a second reviewer's pass writes reviewer-approved with the saved report; the user's
    approval after a fallback writes approved."""

    def setUp(self):
        super().setUp()
        self.with_flow()
        self.write_design("b")
        self.use_127_marks()
        self.set_flow({"b": "normal"}, {"b": flow_row(design="reviewer")})
        s = self.ok(self.spec_review("b"))
        assert review.approve(self.repo, [s], "b 的需求批准").code == 0
        self.n = self.ok(self.design_review("b"), rid=2)

    def files(self):
        import hashlib
        import subprocess
        rec = store.get(self.db(), "item", str(self.n))
        return {f["path"]: hashlib.sha256(subprocess.run(["git", "-C", str(self.wt["b"]), "show",
                                                          f"{rec['commit']}:{f['path']}"], capture_output=True,
                                                         check=True).stdout).hexdigest() for f in rec["files"]}

    def design_report(self, findings=(), same=False, **kw):
        doc = report(self.files(), findings, backend="claude-code", **kw)
        doc["reviewer"] = {"vendor": "anthropic" if same else "openai", "backend": "claude-code" if same else "codex",
                           "same_vendor": same, "selection": "same-vendor" if same else "other-vendor"}
        doc["criteria"] = "design-v1"
        return doc

    def note(self, doc):
        path = self.tmp / f"report-{len(list(self.tmp.glob('report-*')))}.json"
        path.write_text(json.dumps(doc))
        res = self.run_cli("review", "codex-note", f"C{self.n}", "--report", str(path), cwd=self.repo)
        return res.returncode, res.stdout + res.stderr

    def test_pass_writes_reviewer_approved_with_saved_report(self):
        code, out = self.note(self.design_report([finding("命名", severity="suggestion")], same=True))
        self.assertEqual(code, 0, out)
        [call] = self.calls("design")
        self.assertEqual(self.arg(call, "--state"), "reviewer-approved")
        saved = self.db().path / "codex" / f"C{self.n}-r1.json"
        self.assertEqual(Path(self.arg(call, "--review")).resolve(), saved.resolve())
        self.assertIn("--confirm", call)
        design = (self.repo / "tasks" / "b" / "design.md").read_text()
        self.assertTrue(design.startswith("<!-- spec-guard: review reviewer-approved"), design)
        self.assertEqual(store.get(self.db(), "item", str(self.n))["closedReason"], "codex-approved")

    def test_no_reviewer_then_user_writes_approved(self):
        doc = {"schema_version": 1, "execution_status": "conditions_missing", "backend": None,
               "diagnostics": ["no_reviewer_available"], "reviewer": {"vendor": None, "backend": None,
                                                                       "same_vendor": None, "selection": "none"}}
        self.assertEqual(self.note(doc)[0], 5)
        self.assertEqual(self.calls("design"), [])
        res = self.run_cli("review", "codex-fallback", f"C{self.n}", "--original", "我来批", cwd=self.repo)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        got = review.approve(self.repo, [self.n], "C 我来批")
        self.assertEqual(got.code, 0, got.lines)
        [call] = self.calls("design")
        self.assertEqual(self.arg(call, "--state"), "approved")
        self.assertNotIn("--review", call)


class SkipNoMarkTest(DesignMarkMixin, ReviewCase):
    """Decision 3; AC3: a design spec-guard says needs no review lands without a mark."""

    def test_skip_writes_no_design_mark(self):
        self.with_flow()
        self.write_design("b")
        self.use_127_marks()
        self.set_flow({"b": "normal"}, {"b": flow_row(design="reviewer", approval="not-required")})
        s = self.ok(self.spec_review("b"))
        self.assertEqual(review.approve(self.repo, [s], "b 的需求批准").code, 0)
        out = self.add(self.design_review("b"), rid=2)
        self.assertEqual(out.code, 0, out.lines)
        self.assertTrue((self.repo / "tasks" / "b" / "design.md").exists())
        self.assertEqual(self.calls("design"), [])
        self.assertTrue([x for x in out.sends if x["kind"] == "coordination-notice"], out.lines)


if __name__ == "__main__":
    import unittest
    unittest.main()
