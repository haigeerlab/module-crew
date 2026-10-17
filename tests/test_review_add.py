import unittest

from helpers import ReviewCase, git, review_text

from module_crew import review, store


def files(db):
    return {str(p): p.read_bytes() for p in db.path.rglob("*") if p.is_file() and p.name != ".lock"}


class AddTest(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def test_recorded(self):
        out = review.add(self.db, self.spec_review("b"), "shop-b", 4600)
        self.assertEqual(out.code, 0, out.lines)
        rec = store.get(self.db, "item", str(out.number))
        self.assertEqual((rec["kind"], rec["state"], rec["module"], rec["node"]), ("review", "open", "b", "spec"))
        self.assertEqual(rec["files"][0]["path"], "spec/b.md")
        self.assertEqual(rec["commit"], git(self.wt["b"], "rev-parse", "HEAD").strip())

    def assert_rejected(self, text, sender="shop-b", words=""):
        before = files(self.db)
        out = review.add(self.db, text, sender, 4700)
        self.assertEqual(out.code, 3, out.lines)
        self.assertIn(words, " ".join(out.lines))
        self.assertEqual(files(self.db), before)

    def test_rejections(self):
        self.assert_rejected(self.spec_review("b"), sender="shop-x", words="登记")
        self.assert_rejected(self.spec_review("c"), sender="shop-b", words="模块")
        bad = self.spec_review("b").replace("sha256:", "sha256:0000")
        self.assert_rejected(bad, words="指纹")
        self.assert_rejected(self.spec_review("b").replace("节点：Spec", "节点：需求"), words="bad-node")

    def test_uncommitted_or_untracked(self):
        spec = self.wt["b"] / "spec" / "b.md"
        spec.write_text(spec.read_text() + "改了没提交\n")
        self.assert_rejected(self.spec_review("b"), words="未提交")
        new = self.wt["b"] / "spec" / "extra.md"
        new.write_text("x")
        self.assert_rejected(review_text("b", "Spec", [("spec/extra.md", new)]), words="未提交")

    def test_supersede_same_module_node_and_repeat(self):
        first = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        plan = review.add(self.db, self.plan_review("b"), "shop-b", 2).number
        out = review.add(self.db, self.spec_review("b"), "shop-b", 3)
        self.assertEqual(out.closed, [first])
        self.assertEqual(store.get(self.db, "item", str(first))["closedReason"], "superseded")
        self.assertEqual(store.get(self.db, "item", str(plan))["state"], "open")
        before = files(self.db)
        again = review.add(self.db, self.spec_review("b"), "shop-b", 3)
        self.assertIn("已记过", " ".join(again.lines))
        self.assertEqual(files(self.db), before)


if __name__ == "__main__":
    unittest.main()
