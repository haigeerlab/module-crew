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


# ---------------------------------------------------------------- Task 2: reading the takeover

FAKE_SHOW = '''import json, os, sys
if os.environ.get("FAKE_SHOW_FAIL"):
    sys.exit(int(os.environ["FAKE_SHOW_FAIL"]))
value = json.loads(os.environ.get("FAKE_TAKEOVER", '"none"'))
source = os.environ.get("FAKE_TAKEOVER_SOURCE", "default")
print(json.dumps({"items": [{"key": "reviewCadence", "value": "separate", "source": "default"},
                            {"key": "takeover", "value": value, "source": source}], "problems": []}))
'''

NARROW_COMMAND = ["python3", "-B", "hooks/project_config.py", "narrow", "--project", "<project-root>",
                  "[--module <module-id>]", "--source", "<source>", "--reason", "<one line, at most 200 characters>",
                  "[--confirm]"]


def takeover_row(spec="human", plan="human", merge="human", source=".agent/config.json", reasons=()):
    return {"takeover": {"spec": spec, "plan": plan, "merge": merge, "release": "human", "source": source,
                         "widerThanProject": False, "narrowed": None},
            "important": {"reasons": list(reasons)}}


class TakeoverMixin:
    """A fake spec-guard 0.91.0 (interface 1.15) and delegate 1.5; each module's takeover lives in the fake /map."""

    def with_takeover(self, version: str = "1.15", plugin_version: str = "0.91.0", delegate: str | None = "1.5"):
        import os
        from pathlib import Path
        entry = self.plugins.entries["spec-guard@m"][-1]
        entry["version"] = plugin_version
        self.plugins.write()
        root = Path(entry["installPath"])
        doc = json.loads((root / "interface.json").read_text())
        doc["interface"] = version
        if version >= "1.15":
            doc["takeover"] = {"key": "takeover", "default": "none"}
            doc["takeoverNarrow"] = {"command": NARROW_COMMAND}
        else:
            doc.pop("takeover", None)
            doc.pop("takeoverNarrow", None)
        (root / "interface.json").write_text(json.dumps(doc))
        (root / "hooks" / "project_config.py").write_text(FAKE_SHOW)
        if delegate is not None:
            report = {"schemaVersion": 1, "severity": {"field": "findings[].severity"}} if delegate >= "1.5" else {"schemaVersion": 1}
            self.plugins.install("delegate", {"interface": delegate, "review": {"command": "/delegate:review",
                                                                               "report": report}})
        for k in ("FAKE_TAKEOVER", "FAKE_TAKEOVER_SOURCE", "FAKE_SHOW_FAIL"):
            self.addCleanup(lambda k=k: os.environ.pop(k, None))

    def set_takeover(self, value, rows: dict | None = None, source: str = ".agent/config.json"):
        """Project value for `show`, and per-module rows merged into the fake /map."""
        import os
        from helpers import START_MAP
        os.environ["FAKE_TAKEOVER"] = json.dumps(value)
        os.environ["FAKE_TAKEOVER_SOURCE"] = source
        doc = json.loads(json.dumps(START_MAP))
        for m in doc["modules"]:
            m.update((rows or {}).get(m["id"], takeover_row(source="default")))
        self.set_map(doc)
        (self.repo / ".agent" / "config.json").touch()     # a new mtime: no cached /map


class ReadTakeoverTest(TierMixin, TakeoverMixin, ReviewCase):
    """Task 2, acceptance 1 and 2."""

    def db(self):
        return store.open_store(self.repo)

    def test_presets_custom_module_and_forced(self):
        from module_crew import takeover
        self.with_takeover()
        self.set_takeover("plan", {"b": takeover_row(plan="codex"),
                                   "c": takeover_row(spec="codex", plan="codex", merge="auto", reasons=["multi-module"],
                                                     source="moduleTakeover.c")})
        db = self.db()
        b = takeover.module(db, self.repo, "b")
        self.assertEqual((b.spec, b.plan, b.merge, b.usable), ("human", "codex", "human", True))
        c = takeover.module(db, self.repo, "c")
        self.assertEqual(c.forced, {"spec": "重要需求：跨模块"})
        self.assertEqual(takeover.approver(db, self.repo, "c", "spec"), "human")
        self.assertEqual(takeover.approver(db, self.repo, "c", "plan"), "codex")
        self.assertEqual(takeover.approver(db, self.repo, "c", "final"), "human")
        self.assertEqual(takeover.line(c), "批准方式：Spec 人批（重要需求：跨模块）、Plan Codex 放行、合并 自动合")
        plan = "# Plan\n\n## 预先声明\n\n- 公共路径：`config/app.json`\n\n## Task List\n"
        self.assertEqual(takeover.approver(db, self.repo, "c", "plan", plan), "human")
        self.assertEqual(takeover.approver(db, self.repo, "c", "plan", plan.replace("- 公共路径：`config/app.json`", "无")), "codex")
        doc = json.loads(self.cli("tier", "--json")[1])
        self.assertEqual(doc["takeover"]["value"], "plan")
        self.assertEqual({m["module"]: m["plan"] for m in doc["modules"]}, {"b": "codex", "c": "codex"})
        out = self.cli("tier")[1]
        self.assertIn("接管档位：只接管 Plan（.agent/config.json）", out)
        self.assertIn("c：批准方式：Spec 人批（重要需求：跨模块）、Plan Codex 放行、合并 自动合（模块单独设", out)
        self.set_takeover({"spec": "codex", "plan": "human"})
        self.assertIn("接管档位：自定义（spec=codex、plan=human）", self.cli("tier")[1])

    def test_unreadable_is_human(self):
        from module_crew import takeover
        self.with_takeover(version="1.14")
        b = takeover.module(self.db(), self.repo, "b")
        self.assertEqual((b.usable, b.spec, b.plan), (False, "human", "human"))
        self.assertIn("低于 1.15", b.reason)
        self.assertEqual(takeover.approver(self.db(), self.repo, "b", "plan"), "human")
        self.assertIn("读不到接管档位", self.cli("tier")[1])

    def test_status_only_when_something_is_taken_over(self):
        self.with_takeover()
        self.set_takeover("none")
        out = self.cli("status")[1]
        self.assertNotIn("接管档位", out)
        self.assertIsNone(json.loads(self.cli("status", "--json")[1])["store"]["takeover"])
        self.set_takeover("plan", {"b": takeover_row(plan="codex")})
        out = self.cli("status")[1]
        self.assertIn("接管档位：只接管 Plan", out)
        self.assertIn("b：批准方式：Spec 人批、Plan Codex 放行、合并 人合", out)
        self.assertIn("Codex 放行：Spec 0 次、Plan 0 次", out)
        doc = json.loads(self.cli("status", "--json")[1])["store"]["takeover"]
        self.assertEqual(doc["codex"]["plan"], 0)

    def test_preflight(self):
        self.with_takeover()
        code, out = self.cli("tier", "--preflight")
        self.assertEqual(code, 0, out)
        self.assertIn("可以写 takeover", out)
        self.with_takeover(version="1.14", plugin_version="0.90.1")
        code, out = self.cli("tier", "--preflight")
        self.assertEqual(code, 3)
        self.assertIn("0.90.1 低于 0.91.0", out)
        self.assertIn("没有 takeover", out)

    def test_preflight_old_delegate(self):
        self.with_takeover(delegate="1.4")
        code, out = self.cli("tier", "--preflight")
        self.assertEqual(code, 3)
        self.assertIn("低于 1.5", out)


# ---------------------------------------------------------------- Task 3: showing it, batches, split cadence

class ShowTakeoverTest(TierMixin, TakeoverMixin, ReviewCase):
    """Task 3, acceptance 3 and 8."""

    def db(self):
        return store.open_store(self.repo)

    def test_codex_item_is_registered_and_kept_out_of_the_batch(self):
        from module_crew import review
        self.with_takeover()
        self.set_takeover("plan", {"b": takeover_row(plan="codex"), "c": takeover_row(plan="codex")})
        db = self.db()
        out = review.add(db, self.plan_review("b"), "shop-b", 1)
        self.assertEqual(out.code, 0, out.lines)
        self.assertIn("Codex 放行：下一步 review codex", "\n".join(out.lines))
        rec = store.get(db, "item", str(out.number))
        self.assertEqual((rec["reviewer"], rec["sentTo"]), ("codex", ["codex"]))
        self.assertEqual(out.sends, [])
        spec_c = review.add(db, self.spec_review("c"), "shop-c", 2)        # Spec stays human
        self.assertNotIn("reviewer", store.get(db, "item", str(spec_c.number)))
        b = review.batch(self.repo)
        ready = {i["number"]: i["ready"] for i in b["items"]}
        self.assertEqual((ready[out.number], ready[spec_c.number]), (False, True))
        self.assertEqual(len(b["codex"]), 1)
        self.assertIn(f"C{out.number} b 的 Plan", b["codex"][0])
        self.assertEqual(review.review_state(db, out.number, now=__import__("datetime").datetime(2100, 1, 1,
                         tzinfo=__import__("datetime").timezone.utc)), "reviewing")    # no timeout for Codex
        text = self.cli("review", "batch")[1]
        self.assertIn("另有 1 项由 Codex 审查中（不提请你批）", text)
        cards = "\n".join(t for _, _, t in review.for_hub(self.repo))
        self.assertNotIn("b 的 Plan", cards)

    def test_predeclared_plan_goes_to_the_user(self):
        from module_crew import review
        self.with_takeover()
        self.set_takeover("plan", {"b": takeover_row(plan="codex")})
        plan = self.wt["b"] / "tasks" / "b" / "plan.md"
        plan.write_text(plan.read_text() + "\n## 预先声明\n\n- 公共路径：`config/app.json`\n", encoding="utf-8")
        git(self.wt["b"], "commit", "-qam", "declare")
        out = review.add(self.db(), self.plan_review("b"), "shop-b", 1)
        self.assertNotIn("reviewer", store.get(self.db(), "item", str(out.number)))

    def test_split_approvers_are_separate(self):
        self.with_takeover()
        self.set_takeover("plan", {"b": takeover_row(plan="codex"), "c": takeover_row()})
        cfg = json.loads((self.repo / ".agent" / "config.json").read_text())
        (self.repo / ".agent" / "config.json").write_text(json.dumps({**cfg, "reviewCadence": "combined"}))
        self.assertEqual(start.review_cadence(self.repo), "combined")
        self.assertEqual(start.review_cadence(self.repo, None, "b"), "separate")
        self.assertEqual(start.review_cadence(self.repo, None, "c"), "combined")
        self.set_takeover("plan", {"b": takeover_row(spec="codex", plan="codex", reasons=["new-module"])})
        self.assertEqual(start.review_cadence(self.repo, None, "b"), "separate")    # important Spec: user; Plan: Codex


class KickoffTakeoverTest(TierMixin, TakeoverMixin, StartCase):
    def test_kickoff_line_and_cadence(self):
        self.with_takeover()
        self.set_takeover("plan", {"b": takeover_row(plan="codex")})
        cfg = json.loads((self.repo / ".agent" / "config.json").read_text())
        (self.repo / ".agent" / "config.json").write_text(json.dumps({**cfg, "reviewCadence": "combined"}))
        git(self.repo, "commit", "-qam", "takeover")
        self.set_takeover("plan", {"b": takeover_row(plan="codex")})
        res = start.prepare(self.repo, ["b", "c"], "开 b 和 c", short="shop", max_modules=3)
        assert res.code == 0, res.lines
        db = store.open_store(self.repo)
        texts = {p["id"]: store.read_body(db, p["kickoff"]) for p in res.prepared}
        self.assertIn("项目评审节奏：separate", texts["b"])
        self.assertIn("批准方式：Spec 人批、Plan Codex 放行、合并 人合", texts["b"])
        self.assertIn("项目评审节奏：combined", texts["c"])
        self.assertNotIn("批准方式", texts["c"])
