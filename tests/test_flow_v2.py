"""crew-flow-v2: spec-guard flow v2 modules (interface 1.18 tier) -- review nodes, starting, approvers, display."""

import json
import unittest

from helpers import START_MAP, ReviewCase
from module_crew import flow, probe, store
from test_autonomy_tier import TierMixin
from test_declared_scope import DeclaredMixin
from test_takeover_approve import TakeoverMixin, takeover_row


class FlowMixin(TierMixin, TakeoverMixin, DeclaredMixin):
    """A fake spec-guard 1.18: every module in the fake /map carries its takeover row and, when given, a tier."""

    def with_flow(self, version: str = "1.18"):
        self.with_takeover(version=version, plugin_version="0.94.0")

    def set_flow(self, tiers: dict, rows: dict | None = None, steps: dict | None = None):
        doc = json.loads(json.dumps(START_MAP))
        for m in doc["modules"]:
            m.update((rows or {}).get(m["id"], takeover_row(source="default")))
            if m["id"] in tiers:
                m["tier"] = tiers[m["id"]]
            if m["id"] in (steps or {}):
                m["step"] = steps[m["id"]]
        self.set_map(doc)
        (self.repo / ".agent" / "config.json").touch()

    def db(self):
        return store.open_store(self.repo)


class RecognizeTest(FlowMixin, ReviewCase):
    """Task 1, decision 1, acceptance 1."""

    def test_reads_five_kinds(self):
        self.with_flow()
        self.set_flow({"b": "normal", "c": "bug", "d": "important", "e": "small"})
        db = self.db()
        got = {m: flow.tier(db, self.repo, m) for m in ("a", "b", "c", "d", "e")}
        self.assertEqual(got, {"a": None, "b": "normal", "c": "bug", "d": "important", "e": "small"})
        self.assertTrue(flow.is_v2(got["c"]))
        self.assertFalse(flow.is_v2(got["a"]))
        self.assertEqual([m for m, t in got.items() if flow.full_docs(t)], ["b", "d"])

    def test_null_and_unknown_tier(self):
        self.assertIsNone(flow.tier_of({"tier": None}))
        self.assertIsNone(flow.tier_of({}))
        self.assertEqual(flow.tier_of({"tier": "huge"}), "normal")

    def test_older_spec_guard_is_old_flow(self):
        self.with_flow(version="1.17")
        self.set_flow({})                  # 1.17 has no tier field at all
        db = self.db()
        self.assertIsNone(flow.tier(db, self.repo, "b"))

    def test_no_takeover_interface_is_old_flow(self):
        db = self.db()                     # the plain fake spec-guard 1.7: /map is read but no takeover
        self.assertIsNone(flow.tier(db, self.repo, "b"))

    def test_step_words_and_probe_summary(self):
        self.assertEqual(flow.step_word({"step": "design"}), "写技术方案")
        self.assertEqual(flow.step_word({"step": "regression"}), "写回归")
        self.assertIsNone(flow.step_word({"step": "plan"}))
        doc = {"modules": [{"id": "a", "status": "done"}, {"id": "b", "tier": "normal", "status": "in_progress"}]}
        self.assertEqual(probe.summarize_map(doc)["flowV2"], {"b": "normal"})
        self.assertNotIn("flowV2", probe.summarize_map({"modules": [{"id": "a", "status": "done"}]}))


if __name__ == "__main__":
    unittest.main()
