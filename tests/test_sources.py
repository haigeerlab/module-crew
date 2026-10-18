import unittest

from helpers import ReviewCase, RepoCase, git, seed_sessions

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



class ApproveWithSourceTest(ReviewCase):
    def setUp(self):
        super().setUp()
        from module_crew import review
        self.db = store.open_store(self.repo)
        sources.add(self.db, "live-saas-hub", "hub", "登记收件枢纽")
        self.spec = review.add(self.db, self.spec_review("b"), "shop-b", 4001).number
        self.plan = review.add(self.db, self.plan_review("b"), "shop-b", 4002).number
        self.msg = self.tmp / "hub.txt"
        self.msg.write_text(hub_reply(120, "两个都批准"), encoding="utf-8")

    def test_one_hub_item_approves_two_reviews(self):
        out = self.run_cli("review", "approve", str(self.spec), str(self.plan), "--source", "live-saas-hub",
                           "--source-item", "120", "--source-relay-id", "6100", "--original-file", str(self.msg), cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        want = {"name": "live-saas-hub", "kind": "hub", "item": 120, "relayId": 6100}
        for n in (self.spec, self.plan):
            ans = store.get(self.db, "item", str(n))["answer"]
            self.assertEqual((ans["original"], ans["source"]), ("两个都批准", want))
        numbers = {r["number"] for r in sources.map_item(self.db, 120)}
        self.assertTrue({self.spec, self.plan} <= numbers)
        self.assertEqual(sources.map_crew(self.db, self.spec), want)
        listed = self.run_cli("source", "map", "120", cwd=self.repo).stdout
        self.assertIn(f"#{self.spec}", listed)
        self.assertIn("live-saas-hub", self.run_cli("source", "map", f"#{self.plan}", cwd=self.repo).stdout)

    def test_bad_source_changes_nothing(self):
        before = (store.events(self.db), git(self.repo, "rev-parse", "HEAD"))
        for extra in (["--source", "nobody", "--source-item", "120", "--source-relay-id", "1"],
                      ["--source", "live-saas-hub", "--source-item", "121", "--source-relay-id", "1"]):
            out = self.run_cli("review", "approve", str(self.spec), *extra, "--original-file", str(self.msg), cwd=self.repo)
            self.assertEqual(out.returncode, 3, out.stdout)
        out = self.run_cli("review", "approve", str(self.spec), "--source", "live-saas-hub", "--original-file", str(self.msg),
                           cwd=self.repo)
        self.assertEqual(out.returncode, 2)
        self.assertEqual((store.events(self.db), git(self.repo, "rev-parse", "HEAD")), before)

    def test_self_approval_has_no_source(self):
        from module_crew import review
        self.assertEqual(review.approve(self.repo, [self.spec], "批准").code, 0)
        self.assertNotIn("source", store.get(self.db, "item", str(self.spec))["answer"])
        self.assertIsNone(sources.map_crew(self.db, self.spec))

    def test_other_commands_take_source(self):
        out = self.run_cli("suspend", "c", "--reason", "等设计稿", "--source", "live-saas-hub", "--source-item", "120",
                           "--source-relay-id", "6100", "--original-file", str(self.msg), cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        rec = store.get(self.db, "session", "shop-c")
        self.assertEqual(rec["suspended"]["original"], "两个都批准")
        self.assertEqual(store.events(self.db, key="shop-c")[-1]["data"]["source"]["item"], 120)


if __name__ == "__main__":
    unittest.main()
