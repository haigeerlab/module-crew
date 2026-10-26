"""crew-autonomy-tier: spec-guard autonomyTier, the step-down cap, standard and relaxed, step-up advice
(see spec/crew-autonomy-tier.md)."""

import io
import json
import os
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from helpers import ReviewCase, StartCase, git

from module_crew import autonomy, declared, start, store
from test_declared_scope import DeclaredMixin, request, usable

READ_FROM = ("python3 -B hooks/project_config.py show --project <project-root> --format json: the item whose key is "
             "autonomyTier, with value and source")

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

    def with_tier(self, version: str = "1.11", read_from: str = READ_FROM, plugin_version: str = "0.85.0"):
        entry = self.plugins.entries["spec-guard@m"][-1]
        entry["version"] = plugin_version
        self.plugins.write()
        root = Path(entry["installPath"])
        doc = json.loads((root / "interface.json").read_text())
        doc["interface"] = version
        if version >= "1.11":
            doc["autonomyTier"] = {"config": ".agent/config.json", "key": "autonomyTier", "default": "strict",
                                   "readFrom": read_from}
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
    def test_three_values_and_sources(self):
        self.with_tier()
        for value in ("strict", "standard", "relaxed"):
            self.set_tier(value)
            t = autonomy.read(self.repo)
            self.assertEqual((t.value, t.source, t.usable, t.explicit), (value, ".agent/config.json", True, True))
        self.set_tier(None)
        t = autonomy.read(self.repo)
        self.assertEqual((t.value, t.source, t.explicit), ("strict", "default", False))
        self.set_tier("loose")
        t = autonomy.read(self.repo)
        self.assertEqual((t.value, t.source, t.explicit), ("strict", "default (config invalid)", False))

    def test_unreadable_reads_as_strict_with_reason(self):
        self.with_tier(version="1.10")
        self.set_tier("relaxed")
        t = autonomy.read(self.repo)
        self.assertEqual((t.value, t.usable), ("strict", False))
        self.assertIn("低于 1.11", t.reason)

        self.with_tier(read_from="python3 hooks/config.py --json")
        t = autonomy.read(self.repo)
        self.assertEqual(t.value, "strict")
        self.assertIn("readFrom 写法和预期不同", t.reason)

        self.with_tier()
        os.environ["FAKE_CONFIG_FAIL"] = "1"
        self.set_tier("standard")          # a new mtime: no cached answer
        t = autonomy.read(self.repo)
        self.assertEqual((t.value, t.usable), ("strict", False))
        self.assertIn("退出码 1", t.reason)

    def test_unset_writes_nothing(self):
        self.with_tier()
        db = self.db()
        eff = autonomy.effective(db, self.repo)
        self.assertEqual((eff.value, eff.active), ("strict", False))
        self.assertNotIn("autonomy", store.get(db, "config", "main") or {})
        code, out = self.cli("tier")
        self.assertEqual(code, 0)
        self.assertIn("档位没设（spec-guard 默认 strict），module-crew 照今天做", out)
        self.assertNotIn("autonomy", store.get(self.db(), "config", "main") or {})

    def test_set_tier_is_seen_once(self):
        self.with_tier()
        self.set_tier("standard")
        db = self.db()
        self.assertEqual(autonomy.effective(db, self.repo).value, "standard")
        autonomy.effective(db, self.repo)
        seen = [e for e in autonomy.marks(db) if e["type"] == "config.tier-seen"]
        self.assertEqual(len(seen), 1)
        code, out = self.cli("tier", "--json")
        doc = json.loads(out)
        self.assertEqual((doc["configured"]["value"], doc["effective"], doc["explicit"], doc["cap"]),
                         ("standard", "standard", True, None))

    def test_cap_lowers_and_clears_when_configured_changes(self):
        self.with_tier()
        self.set_tier("relaxed")
        db = self.db()
        with db.transaction(actor="test") as tx:
            cfg = tx.get("config", "main")
            tx.put("config", "main", {**cfg, "autonomy": {"cap": "standard", "capFor": "relaxed"}}, action="tier-lowered")
        eff = autonomy.effective(db, self.repo)
        self.assertEqual((eff.value, eff.cap), ("standard", "standard"))
        self.set_tier("strict")
        eff = autonomy.effective(db, self.repo)
        self.assertEqual((eff.value, eff.cap), ("strict", None))
        self.assertIn("config.tier-cap-cleared", [e["type"] for e in autonomy.marks(db)])


class PreflightTest(TierMixin, ReviewCase):
    def test_085_passes(self):
        self.with_tier()
        code, out = self.cli("tier", "--preflight")
        self.assertEqual(code, 0, out)
        self.assertIn("可以写 autonomyTier", out)

    def test_older_version_or_interface_refused(self):
        self.with_tier(plugin_version="0.84.2")
        code, out = self.cli("tier", "--preflight")
        self.assertEqual(code, 3)
        self.assertIn("0.84.2 低于 0.85.0", out)
        self.with_tier(version="1.10")
        code, out = self.cli("tier", "--preflight")
        self.assertEqual(code, 3)
        self.assertIn("没有 autonomyTier", out)

    def test_codex_session_adds_a_reminder(self):
        self.with_tier()
        db = self.db()
        with db.transaction(actor="test") as tx:
            tx.put("session", "shop-x", {"role": "dev", "host": "codex-desktop", "status": "active", "module": "x",
                                         "worktree": "/tmp/wx"}, action="registered")
        code, out = self.cli("tier", "--preflight")
        self.assertEqual(code, 0)
        self.assertIn("Codex 那边的 spec-guard 版本 module-crew 查不到", out)


def cap(db, to: str, configured: str):
    """Pretend an incident lowered the tier to `to` while `configured` was set."""
    with db.transaction(actor="test") as tx:
        cfg = tx.get("config", "main")
        tx.put("config", "main", {**cfg, "autonomy": {"cap": to, "capFor": configured}}, action="tier-lowered")


class StandardTest(TierMixin, DeclaredMixin, ReviewCase):
    """Acceptance 4 and the cadence part of 6."""

    def test_declared_scope_follows_the_tier_unless_set(self):
        self.with_declared({"b": usable()})
        self.with_tier()
        db = self.db()
        self.assertFalse(declared.enabled(db))                     # tier unset
        self.set_tier("strict")
        self.assertFalse(declared.enabled(db))
        self.set_tier("standard", "combined")
        self.assertTrue(declared.enabled(db))
        from module_crew import changes
        out = changes.add(db, request(["config/app.json"]), "shop-b", 1)
        self.assertIs(store.get(db, "request", str(out.number))["declared"], True)
        self.switch("off")
        self.assertFalse(declared.enabled(db))                     # the user's own switch wins
        self.switch("on")
        self.set_tier(None)
        self.assertTrue(declared.enabled(db))

    def test_combined_cadence_and_the_hint(self):
        self.with_tier()
        self.set_tier("standard", "combined")
        self.assertEqual(start.review_cadence(self.repo), "combined")
        code, out = self.cli("tier")
        self.assertNotIn("reviewCadence 是 separate", out)
        self.set_tier("standard", "separate")
        self.assertEqual(start.review_cadence(self.repo), "separate")
        code, out = self.cli("tier", "--json")
        doc = json.loads(out)
        self.assertEqual(doc["cadence"], "separate")
        self.assertIn("档位 standard 要 Spec 与 Plan 一起审，但 reviewCadence 是 separate", doc["cadenceHint"])

    def test_cap_to_strict_reads_as_separate(self):
        self.with_tier()
        self.set_tier("standard", "combined")
        cap(self.db(), "strict", "standard")
        value, source, _ = start.cadence_info(self.repo)
        self.assertEqual(value, "separate")
        self.assertIn("降到 strict", source)
        self.set_tier("strict", "combined")                        # the user said something new: cap cleared
        self.assertEqual(start.review_cadence(self.repo), "combined")


class StandardKickoffTest(TierMixin, StartCase):
    def kickoff(self, module):
        res = start.prepare(self.repo, [module], f"开 {module}", short="shop", max_modules=3)
        assert res.code == 0, res.lines
        return store.read_body(store.open_store(self.repo), res.prepared[0]["kickoff"])

    def test_kickoff_cadence(self):
        self.with_tier()
        self.set_tier("standard", "combined")
        git(self.repo, "commit", "-qam", "tier")
        self.assertIn("项目评审节奏：combined", self.kickoff("b"))
        cap(store.open_store(self.repo), "strict", "standard")
        self.assertIn("项目评审节奏：separate", self.kickoff("c"))


if __name__ == "__main__":
    unittest.main()
