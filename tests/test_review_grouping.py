"""Batch reviews are presented module by module, in Build order (user request via spec-guard, 2026-10-18)."""

import json
import unittest

from helpers import ReviewCase

from module_crew import protocol, review, store


class GroupingTest(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        # arrival order interleaves the modules and puts c (later in Build order) first
        self.c_spec = review.add(self.db, self.spec_review("c"), "shop-c", 1).number
        self.b_plan = review.add(self.db, self.plan_review("b"), "shop-b", 2).number
        self.c_plan = review.add(self.db, self.plan_review("c"), "shop-c", 3).number
        self.b_spec = review.add(self.db, self.spec_review("b"), "shop-b", 4).number

    def test_items_follow_build_order_then_node(self):
        b = review.batch(self.repo)
        self.assertEqual([i["number"] for i in b["items"]], [self.b_spec, self.b_plan, self.c_spec, self.c_plan])
        self.assertEqual([(g["module"], g["items"]) for g in b["groups"]],
                         [("b", [self.b_spec, self.b_plan]), ("c", [self.c_spec, self.c_plan])])
        self.assertEqual(b["groups"][0]["responsibility"], "支付页")

    def test_text_output_one_section_per_module(self):
        out = self.run_cli("review", "batch", cwd=self.repo).stdout
        b_at, c_at = out.index("## b（支付页）"), out.index("## c（订单页）")
        self.assertLess(b_at, c_at)
        self.assertLess(out.index(f"C{self.b_plan} b 的 Plan"), c_at)        # b's Plan is inside b's section
        self.assertGreater(out.index(f"C{self.c_spec} c 的 Spec"), c_at)
        doc = json.loads(self.run_cli("review", "batch", "--json", cwd=self.repo).stdout)
        self.assertEqual([g["module"] for g in doc["groups"]], ["b", "c"])

    def test_for_hub_one_item_per_module_in_build_order(self):
        made = review.for_hub(self.repo)          # no reviewer: everything is ready; separate cadence: one node each
        asked = [protocol.parse(text).fields["要你决定"] for _, _, text in made]
        self.assertEqual(len(asked), 4)
        for want, got in zip((self.b_spec, self.b_plan, self.c_spec, self.c_plan), asked):
            self.assertIn(f"C{want}", got)


if __name__ == "__main__":
    unittest.main()
