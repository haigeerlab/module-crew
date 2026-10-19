"""crew-hub-card-fields: v2.3 approval cards for the decision inbox (spec/crew-hub-card-fields.md)."""

import unittest

from helpers import RepoCase

from module_crew import sources, store


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
        sources.add(self.db, "arch", "lead", "登记审查会话")                   # a reviewer does not count
        self.assertEqual(sources.hub_protocol(self.db), "2.3")
        sources.add(self.db, "hub-b", "hub", "第二个收件箱")                   # one hub still on 2.2
        self.assertEqual(sources.hub_protocol(self.db), "2.2")

    def test_refusals(self):
        with self.assertRaises(sources.SourceRefused):
            sources.add(self.db, "hub-a", "hub", "登记", protocol="2.4")
        with self.assertRaises(sources.SourceRefused):
            sources.add(self.db, "arch", "lead", "登记", protocol="2.3")     # only a hub has a contract version

    def test_cli(self):
        out = self.run_cli("source", "add", "hub-a", "--kind", "hub", "--protocol", "2.3", "--original", "登记收件箱")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("契约 v2.3", out.stdout)
        self.assertIn("契约 v2.3", self.run_cli("source", "list").stdout)
        self.assertNotEqual(self.run_cli("source", "add", "hub-b", "--kind", "hub", "--protocol", "3",
                                         "--original", "x").returncode, 0)


if __name__ == "__main__":
    unittest.main()
