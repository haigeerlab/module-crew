"""crew-autonomy-tier: spec-guard autonomyTier, the step-down cap, standard and relaxed, step-up advice
(see spec/crew-autonomy-tier.md)."""

from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from helpers import MergeCase, ReviewCase, git

from module_crew import autonomy, merge, review, sources, start, store

# A spec-guard project_config.py show that reads the checkout's own .agent/config.json like the real one.
FAKE_CONFIG = '''import json, os, sys
args = sys.argv[1:]
if os.environ.get("FAKE_CONFIG_FAIL"):
    sys.exit(int(os.environ["FAKE_CONFIG_FAIL"]))
project = args[args.index("--project") + 1]
try:
    cfg = json.load(open(os.path.join(project, ".agent", "config.json")))
except (OSError, ValueError):
    cfg = None
items = []
for key, default in (("reviewCadence", "separate"), ("autonomyTier", "strict")):
    if cfg is None:
        items.append({"key": key, "value": default, "source": "default (config invalid)"})
    elif key in cfg:
        ok = {"reviewCadence": ("separate", "combined"), "autonomyTier": ("strict", "standard", "relaxed")}[key]
        if cfg[key] in ok:
            items.append({"key": key, "value": cfg[key], "source": ".agent/config.json"})
        else:
            items.append({"key": key, "value": default, "source": "default (config invalid)"})
    else:
        items.append({"key": key, "value": default, "source": "default"})
print(json.dumps({"items": items, "problems": []}))
'''


class TierMixin:
    """A fake spec-guard 1.11 with autonomyTier; the tier lives in the integration checkout's .agent/config.json."""

    def with_tier(self, version: str = "1.11", plugin_version: str = "0.85.0"):
        entry = self.plugins.entries["spec-guard@m"][-1]
        entry["version"] = plugin_version
        self.plugins.write()
        root = Path(entry["installPath"])
        doc = json.loads((root / "interface.json").read_text())
        doc["interface"] = version
        if version >= "1.11":
            doc["autonomyTier"] = {"config": ".agent/config.json", "key": "autonomyTier", "default": "strict"}
        else:
            doc.pop("autonomyTier", None)
        (root / "interface.json").write_text(json.dumps(doc))
        (root / "hooks" / "project_config.py").write_text(FAKE_CONFIG)
        self.addCleanup(lambda: os.environ.pop("FAKE_CONFIG_FAIL", None))

    def set_tier(self, tier: str | None, cadence: str | None = None, raw: str | None = None):
        path = self.repo / ".agent" / "config.json"
        if raw is not None:
            path.write_text(raw)
            return
        cfg = json.loads(path.read_text())
        for key, value in (("autonomyTier", tier), ("reviewCadence", cadence)):
            if value is None:
                cfg.pop(key, None)
            else:
                cfg[key] = value
        path.write_text(json.dumps(cfg))

    def db(self):
        return store.open_store(self.repo)

    def cli(self, *argv) -> tuple[int, str]:
        from module_crew.__main__ import main
        out = io.StringIO()
        old = os.getcwd()
        os.chdir(self.repo)
        try:
            with redirect_stdout(out):
                code = main(list(argv))
        finally:
            os.chdir(old)
        return code, out.getvalue()


class ReadTest(TierMixin, ReviewCase):
    def test_tier_writes_nothing_and_has_no_retired_hint(self):
        """T827: the old tier is no longer read at all, set or not."""
        self.with_tier()
        for tier in (None, "relaxed"):
            self.set_tier(tier)
            code, out = self.cli("tier")
            self.assertEqual(code, 0)
            self.assertNotIn("autonomyTier 已退役", out)
            self.assertNotIn("retiredTier", json.loads(self.cli("tier", "--json")[1]))
            self.assertNotIn("autonomy", store.get(self.db(), "config", "main") or {})


def cap(db, to: str, configured: str):
    """Pretend an incident lowered the tier to `to` while `configured` was set."""
    with db.transaction(actor="test") as tx:
        cfg = tx.get("config", "main")
        tx.put("config", "main", {**cfg, "autonomy": {"cap": to, "capFor": configured}}, action="tier-lowered")


class IncidentBase(TierMixin, MergeCase):
    def setUp(self):
        super().setUp()
        self.with_tier()
        self.set_tier("relaxed", "combined")
        git(self.repo, "commit", "-qam", "tier relaxed")
        self.db = store.open_store(self.repo)



def fake_merged(db, module: str, rework: int = 0):
    """A module merged through the queue (and its rework rounds), as the store records it."""
    with db.transaction(actor="test") as tx:
        for _ in range(rework):
            k = tx.allocate_number()
            tx.put("item", str(k), {"kind": "review", "module": module, "node": "spec", "state": "open"},
                   action="rework-sent", data={"module": module, "node": "spec"})
        n = tx.allocate_number()
        tx.put("item", str(n), {"kind": "merge-approval", "module": module, "task": None, "state": "closed",
                                "closedReason": "merged"}, action="merged")


class DigestTest(IncidentBase):
    """Acceptance 5."""

    def test_lists_and_marks(self):
        from module_crew import checks
        fake_merged(self.db, "b")
        checks.record(self.db, {"tree": "a" * 40, "kind": "quick", "command": "q", "result": "pass", "exitCode": 0,
                                "tail": "", "commit": None, "where": str(self.wt["c"]), "by": "shop-c",
                                "startedAt": store.now(), "seconds": 1, "inheritedFrom": None})
        with self.db.transaction(actor="test") as tx:
            n = tx.allocate_number()
            tx.put("request", str(n), {"from": "shop-c", "files": ["shared/x.ts"], "state": "closed",
                                       "closedReason": "landed", "commit": "c" * 40, "fromModule": {"commit": "d" * 40},
                                       "toldUser": False}, action="landed", data={"commit": "c" * 40})
        autonomy.incident(self.db, self.repo, "revoked", "77")                # never in the digest
        code, out = self.cli("tier", "digest")
        self.assertEqual(code, 0, out)
        self.assertIn("收尾汇总", out)
        self.assertIn("- b：", out)
        self.assertIn("合入集成分支", out)
        self.assertIn("- c：", out)
        self.assertIn("快检查 通过（树 aaaaaaa）", out)
        self.assertIn(f"C{n}", out)
        self.assertIn("shared/x.ts", out)
        self.assertNotIn("降到", out)
        code, out = self.cli("tier", "digest", "--json")
        doc = json.loads(out)
        self.assertEqual(sorted(doc["groups"]), ["b", "c", "集成分支"])          # the tier commit is unqueued
        self.assertIn("不经合并队列的提交", "".join(doc["groups"]["集成分支"]))
        code, out = self.cli("tier", "digest", "--mark-told")
        self.assertEqual(code, 0)
        self.assertEqual(store.get(self.db, "request", str(n))["toldUser"], True)
        code, out = self.cli("tier", "digest")
        self.assertEqual(code, 3, out)


class StatusTest(TierMixin, ReviewCase):
    """Decision 9."""

    def test_unset_shows_nothing(self):
        self.with_tier()
        code, out = self.cli("status")
        self.assertNotIn("自治档位", out)
        self.assertNotIn("档位", out)
        code, out = self.cli("status", "--json")
        self.assertIsNone(json.loads(out)["store"]["autonomy"])

    def test_old_tier_shows_nothing(self):
        self.with_tier()
        self.set_tier("relaxed", "combined")
        code, out = self.cli("status")
        self.assertNotIn("autonomyTier 已退役", out)
        self.assertIsNone(json.loads(self.cli("status", "--json")[1])["store"]["autonomy"])


class FloorTest(TierMixin, MergeCase):
    """Acceptance 9: no tier goes below the floor."""

    def setUp(self):
        super().setUp()
        self.with_tier()
        self.set_tier("relaxed", "combined")
        git(self.repo, "commit", "-qam", "tier relaxed")
        self.db = store.open_store(self.repo)

    def test_spec_approval_still_needs_words(self):
        n = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        res = review.approve(self.repo, [n], " ")
        self.assertEqual(res.code, 3)
        self.assertIn("用户原话不能为空", "\n".join(res.lines))

    def test_final_acceptance_still_needs_an_answer(self):
        out = review.add(self.db, self.finish("b"), "shop-b", 2)
        res = review.approve(self.repo, [out.number], "批")
        self.assertEqual(res.code, 3)
        self.assertIn("最终验收：批准合并用 merge approve", "\n".join(res.lines))   # crew-final-accept-split

    def test_kickoff_still_waits_for_the_start_notice(self):
        res = start.prepare(self.repo, ["d"], "开 d", short="shop", max_modules=3)
        self.assertEqual(res.code, 0, res.lines)
        text = store.read_body(self.db, res.prepared[0]["kickoff"])
        self.assertIn("收到开工类【协调通知】之前不要开始构建", text)
