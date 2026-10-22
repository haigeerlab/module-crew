"""crew-review-display: overlap conclusions, final-acceptance tables, request templates (see the Spec)."""

import json
import os
import unittest
from pathlib import Path

from helpers import MergeCase, ReviewCase, git, review_text

from module_crew import protocol, review, store

FAKE_OVERLAP = '''import json, os, sys
open(os.environ["FAKE_OVERLAP_ARGS"], "w").write(json.dumps(sys.argv[1:]))
print(open(os.environ["FAKE_OVERLAP_OUT"]).read())
'''


class OverlapCase(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        self.args = self.tmp / "overlap-args.json"
        self.out = self.tmp / "overlap-out.json"
        os.environ["FAKE_OVERLAP_ARGS"], os.environ["FAKE_OVERLAP_OUT"] = str(self.args), str(self.out)
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in ("FAKE_OVERLAP_ARGS", "FAKE_OVERLAP_OUT")])

    def with_scope_overlap(self, result):
        root = Path(self.plugins.entries["spec-guard@m"][-1]["installPath"])
        doc = json.loads((root / "interface.json").read_text())
        doc["interface"] = "1.10"
        doc["scopeOverlap"] = {"command": ["python3", "-B", "hooks/module_scope.py", "overlap", "--project", "<project-root>",
                                           "--spec", "<module-id>=<spec-file>"]}
        (root / "interface.json").write_text(json.dumps(doc))
        (root / "hooks" / "module_scope.py").write_text(FAKE_OVERLAP)
        self.out.write_text(json.dumps(result))

    def both_specs(self):
        for m, rid in (("b", 1), ("c", 2)):
            assert review.add(self.db, self.spec_review(m), f"shop-{m}", rid).code == 0

    def overlap_line(self):
        out = self.run_cli("review", "batch").stdout
        return [x for x in out.splitlines() if "并行边界" in x or x.startswith("未比对")]


class OverlapTest(OverlapCase):
    """Acceptance 6."""

    def test_pending_specs_without_scope_overlap_unchecked(self):
        self.both_specs()
        o = review.batch(self.repo)["overlap"]
        self.assertEqual(o["state"], "unchecked")
        self.assertIn("1.10", o["reason"])
        lines = self.overlap_line()
        self.assertTrue(any(x.startswith("未比对") for x in lines), lines)
        self.assertFalse(any(x.endswith("并行边界重叠：无") for x in lines), lines)

    def test_scope_overlap_reports_conflicts_from_submitted_specs(self):
        self.with_scope_overlap({"conflicts": [{"modules": ["b", "c"], "paths": ["src/shared.py"],
                                                "sources": {"b": "x", "c": "y"}}], "errors": []})
        self.both_specs()
        o = review.batch(self.repo)["overlap"]
        self.assertEqual((o["state"], o["conflicts"][0]["paths"]), ("conflicts", ["src/shared.py"]))
        args = json.loads(self.args.read_text())
        specs = [args[i + 1] for i, a in enumerate(args) if a == "--spec"]
        self.assertEqual(sorted(s.split("=", 1)[0] for s in specs), ["b", "c"])
        for s in specs:                                    # the submitted Spec, saved under the store's tmp/
            path = Path(s.split("=", 1)[1])
            self.assertEqual(path.parent, self.db.path / "tmp")
            self.assertIn("# Spec:", path.read_text(encoding="utf-8"))
        self.assertIn("--project", args)
        self.assertTrue(any("⚠️ 并行边界重叠：b、c 在 src/shared.py" in x for x in self.overlap_line()))

    def test_errors_listed_and_never_none(self):
        self.with_scope_overlap({"conflicts": [], "errors": [{"module": "c", "source": "f", "error": "no-boundary"}]})
        self.both_specs()
        o = review.batch(self.repo)["overlap"]
        self.assertEqual(o["state"], "unchecked")
        lines = self.overlap_line()
        self.assertTrue(any("no-boundary" in x for x in lines), lines)
        self.assertFalse(any(x.endswith("并行边界重叠：无") for x in lines), lines)

    def test_clean_compare_says_none_with_basis(self):
        self.with_scope_overlap({"conflicts": [], "errors": []})
        self.both_specs()
        self.assertEqual(review.batch(self.repo)["overlap"]["state"], "none")
        self.assertIn("并行边界重叠：无（已按交审中的 Spec 比对）", self.overlap_line())

    def test_no_pending_spec_uses_the_map(self):
        s = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        assert review.approve(self.repo, [s], "批").code == 0
        assert review.add(self.db, self.plan_review("b"), "shop-b", 2).code == 0
        self.assertEqual(review.batch(self.repo)["overlap"]["state"], "none")
        self.assertIn("并行边界重叠：无（已按集成分支上的 Spec 比对）", self.overlap_line())


class FinalTablesCase(MergeCase):
    """b's Spec and Plan approved (the Plan names src/a.py and docs/guide.md), then a final review with real changes."""

    plan_text = "<!-- spec-guard: review pending -->\n# Plan: b\n\n会改哪些文件：`src/a.py`、`docs/guide.md`\n"

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        (self.wt["b"] / "tasks" / "b" / "plan.md").write_text(self.plan_text, encoding="utf-8")
        git(self.wt["b"], "commit", "-qam", "b: plan names its files")
        s = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        p = review.add(self.db, self.plan_review("b"), "shop-b", 2).number
        assert review.approve(self.repo, [s, p], "批").code == 0
        git(self.wt["b"], "merge", "-q", "--no-edit", "-X", "theirs", "main")
        wt = self.wt["b"]
        (wt / "docs").mkdir()
        (wt / "docs" / "guide.md").write_text("用法\n", encoding="utf-8")
        (wt / "src").mkdir()
        (wt / "src" / "extra.py").write_text("X = 1\nY = 2\n", encoding="utf-8")
        (wt / "package.json").write_text('{\n  "dependencies": {\n    "left-pad": "1.3.0"\n  }\n}\n', encoding="utf-8")
        git(wt, "rm", "-q", "README.md")
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", "b: docs, extra code, a dependency")
        self.n = review.add(self.db, self.finish("b", path="src/a.py"), "shop-b", 3).number


class FinalTablesTest(FinalTablesCase):
    """Acceptance 1."""

    def test_tables(self):
        d = review.batch(self.repo)
        item = next(i for i in d["items"] if i["number"] == self.n)
        t = item["display"]
        self.assertEqual({(r["status"], r["path"]) for r in t["docs"]}, {("新增", "docs/guide.md"), ("删除", "README.md")})
        code = {r["path"]: r for r in t["code"]}
        self.assertEqual(set(code), {"src/a.py", "src/extra.py", "package.json"})
        self.assertFalse(code["src/a.py"]["beyondPlan"])
        self.assertTrue(code["src/extra.py"]["beyondPlan"])
        self.assertEqual((code["src/extra.py"]["added"], code["src/extra.py"]["deleted"]), (2, 0))
        subjects = [c.split(" ", 1)[1] for c in t["commits"]]   # every module commit the integration branch lacks, oldest first
        self.assertEqual(subjects[-2:], ["b: docs, extra code, a dependency", "b: code"])
        self.assertIn("b: spec and plan", subjects)
        self.assertEqual(t["dependencies"], ["left-pad 1.3.0（package.json）"])
        self.assertIsNone(t["specDiff"])

    def test_card_order_and_text(self):
        [(n, path, text)] = review.for_hub(self.repo)
        points = protocol.parse(text).fields["要点"]
        at = {k: points.index(k) for k in ("做：页面与接口", "验收标准与证据", "改了哪些文件：", "Spec 中途改过吗：")}
        # the module's own items (做了什么, 验收结果) as written, then the tables from git, then the Spec question
        self.assertLess(max(at["做：页面与接口"], at["验收标准与证据"]), at["改了哪些文件："])
        self.assertLess(at["改了哪些文件："], at["Spec 中途改过吗："])
        for words in ("文档：", "- 新增 docs/guide.md（+1 −0）", "- 删除 README.md", "代码：", "- 新增 src/extra.py（+2 −0，超出 Plan）",
                      "提交：", "b: docs, extra code, a dependency", "新增依赖：", "- left-pad 1.3.0（package.json）",
                      "Spec 中途改过吗：没有"):
            self.assertIn(words, points)


class PlanWithoutFilesTest(FinalTablesCase):
    """Acceptance 2."""

    plan_text = "<!-- spec-guard: review pending -->\n# Plan: b\n\n分几步：一步做完\n"

    def test_beyond_plan_unknown(self):
        item = next(i for i in review.batch(self.repo)["items"] if i["number"] == self.n)
        self.assertTrue(all(r["beyondPlan"] is None for r in item["display"]["code"]))
        [(n, path, text)] = review.for_hub(self.repo)
        self.assertIn("无法判断（Plan 没写文件）", protocol.parse(text).fields["要点"])


if __name__ == "__main__":
    unittest.main()
