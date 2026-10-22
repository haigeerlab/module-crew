"""crew-review-display: overlap conclusions, final-acceptance tables, request templates (see the Spec)."""

import json
import os
import unittest
from pathlib import Path

from helpers import ReviewCase

from module_crew import review, store

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


if __name__ == "__main__":
    unittest.main()
