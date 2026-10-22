"""crew-contract-v26: C<交审号>-<序号> pending questions by registered inbox version, both answer forms (see the Spec)."""

import unittest

from helpers import git
from test_review_nearby import DECISIONS, NearbyCase, NoteTest, conclusion

from module_crew import protocol, review, sources, store


class NumberingCase(NearbyCase):
    submit = NoteTest.submit

    def hub(self, version):
        sources.add(self.db, "inbox", "hub", "登记收件箱", protocol=version)

    def card(self):
        [(n, path, text)] = review.for_hub(self.repo)
        msg = protocol.parse(text)
        self.assertTrue(msg.ok, msg.problems)
        return msg

    def reviewed(self):
        n = self.submit()
        review.note(self.db, n, "arch", conclusion("通过", DECISIONS))
        return n


class NumberingTest(NumberingCase):
    """Acceptance 4."""

    def test_v26_inbox_gets_c_numbers(self):
        self.hub("2.6")
        n = self.reviewed()
        msg = self.card()
        self.assertEqual([d["id"] for d in msg.contract()["decisions"]], [f"C{n}-1", f"C{n}-2"])
        rec = [v for v in store.records(self.db, "item").values() if v.get("kind") == "hub-batch"][-1]
        self.assertEqual(rec["decisions"][f"C{n}-2"]["review"], n)
        self.assertIn(f"C{n}-1 B", msg.fields["你该回"])

    def test_older_inbox_keeps_d_numbers(self):
        self.hub("2.5")
        self.reviewed()
        self.assertEqual([d["id"] for d in self.card().contract()["decisions"]], ["D1", "D2"])

    def test_no_inbox_uses_c_numbers(self):
        n = self.reviewed()
        out = self.run_cli("review", "batch", cwd=self.repo).stdout
        self.assertIn(f"C{n}-1：alpha 首字母要不要大写？", out)
        self.assertNotIn("D1：", out)


class AnswerTest(NumberingCase):
    """Acceptance 2 (answers) and 4: either numbering is read."""

    def test_c_answers(self):
        n = self.reviewed()
        self.assertEqual(review.approve(self.repo, [n], f"C{n} A；C{n}-1 B；C{n}-2 A").code, 0)

    def test_d_answers_still_read(self):
        self.hub("2.5")
        n = self.reviewed()
        self.assertEqual(review.approve(self.repo, [n], "A；D1 B；D2：A").code, 0)

    def test_missing_c_answer_chased(self):
        n = self.reviewed()
        before = (store.events(self.db), git(self.repo, "rev-parse", "HEAD"))
        res = review.approve(self.repo, [n], f"C{n} A；C{n}-1 B")
        self.assertEqual(res.code, 3, res.lines)
        self.assertIn(f"C{n}-2", " ".join(res.lines))
        self.assertEqual((store.events(self.db), git(self.repo, "rev-parse", "HEAD")), before)


class RegisterTest(NumberingCase):
    """Acceptance 7 (registration)."""

    def test_register_26(self):
        self.hub("2.6")
        self.assertEqual(sources.hub_protocol(sources.listing(self.db)[-1]), "2.6")
        self.assertIn("2.6", sources.PROTOCOLS)


if __name__ == "__main__":
    unittest.main()
