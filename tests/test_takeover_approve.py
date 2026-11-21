"""crew-takeover-approve: spec-guard takeover, Codex as a reviewer, separate bookkeeping, narrowing on incidents,
and the retirement of autonomyTier (see spec/crew-takeover-approve.md)."""

import json

from helpers import MergeCase, ReviewCase, StartCase, git

from module_crew import declared, start, store
from test_autonomy_tier import TierMixin
from test_declared_scope import DeclaredMixin, usable


class RetireTest(TierMixin, DeclaredMixin, ReviewCase):
    """Task 1, acceptance 11: an old autonomyTier no longer has any effect."""

    def test_old_tier_no_longer_opens_declared_scope_or_combined(self):
        self.with_declared({"b": usable()})
        self.with_tier()
        self.set_tier("relaxed", "separate")
        db = self.db()
        self.assertFalse(declared.enabled(db))                     # never set: off, whatever the old tier says
        self.switch("on")
        self.assertTrue(declared.enabled(db))
        self.switch("off")
        self.assertFalse(declared.enabled(db))
        self.assertEqual(start.review_cadence(self.repo), "separate")

    def test_old_cap_no_longer_forces_separate(self):
        self.with_tier()
        self.set_tier("standard", "combined")
        db = self.db()
        with db.transaction(actor="test") as tx:
            cfg = tx.get("config", "main")
            tx.put("config", "main", {**cfg, "autonomy": {"cap": "strict", "capFor": "standard"}}, action="tier-lowered")
        self.assertEqual(start.review_cadence(self.repo), "combined")   # only spec-guard's reviewCadence counts

    def test_migration_hint(self):
        self.with_tier()
        code, out = self.cli("tier")
        self.assertNotIn("autonomyTier 已退役", out)
        self.set_tier("relaxed")
        code, out = self.cli("tier")
        self.assertEqual(code, 0)
        self.assertIn("autonomyTier 已退役、不再生效（旧值 relaxed 不映射为接管档位）", out)
        doc = json.loads(self.cli("tier", "--json")[1])
        self.assertEqual(doc["retiredTier"], "relaxed")
        code, out = self.cli("status")
        self.assertIn("autonomyTier 已退役", out)
        self.assertNotIn("可以建议升到", out)

    def test_status_unchanged_without_old_tier(self):
        self.with_tier()
        code, out = self.cli("status")
        self.assertNotIn("档位", out)
        self.assertIsNone(json.loads(self.cli("status", "--json")[1])["store"]["autonomy"])

    def test_restore_is_retired(self):
        self.with_tier()
        code, out = self.cli("tier", "restore", "--original", "恢复")
        self.assertEqual(code, 3)

    def test_digest_switch(self):
        code, _ = self.cli("config", "set", "--digest", "on", "--original", " ")
        self.assertEqual(code, 3)
        code, out = self.cli("config", "set", "--digest", "on", "--original", "打开收尾汇总")
        self.assertEqual(code, 0)
        self.assertIn("已打开收尾汇总", out)
        self.assertEqual(store.get(self.db(), "config", "main")["digest"], "on")
        code, out = self.cli("tier")
        self.assertIn("收尾汇总：开", out)


class RetireKickoffTest(TierMixin, StartCase):
    def test_kickoff_follows_review_cadence_only(self):
        self.with_tier()
        self.set_tier("relaxed", "separate")
        git(self.repo, "commit", "-qam", "old tier")
        res = start.prepare(self.repo, ["b"], "开 b", short="shop", max_modules=3)
        assert res.code == 0, res.lines
        text = store.read_body(store.open_store(self.repo), res.prepared[0]["kickoff"])
        self.assertIn("项目评审节奏：separate", text)


class RetireMergeTest(MergeCase):
    def test_merge_run_never_advises(self):
        import inspect
        from module_crew import autonomy, merge
        self.assertNotIn("suggestion_line", inspect.getsource(merge))
        self.assertFalse(hasattr(autonomy, "suggestion_line"))
