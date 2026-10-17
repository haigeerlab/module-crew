import unittest

from helpers import StartCase, seed_sessions

from module_crew import start, store


class PlanTest(StartCase):
    def test_proposes_up_to_free_slots_in_build_order(self):
        p = start.plan(self.repo)
        self.assertEqual(p.blockers, [])
        self.assertEqual(p.slots, 3)
        self.assertEqual([m["id"] for m in p.modules], ["b", "c", "d"])
        self.assertEqual(p.modules[0]["responsibility"], "支付页")

    def test_active_dev_sessions_take_slots(self):
        db, _ = store.init_store(self.repo)
        with db.transaction(actor="t") as tx:
            tx.put("session", "shop-x", {"role": "dev", "host": "claude-desktop", "status": "active",
                                         "module": "x", "worktree": "/tmp/x"}, action="registered")
            tx.put("session", "shop-y", {"role": "dev", "host": "claude-desktop", "status": "retired",
                                         "module": "y", "worktree": "/tmp/y"}, action="registered")
        p = start.plan(self.repo)
        self.assertEqual(p.slots, 2)
        self.assertEqual([m["id"] for m in p.modules], ["b", "c"])

    def test_configured_max(self):
        db, _ = store.init_store(self.repo)
        with db.transaction(actor="t") as tx:
            tx.put("config", "main", {"projectShort": "shop", "integrationBranch": "main", "maxModules": 2,
                                      "crewDir": str(self.tmp / "repo-crew")}, action="set")
        self.assertEqual([m["id"] for m in start.plan(self.repo).modules], ["b", "c"])

    def test_conflicts_passed_through(self):
        from helpers import START_MAP
        doc = dict(START_MAP, startable={"modules": ["b", "c"], "conflicts": [{"modules": ["b", "c"], "paths": ["apps/x/"]}]})
        self.set_map(doc)
        self.assertEqual(start.plan(self.repo).conflicts, [{"modules": ["b", "c"], "paths": ["apps/x/"]}])

    def test_blockers_reported(self):
        (self.repo / "dirty.txt").write_text("x")
        p = start.plan(self.repo)
        self.assertTrue(any("集成基线不干净" in b for b in p.blockers))
        self.assertEqual(p.modules, [])


if __name__ == "__main__":
    unittest.main()


class PlanCliTest(StartCase):
    def test_human_and_json(self):
        r = self.run_cli("start", "plan")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("空位：3", r.stdout)
        self.assertIn("b（支付页）", r.stdout)
        import json
        doc = json.loads(self.run_cli("start", "plan", "--json").stdout)
        self.assertEqual([m["id"] for m in doc["modules"]], ["b", "c", "d"])

    def test_blocked_exit_3(self):
        (self.repo / "dirty.txt").write_text("x")
        r = self.run_cli("start", "plan")
        self.assertEqual(r.returncode, 3)
        self.assertIn("集成基线不干净", r.stdout)
