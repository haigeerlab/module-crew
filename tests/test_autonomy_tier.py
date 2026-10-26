"""crew-autonomy-tier: spec-guard autonomyTier, the step-down cap, standard and relaxed, step-up advice
(see spec/crew-autonomy-tier.md)."""

import io
import json
import os
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from helpers import MergeCase, ReviewCase, StartCase, git

from module_crew import autonomy, declared, merge, review, sources, start, store
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


class IncidentBase(TierMixin, MergeCase):
    def setUp(self):
        super().setUp()
        self.with_tier()
        self.set_tier("relaxed", "combined")
        git(self.repo, "commit", "-qam", "tier relaxed")
        self.db = store.open_store(self.repo)

    def lowered(self):
        return [e for e in autonomy.marks(self.db) if e["type"] == "config.tier-lowered"]

    def effective(self):
        return autonomy.effective(self.db, self.repo).value


class IncidentTest(IncidentBase):
    """Acceptance 6 and 7."""

    def test_merge_returned_lowers_one_step_once(self):
        n = self.approve_final("b", 1)
        res = merge.run(self.repo, check_command=self.check_script(fail_if="src/b.py"))
        self.assertEqual(res.code, 5)
        text = "\n".join(res.lines)
        self.assertIn("自治档位已从 relaxed 降到 standard：合并因模块的原因退回", text)
        self.assertIn("马上告诉用户", text)
        self.assertEqual(self.effective(), "standard")
        self.assertEqual(autonomy.incident(self.db, self.repo, "merge-returned", str(n)), None)   # same item: once
        self.assertEqual(len(self.lowered()), 1)

    def test_env_return_does_not_lower(self):
        self.approve_final("b", 1)
        res = merge.run(self.repo, check_command=self.check_script(sleep=3))
        self.assertNotIn("自治档位", "\n".join(res.lines))
        self.assertEqual(self.effective(), "relaxed")

    def test_revoke_lowers(self):
        n = self.approve_final("b", 1)
        note = merge.revoke(self.db, n, "撤回")
        self.assertIn("降到 standard：用户撤销合并批准", note.tier_line)

    def test_down_to_strict_then_nothing(self):
        self.assertIsNotNone(autonomy.incident(self.db, self.repo, "baseline-red", "t1"))
        self.assertIsNotNone(autonomy.incident(self.db, self.repo, "baseline-red", "t2"))
        self.assertEqual(self.effective(), "strict")
        self.assertIsNone(autonomy.incident(self.db, self.repo, "baseline-red", "t3"))
        self.assertEqual(len(self.lowered()), 2)
        self.assertEqual(start.review_cadence(self.repo), "separate")

    def test_restore(self):
        with self.assertRaises(autonomy.Refused):
            autonomy.restore(self.db, self.repo, "恢复")              # no cap yet
        autonomy.incident(self.db, self.repo, "revoked", "1")
        autonomy.incident(self.db, self.repo, "revoked", "2")
        with self.assertRaises(autonomy.Refused):
            autonomy.restore(self.db, self.repo, " ")
        self.assertIn("恢复到 standard", autonomy.restore(self.db, self.repo, "恢复一档")[0])
        self.assertEqual(self.effective(), "standard")
        self.assertIn("降档上限清掉", autonomy.restore(self.db, self.repo, "再恢复")[0])
        self.assertEqual((self.effective(), autonomy.state(self.db).get("cap")), ("relaxed", None))
        restored = [e for e in autonomy.marks(self.db) if e["type"] == "config.tier-restored"]
        self.assertEqual(restored[0]["data"]["original"], "恢复一档")

    def test_restore_cli_needs_words(self):
        autonomy.incident(self.db, self.repo, "revoked", "1")
        code, _ = self.cli("tier", "restore", "--original", " ")
        self.assertEqual(code, 3)
        code, out = self.cli("tier", "restore", "--original", "恢复")
        self.assertEqual(code, 0)
        self.assertIn("恢复到 relaxed", out)

    def test_strict_tier_never_lowers(self):
        self.set_tier("strict")
        self.assertIsNone(autonomy.incident(self.db, self.repo, "revoked", "9"))


class ReworkIncidentTest(IncidentBase):
    def test_rework_over_limit_lowers(self):
        from test_review_nearby import CHANGES, conclusion
        sources.add(self.db, "arch", "lead", "登记审查会话", scope=sources.ALL_SCOPE)
        rid = 5000

        def submit():
            nonlocal rid
            rid += 1
            return review.add(self.db, self.spec_review("b"), "shop-b", rid).number
        n = submit()
        for _ in range(3):
            review.note(self.db, n, "arch", conclusion("有须修改项2条", CHANGES))
            n = submit()
        res = review.note(self.db, n, "arch", conclusion("有须修改项2条", CHANGES))
        self.assertIn("降到 standard：返工满 3 次", "\n".join(res.lines))


class BaselineIncidentTest(TierMixin, MergeCase):
    def test_new_red_baseline_lowers_old_record_does_not(self):
        import test_check_ledger as tcl
        from module_crew import hooks
        self.with_tier()
        self.set_tier("relaxed", "combined")
        git(self.repo, "commit", "-qam", "tier relaxed")
        ledger = tcl.BaselineTest.__new__(tcl.BaselineTest)        # borrow its helpers on this repo
        ledger.__dict__.update(self.__dict__)
        ledger.db = store.open_store(self.repo)
        hooks.bind(ledger.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")
        ledger.red_switch()
        ledger.commit_main("fail.flag")
        out = ledger.baseline()
        self.assertEqual(out.returncode, 5, out.stdout + out.stderr)
        self.assertIn("自治档位已从 relaxed 降到 standard：基线完整检查新跑出失败", out.stdout)
        out = ledger.baseline()                                    # the recorded failure, not a new run
        self.assertNotIn("自治档位", out.stdout)
        self.assertEqual(autonomy.effective(ledger.db, self.repo).value, "standard")


if __name__ == "__main__":
    unittest.main()
