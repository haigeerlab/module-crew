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


class AdviceTest(IncidentBase):
    """Acceptance 8."""

    def setUp(self):
        super().setUp()
        self.set_tier("standard", "combined")
        git(self.repo, "commit", "-qam", "tier standard")
        autonomy.effective(self.db, self.repo)                     # the start of the evidence

    def test_three_good_modules_advise_once(self):
        fake_merged(self.db, "x")
        fake_merged(self.db, "y", rework=1)
        code, out = self.cli("tier")
        self.assertNotIn("可以建议升到", out)
        fake_merged(self.db, "z")
        code, out = self.cli("tier", "--json")
        doc = json.loads(out)
        self.assertEqual(doc["suggest"], "relaxed")
        self.assertEqual([r["module"] for r in doc["evidence"]], ["x", "y", "z"])
        code, out = self.cli("tier")
        self.assertIn("可以建议升到 relaxed：最近 3 个模块（x、y、z）", out)
        self.assertIn("不自动升", out)
        self.cli("tier")
        self.assertEqual(len([e for e in store.events(self.db, key="main", kind="config")
                              if e["type"] == "config.tier-suggested"]), 1)
        self.assertEqual(autonomy.effective(self.db, self.repo).value, "standard")   # never a step up by itself

    def test_two_rework_rounds_break_the_streak(self):
        for m, r in (("x", 0), ("y", 2), ("z", 0)):
            fake_merged(self.db, m, rework=r)
        self.assertIsNone(json.loads(self.cli("tier", "--json")[1])["suggest"])

    def test_unset_tier_never_advises(self):
        self.set_tier(None)
        for m in ("x", "y", "z"):
            fake_merged(self.db, m)
        self.assertIsNone(json.loads(self.cli("tier", "--json")[1])["suggest"])

    def test_merge_run_prints_the_advice(self):
        fake_merged(self.db, "x")
        fake_merged(self.db, "y")
        self.approve_final("b", 1)
        res = merge.run(self.repo, check_command="python3 -c pass")
        self.assertEqual(res.code, 0, res.lines)
        self.assertIn("可以建议升到 relaxed：最近 3 个模块（x、y、b）", "\n".join(res.lines))
        self.approve_final("c", 2)
        res = merge.run(self.repo)
        self.assertEqual(res.code, 0, res.lines)
        self.assertNotIn("可以建议升到", "\n".join(res.lines))          # pushed once per start
        self.assertIn("可以建议升到 relaxed", self.cli("tier")[1])      # still shown when asked


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

    def test_set_tier_and_cap(self):
        self.with_tier()
        self.set_tier("relaxed", "combined")
        code, out = self.cli("status")
        self.assertIn("自治档位：设的 relaxed（.agent/config.json），生效 relaxed", out)
        cap(self.db(), "standard", "relaxed")
        code, out = self.cli("status", "--json")
        doc = json.loads(out)["store"]["autonomy"]
        self.assertEqual((doc["configured"], doc["cap"], doc["effective"]), ("relaxed", "standard", "standard"))
        code, out = self.cli("status")
        self.assertIn("生效 standard", out)
        self.assertIn("恢复要用户原话", out)


class FloorTest(TierMixin, MergeCase):
    """Acceptance 9: no tier goes below the floor."""

    def setUp(self):
        super().setUp()
        self.with_tier()
        self.set_tier("relaxed", "combined")
        git(self.repo, "commit", "-qam", "tier relaxed")
        self.db = store.open_store(self.repo)
        self.assertEqual(autonomy.effective(self.db, self.repo).value, "relaxed")

    def test_spec_approval_still_needs_words(self):
        n = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        res = review.approve(self.repo, [n], " ")
        self.assertEqual(res.code, 3)
        self.assertIn("用户原话不能为空", "\n".join(res.lines))

    def test_final_acceptance_still_needs_an_answer(self):
        out = review.add(self.db, self.finish("b"), "shop-b", 2)
        res = review.approve(self.repo, [out.number], "批")
        self.assertEqual(res.code, 3)
        self.assertIn("最终验收：用 review answer 答复", "\n".join(res.lines))

    def test_kickoff_still_waits_for_the_start_notice(self):
        res = start.prepare(self.repo, ["d"], "开 d", short="shop", max_modules=3)
        self.assertEqual(res.code, 0, res.lines)
        text = store.read_body(self.db, res.prepared[0]["kickoff"])
        self.assertIn("收到开工类【协调通知】之前不要开始构建", text)


class SkillTest(unittest.TestCase):
    """Acceptance 10."""
    ROOT = Path(__file__).resolve().parent.parent

    def test_coordinator_and_dev_skills(self):
        for d in ("skills", "codex-skills"):
            coord = (self.ROOT / d / "crew-coordinator" / "SKILL.md").read_text(encoding="utf-8")
            for words in ("module-crew tier --preflight", "reviewCadence=combined", "/spec-guard:config",
                          "module-crew tier digest", "马上告诉用户", "不要自己升", "tier restore --original-file"):
                self.assertIn(words, coord, (d, words))
            dev = (self.ROOT / d / "crew-dev" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("不改变你的停点", dev)
            self.assertIn("gate", dev)


if __name__ == "__main__":
    unittest.main()
