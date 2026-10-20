"""crew-hub-card-fields: v2.3 approval cards for the decision inbox (spec/crew-hub-card-fields.md)."""

import re
import unittest
from pathlib import Path

from helpers import MergeCase, RepoCase

from module_crew import protocol, review, sources, start, store

V22 = Path(__file__).resolve().parent / "fixtures" / "card-fields"


def conclusion(module="b", node="Spec", verdict="通过", ref="R-1", extra=""):
    return (f"【审查结论】\n审查编号：{ref}\n节点：{node}\n模块：{module}\n送审方：shop-{module}\n结论：{verdict}\n"
            f"来自：arch\n要点：接口清楚。\n{extra}")


class CardCase(MergeCase):
    """Module b with a reviewed Spec and Plan, a hub source, and a registered reviewer."""

    protocol_version = None

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        sources.add(self.db, "arch", "lead", "登记审查会话", scope=sources.ALL_SCOPE)
        sources.add(self.db, "hub", "hub", "登记收件箱", protocol=self.protocol_version)

    def normal(self, text: str) -> str:
        """Paths, commits and fingerprints differ per run; everything else must match byte for byte."""
        text = text.replace(str(self.tmp), "<TMP>")
        text = re.sub(r"sha256:[0-9a-f]{64}", "sha256:<H>", text)
        return re.sub(r"\b[0-9a-f]{40}\b|\b[0-9a-f]{7}\b", "<SHA>", text)

    def spec_and_plan(self):
        s = review.add(self.db, self.spec_review("b"), "shop-b", 4001).number
        p = review.add(self.db, self.plan_review("b"), "shop-b", 4002).number
        review.note(self.db, s, "arch", conclusion(verdict="通过，附建议2条"))
        review.note(self.db, p, "arch", conclusion(node="Plan", ref="R-2"))
        return s, p

    def final(self):
        f = review.add(self.db, self.finish("c"), "shop-c", 4003).number
        review.note(self.db, f, "arch", conclusion(module="c", node="最终验收", ref="R-3"))
        return f


class HubProtocolTest(RepoCase):
    """Task 2: the decision inbox's contract version is recorded with its source (Spec acceptance 6)."""

    def setUp(self):
        super().setUp()
        store.init_store(self.repo)
        self.db = store.open_store(self.repo)

    def test_default_and_recorded(self):
        self.assertEqual(sources.hub_protocol(self.db), "2.2")              # no hub at all
        sources.add(self.db, "hub-a", "hub", "登记收件箱")
        self.assertEqual(sources.listing(self.db)[0].get("protocol"), None)  # not written: read as 2.2
        self.assertEqual(sources.hub_protocol(self.db), "2.2")
        sources.remove(self.db, "hub-a", "撤掉")
        sources.add(self.db, "hub-a", "hub", "登记收件箱", protocol="2.3")
        self.assertEqual(sources.hub_protocol(self.db), "2.3")
        sources.add(self.db, "arch", "lead", "登记审查会话", scope=sources.ALL_SCOPE)                   # a reviewer does not count
        self.assertEqual(sources.hub_protocol(self.db), "2.3")
        sources.add(self.db, "hub-b", "hub", "第二个收件箱", protocol="2.4")
        self.assertEqual(sources.hub_protocol(self.db), "2.3")                 # the lowest registered version
        sources.add(self.db, "hub-c", "hub", "第三个收件箱")                   # one hub still on 2.2
        self.assertEqual(sources.hub_protocol(self.db), "2.2")

    def test_refusals(self):
        with self.assertRaises(sources.SourceRefused):
            sources.add(self.db, "hub-a", "hub", "登记", protocol="2.5")
        with self.assertRaises(sources.SourceRefused):
            sources.add(self.db, "arch", "lead", "登记", protocol="2.3")     # only a hub has a contract version

    def test_cli(self):
        out = self.run_cli("source", "add", "hub-a", "--kind", "hub", "--protocol", "2.3", "--original", "登记收件箱")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("契约 v2.3", out.stdout)
        self.assertIn("契约 v2.3", self.run_cli("source", "list").stdout)
        self.assertNotEqual(self.run_cli("source", "add", "hub-b", "--kind", "hub", "--protocol", "3",
                                         "--original", "x").returncode, 0)


class V22UnchangedTest(CardCase):
    """Spec acceptance 5: with a hub on 2.2 (or no version), the text is what 0.6.0 wrote, byte for byte."""

    def test_same_as_before(self):
        self.spec_and_plan()
        self.final()
        made = review.for_hub(self.repo)
        self.assertEqual(len(made), 3)
        for i, (_, _, text) in enumerate(made):
            with self.subTest(i):
                # crew-stage-c-fixes MC-9: the only difference from 0.6.0 is the 「模块」 line right after 要点
                module = protocol.parse(text).contract()["module"]
                self.assertIn(module, ("b", "c"))
                self.assertEqual(self.normal(text).replace(f"模块：{module}\n", "", 1),
                                 (V22 / f"v22-{i}.txt").read_text(encoding="utf-8"))
                self.assertNotIn("类型：", text)


class V23CardTest(CardCase):
    """Spec acceptance 2–4: with a hub on 2.3 every approval card carries 类型, 注意, 推荐理由, 批了会怎样."""

    protocol_version = "2.3"

    def cards(self):
        out = []
        for _, _, text in review.for_hub(self.repo):
            msg = protocol.parse(text)
            self.assertTrue(msg.ok, msg.problems)
            out.append((msg, text))
        return out

    def test_kinds_and_fields(self):
        self.spec_and_plan()
        self.final()
        cards = self.cards()
        self.assertEqual([m.contract()["waitKind"] for m, _ in cards], ["spec", "plan", "final"])
        self.assertEqual([m.contract()["module"] for m, _ in cards], ["b", "b", "c"])
        for _, text in cards:      # contract v2.4: 「模块」 sits right after 要点, before 类型 and the rest
            self.assertLess(text.index("\n模块："), text.index("\n类型："))
        spec, plan, final = (m.fields for m, _ in cards)
        self.assertEqual(spec["类型"].strip(), "Spec")
        self.assertIn("接口清楚", spec["注意"])                         # passed with advice: the advice
        self.assertEqual(plan["注意"].strip(), "无")
        self.assertIn("R-2", plan["推荐理由"])
        self.assertIn("开工", spec["批了会怎样"])
        self.assertIn("合了撤不回", final["批了会怎样"])
        self.assertIn("merge revoke", final["批了会怎样"])
        for m, text in cards:
            self.assertNotIn("批准会发生什么", m.fields["要点"])
            # 批了会怎样 and option A come from the same place
            self.assertEqual(m.contract()["options"][0]["consequence"], m.fields["批了会怎样"].strip())

    def test_combined_is_one_spec_plan_card(self):
        with self.db.transaction(actor="t") as tx:
            tx.put("config", "main", dict(tx.get("config", "main"), reviewCadence="combined"), action="t")
        start_cadence = start.review_cadence
        start.review_cadence = lambda project: "combined"
        self.addCleanup(setattr, start, "review_cadence", start_cadence)
        self.spec_and_plan()
        [(msg, _)] = self.cards()
        self.assertEqual((msg.fields["类型"].strip(), msg.contract()["waitKind"]), ("Spec 与 Plan", "spec-plan"))

    def test_notes(self):
        f = self.final()
        [(msg, _)] = self.cards()
        self.assertEqual(msg.fields["注意"].strip(), "无")
        # rework: last round's 须修改 shows up
        g = review.add(self.db, self.spec_review("b"), "shop-b", 5001).number
        review.note(self.db, g, "arch", conclusion(verdict="有须修改项1条", extra="须修改：\n1. 错误码表缺两项\n"))
        h = review.add(self.db, self.spec_review("b"), "shop-b", 5002).number
        review.note(self.db, h, "arch", conclusion(ref="R-9"))
        notes = {m.fields["要你决定"]: m.fields["注意"] for m, _ in self.cards()}
        self.assertIn("错误码表缺两项", next(v for k, v in notes.items() if "b 的 Spec" in k))
        # reviewer gave no answer in time
        with self.db.transaction(actor="t") as tx:
            rec = tx.get("item", str(f))
            tx.put("item", str(f), dict(rec, reviews=[], sentAt="2000-01-01T00:00:00+08:00"), action="t")
        self.assertIn("审查者无响应", "\n".join(m.fields["注意"] for m, _ in self.cards()))


if __name__ == "__main__":
    unittest.main()
