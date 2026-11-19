import unittest

from helpers import StartCase, seed_sessions

from module_crew import start, store


class PlanTest(StartCase):
    def test_proposes_up_to_free_slots_in_build_order(self):
        p = start.plan(self.repo)
        self.assertEqual(p.blockers, [])
        self.assertEqual(p.slots, 2)                                    # crew-coordinator-switch: default 2
        self.assertEqual([m["id"] for m in p.modules], ["b", "c"])
        self.assertEqual(p.modules[0]["responsibility"], "支付页")

    def test_active_dev_sessions_take_slots(self):
        db, _ = store.init_store(self.repo)
        with db.transaction(actor="t") as tx:
            tx.put("session", "shop-x", {"role": "dev", "host": "claude-desktop", "status": "active",
                                         "module": "x", "worktree": "/tmp/x"}, action="registered")
            tx.put("session", "shop-y", {"role": "dev", "host": "claude-desktop", "status": "retired",
                                         "module": "y", "worktree": "/tmp/y"}, action="registered")
        p = start.plan(self.repo)
        self.assertEqual(p.slots, 1)
        self.assertEqual([m["id"] for m in p.modules], ["b"])

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
        (self.repo / "README.md").write_text("dirty\n")
        p = start.plan(self.repo)
        self.assertTrue(any("集成分支所在的 checkout 不干净" in b for b in p.blockers))
        self.assertEqual(p.modules, [])


class PlanCliTest(StartCase):
    def test_human_and_json(self):
        r = self.run_cli("start", "plan")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("空位：2", r.stdout)
        self.assertIn("b（支付页）", r.stdout)
        import json
        doc = json.loads(self.run_cli("start", "plan", "--json").stdout)
        self.assertEqual([m["id"] for m in doc["modules"]], ["b", "c"])

    def test_blocked_exit_3(self):
        (self.repo / "README.md").write_text("dirty\n")
        r = self.run_cli("start", "plan")
        self.assertEqual(r.returncode, 3)
        self.assertIn("集成分支所在的 checkout 不干净", r.stdout)


class PilotRound2Test(StartCase):
    def dev(self, module, **extra):
        db = store.open_store(self.repo) if (self.repo / ".git" / "module-crew").exists() else store.init_store(self.repo)[0]
        with db.transaction(actor="t") as tx:
            tx.put("session", f"shop-{module}", {"role": "dev", "host": "claude-desktop", "status": "active",
                                                 "module": module, "worktree": f"/tmp/{module}", **extra}, action="registered")
        return db

    def test_suspended_module_not_proposed(self):
        self.dev("b", suspended={"reason": "等设计稿", "at": "2026-10-18T00:00:00+08:00", "original": "挂起 b"})
        p = start.plan(self.repo)
        self.assertEqual(p.slots, 2)
        self.assertEqual([m["id"] for m in p.modules], ["c", "d"])      # problem H

    def test_merged_module_frees_its_slot(self):
        db = self.dev("b")
        with db.transaction(actor="t") as tx:
            tx.put("item", "9", {"kind": "merge-approval", "module": "b", "state": "closed", "closedReason": "merged"},
                   action="merged")
        self.assertEqual(start.plan(self.repo).slots, 2)                # problem O

    def test_reasons_when_nothing_startable(self):
        from helpers import START_MAP
        mods = [dict(m) for m in START_MAP["modules"]]
        for m in mods:
            m["status"] = {"a": "done", "b": "in_progress", "c": "done", "d": "done", "e": "not_ready"}[m["id"]]
        mods[1]["step"] = "写 Spec"
        self.set_map(dict(START_MAP, modules=mods, startable={"modules": [], "conflicts": []}))
        p = start.plan(self.repo)
        self.assertEqual(p.modules, [])
        reasons = {r["module"]: r["reason"] for r in p.reasons}
        self.assertIn("spec-guard 的当前模块", reasons["b"])
        self.assertIn("等 b", reasons["e"])
        r = self.run_cli("start", "plan")
        self.assertEqual(r.returncode, 3)
        self.assertIn("b：", r.stdout)
        self.assertIn("e：", r.stdout)
        import json
        doc = json.loads(self.run_cli("start", "plan", "--json").stdout)
        self.assertEqual({x["module"] for x in doc["reasons"]}, {"b", "e"})


STOP = {"file": "docs/usage-draft.md", "milestone": "M1 下单跑通", "modules": ["a"], "usages": ["U1"]}


class MilestoneStopPlanTest(StartCase):
    """S92: spec-guard 0.88.0 (interface 1.13) /map --json milestoneStop."""

    def test_stop_proposes_nothing(self):
        from helpers import START_MAP
        self.set_map(dict(START_MAP, milestoneStop=STOP))
        p = start.plan(self.repo)
        self.assertEqual(p.modules, [])
        self.assertTrue(any("里程碑停点：M1 下单跑通 还没确认（docs/usage-draft.md），用户确认后再开" in b
                            for b in p.blockers), p.blockers)
        r = self.run_cli("start", "plan")
        self.assertEqual(r.returncode, 3)
        self.assertIn("里程碑停点", r.stdout)
        self.assertNotIn("提议：", r.stdout)

    def test_unreadable_still_proposes_with_note(self):
        from helpers import START_MAP
        self.set_map(dict(START_MAP, milestoneStop={"error": "unreadable", "detail": "草案缺表头"}))
        p = start.plan(self.repo)
        self.assertEqual(p.blockers, [])
        self.assertEqual([m["id"] for m in p.modules], ["b", "c"])
        note = "停点读不出（草案缺表头），先跑 /spec-guard:verify-artifacts"
        self.assertEqual(p.warnings, [note])
        r = self.run_cli("start", "plan")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(note, r.stdout)
        import json
        self.assertEqual(json.loads(self.run_cli("start", "plan", "--json").stdout)["warnings"], [note])

    def test_null_or_absent_unchanged(self):
        from helpers import START_MAP
        for doc in (dict(START_MAP, milestoneStop=None), START_MAP):
            with self.subTest(doc="milestoneStop" in doc):
                self.set_map(doc)
                p = start.plan(self.repo)
                self.assertEqual((p.blockers, p.warnings), ([], []))
                self.assertEqual([m["id"] for m in p.modules], ["b", "c"])


if __name__ == "__main__":
    unittest.main()
