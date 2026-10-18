import unittest

from helpers import RepoCase, seed_sessions

from module_crew import protocol, sources, store


def hub_reply(item=120, original="批准 #4 #5", relay=6001):
    return protocol.render_user_reply(item, original, "2026-10-18T12:00:00+08:00", source_relay_id=relay)


class SourceCase(RepoCase):
    def setUp(self):
        super().setUp()
        self.db, _ = store.init_store(self.repo)
        seed_sessions(self.db)
        with self.db.transaction(actor="t") as tx:
            tx.put("config", "main", {"projectShort": "shop", "integrationBranch": "main"}, action="set")


class WhitelistTest(SourceCase):
    def test_add_list_remove(self):
        sources.add(self.db, "live-saas-hub", "hub", "登记收件枢纽")
        rows = sources.listing(self.db)
        self.assertEqual([(r["name"], r["kind"], r["original"]) for r in rows], [("live-saas-hub", "hub", "登记收件枢纽")])
        self.assertEqual(store.get(self.db, "config", "main")["projectShort"], "shop")  # rest of the config kept
        sources.remove(self.db, "live-saas-hub", "撤掉")
        self.assertEqual(sources.listing(self.db), [])

    def test_refusals_write_nothing(self):
        sources.add(self.db, "live-saas-hub", "hub", "登记")
        before = store.events(self.db)
        for call in (lambda: sources.add(self.db, "x", "hub", " "),
                     lambda: sources.add(self.db, "live-saas-hub", "hub", "再登记"),
                     lambda: sources.add(self.db, "y", "boss", "登记"),
                     lambda: sources.remove(self.db, "nobody", "撤"),
                     lambda: sources.remove(self.db, "live-saas-hub", "")):
            with self.assertRaises(sources.SourceRefused):
                call()
        self.assertEqual(store.events(self.db), before)


class CheckTest(SourceCase):
    def setUp(self):
        super().setUp()
        sources.add(self.db, "live-saas-hub", "hub", "登记收件枢纽")
        sources.add(self.db, "live-saas-arch-review", "lead", "登记审查会话")

    def test_hub_reply_accepted(self):
        info = sources.check(self.db, "live-saas-hub", 120, 6100, hub_reply())
        self.assertEqual(info.original, "批准 #4 #5")
        self.assertEqual(info.source, {"name": "live-saas-hub", "kind": "hub", "item": 120, "relayId": 6100})

    def test_refused(self):
        cases = [("someone", 120, hub_reply()),                 # not whitelisted
                 ("live-saas-hub", 121, hub_reply()),           # item mismatch
                 ("live-saas-hub", 120, "随便写的话"),           # not a user reply
                 ("live-saas-hub", 120, ""),                    # empty
                 ("live-saas-arch-review", 120, hub_reply())]   # lead waits for v1.6
        for name, item, text in cases:
            with self.subTest(name=name, item=item):
                with self.assertRaises(sources.SourceRefused):
                    sources.check(self.db, name, item, 1, text)

    def test_cli(self):
        out = self.run_cli("source", "add", "other-hub", "--kind", "hub", "--original", "登记", cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("other-hub", self.run_cli("source", "list", cwd=self.repo).stdout)
        out = self.run_cli("source", "add", "other-hub", "--kind", "hub", "--original", "登记", cwd=self.repo)
        self.assertEqual(out.returncode, 3)
        self.assertEqual(self.run_cli("source", "remove", "other-hub", "--original", "撤", cwd=self.repo).returncode, 0)


if __name__ == "__main__":
    unittest.main()
