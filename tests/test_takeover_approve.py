"""crew-takeover-approve: spec-guard takeover, Codex as a reviewer, separate bookkeeping, narrowing on incidents,
and the retirement of autonomyTier (see spec/crew-takeover-approve.md)."""

import json
import unittest
from pathlib import Path

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
        code, out = self.cli("tier", "restore")          # Task 11 (M1 note 4): no words needed to get the guidance
        self.assertEqual(code, 3, out)
        self.assertIn("tier restore 已退役", out)
        self.assertIn("/spec-guard:config", out)

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
        if version >= "1.15":                   # Task 9: declaredScope answers "no section" unless a test says otherwise
            from test_declared_scope import DECLARED_COMMAND, FAKE_DECLARED
            doc["declaredScope"] = {"command": DECLARED_COMMAND}
            (root / "interface.json").write_text(json.dumps(doc))
            (root / "hooks" / "module_scope.py").write_text(FAKE_DECLARED)
            out = self.tmp / "declared-out.json"
            out.write_text("{}")
            os.environ["FAKE_DECLARED_OUT"] = str(out)
            self.addCleanup(lambda: os.environ.pop("FAKE_DECLARED_OUT", None))
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


class ReadTakeoverTest(TierMixin, TakeoverMixin, DeclaredMixin, ReviewCase):
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
        self.assertEqual(takeover.approver(db, self.repo, "c", "plan", self.repo), "codex")   # no section: Codex
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

class ShowTakeoverTest(TierMixin, TakeoverMixin, DeclaredMixin, ReviewCase):
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

    def test_predeclared_reads_spec_guard(self):
        """Task 9 (M1 notes 1, 11): spec-guard's declaredScope decides; a malformed section is human, never parsed here."""
        from module_crew import takeover
        from test_declared_scope import DECLARED_COMMAND
        self.with_takeover()
        self.set_takeover("plan", {"c": takeover_row(plan="codex")})
        cases = {"declared": (usable(), "Plan 有预先声明"),
                 "malformed": ({"code": 4, "out": {"error": "unknown-line"}}, "Plan 预先声明格式错误（spec-guard：unknown-line）"),
                 "usage": ({"code": 2, "out": {}}, "读不到 spec-guard 的预先声明判定"),
                 "empty": ({"code": 0, "out": {"declared": True, "publicPaths": [], "configs": [], "patches": [],
                                                "dependencies": []}}, None),
                 "none": ({"code": 0, "out": {"declared": False}}, None)}
        for name, (answer, why) in cases.items():
            with self.subTest(name):
                self.with_declared({"c": answer}, version="1.15")
                (self.repo / ".agent" / "config.json").touch()
                c = takeover.module(self.db(), self.repo, "c", self.repo)
                if why is None:
                    self.assertEqual((c.plan, c.forced), ("codex", {}))
                    self.assertEqual(takeover.approver(self.db(), self.repo, "c", "plan", self.repo), "codex")
                else:
                    self.assertIn(why, c.forced.get("plan", ""))
                    self.assertEqual(takeover.approver(self.db(), self.repo, "c", "plan", self.repo), "human")
        call = json.loads(self.args_log.read_text().splitlines()[-1])
        self.assertEqual(call, DECLARED_COMMAND[3:5] + [str(self.repo)] + ["--module", "c"])
        doc = json.loads((Path(self.plugins.entries["spec-guard@m"][-1]["installPath"]) / "interface.json").read_text())
        doc.pop("declaredScope")
        (Path(self.plugins.entries["spec-guard@m"][-1]["installPath"]) / "interface.json").write_text(json.dumps(doc))
        (self.repo / ".agent" / "config.json").touch()
        c = takeover.module(self.db(), self.repo, "c", self.repo)
        self.assertIn("读不到 spec-guard 的预先声明判定", c.forced["plan"])     # no declaredScope: human

    def test_predeclared_plan_goes_to_the_user(self):
        from module_crew import review
        self.with_takeover()
        self.set_takeover("plan", {"b": takeover_row(plan="codex")})
        plan = self.wt["b"] / "tasks" / "b" / "plan.md"
        plan.write_text(plan.read_text() + "\n## 预先声明\n\n- 公共路径：`config/app.json`\n", encoding="utf-8")
        git(self.wt["b"], "commit", "-qam", "declare")
        self.with_declared({"b": {"code": 4, "out": {"error": "unknown-line"}}}, version="1.15")
        out = review.add(self.db(), self.plan_review("b"), "shop-b", 1)
        rec = store.get(self.db(), "item", str(out.number))
        self.assertNotIn("reviewer", rec)
        why = "Plan 预先声明格式错误（spec-guard：unknown-line）"
        self.assertEqual(rec["humanReason"], why)
        self.assertIn(f"Plan 改为人批：{why}", "\n".join(out.lines))
        call = json.loads(self.args_log.read_text().splitlines()[-1])
        self.assertEqual(call[2], str(self.wt["b"]))                          # spec-guard reads the submitted worktree
        b = review.batch(self.repo)
        self.assertEqual(next(i for i in b["items"] if i["number"] == out.number)["humanReason"], why)
        self.assertIn(f"批准方式：人批（{why}）", self.cli("review", "batch")[1])

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


# ---------------------------------------------------------------- Tasks 4 and 5: Codex as the reviewer

REVIEW_MARK_115 = ["python3", "-B", "hooks/review_mark.py", "--project", "<project-root>", "--module", "<module-id>",
                   "--target", "<spec|plan|both|acceptance>", "--state", "<pending|approved|codex-approved|codex-reviewed>",
                   "[--review <report file>]"]

FAKE_MARK_115 = '''import argparse, json, os, sys
from pathlib import Path
p = argparse.ArgumentParser()
for a in ("--project", "--module", "--target", "--state"):
    p.add_argument(a, required=True)
p.add_argument("--review")
p.add_argument("--confirm", action="store_true")
a = p.parse_args()
with open(os.environ["FAKE_MARK_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(vars(a)) + "\\n")
if os.environ.get("FAKE_REVIEW_FAIL") == a.module or not a.confirm:
    sys.exit(2)
f = Path(a.project) / (("spec/%s.md" if a.target == "spec" else "tasks/%s/plan.md") % a.module)
lines = f.read_text(encoding="utf-8").splitlines(keepends=True)
mark = "<!-- spec-guard: review %s -->\\n" % a.state
if lines and lines[0].startswith("<!-- spec-guard: review"):
    lines[0] = mark
else:
    lines.insert(0, mark)
f.write_text("".join(lines), encoding="utf-8")
'''


def report(files: dict, findings=(), status="completed", outcome=None, backend="codex", recheck=None) -> dict:
    return {"schema_version": 1, "execution_status": status, "backend": backend,
            "review_outcome": outcome or ("findings" if findings else "no_findings_in_scope"),
            "scope": {"paths": list(files), "files": files}, "unreviewed": [], "findings": list(findings),
            "recheck": recheck, "limitations": []}


def finding(title, severity="blocking", **kw):
    out = {"title": title, "file": "tasks/b/plan.md", "line": 2, "trigger": "", "impact": "", "evidence": "",
           "suggestion": kw.pop("suggestion", "改掉")}
    if severity is not None:
        out["severity"] = severity
    return {**out, **kw}


class CodexReviewTest(TierMixin, TakeoverMixin, ReviewCase):
    """Task 4 (acceptance 4, 6) and Task 5 (acceptance 5, 7, 10)."""

    def setUp(self):
        import os
        from pathlib import Path
        super().setUp()
        self.with_takeover()
        root = Path(self.plugins.entries["spec-guard@m"][-1]["installPath"])
        doc = json.loads((root / "interface.json").read_text())
        doc["reviewMark"] = {"command": REVIEW_MARK_115}
        (root / "interface.json").write_text(json.dumps(doc))
        (root / "hooks" / "review_mark.py").write_text(FAKE_MARK_115)
        self.mark_log = self.tmp / "marks.jsonl"
        os.environ["FAKE_MARK_LOG"] = str(self.mark_log)
        self.addCleanup(lambda: os.environ.pop("FAKE_MARK_LOG", None))
        self.set_takeover("plan", {"b": takeover_row(plan="codex")})
        from module_crew import review
        self.db = store.open_store(self.repo)
        spec = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        res = review.approve(self.repo, [spec], "批 b 的 Spec")
        assert res.code == 0, res.lines
        self.n = review.add(self.db, self.plan_review("b"), "shop-b", 2).number

    def files(self, n=None):
        import hashlib
        rec = store.get(self.db, "item", str(n or self.n))
        out = {}
        for f in rec["files"]:
            import subprocess
            data = subprocess.run(["git", "-C", str(self.wt["b"]), "show", f"{rec['commit']}:{f['path']}"],
                                  capture_output=True, check=True).stdout
            out[f["path"]] = hashlib.sha256(data).hexdigest()
        return out

    def note(self, doc, n=None) -> tuple[int, str]:
        path = self.tmp / f"report-{len(list(self.tmp.glob('report-*')))}.json"
        path.write_text(json.dumps(doc))
        return self.cli("review", "codex-note", f"C{n or self.n}", "--report", str(path))

    def marks(self):
        return [json.loads(x) for x in self.mark_log.read_text().splitlines()] if self.mark_log.exists() else []

    def test_command(self):
        code, out = self.cli("review", "codex", f"C{self.n}")
        self.assertEqual(code, 0, out)
        self.assertIn("/delegate:review --backend codex --repo", out)
        self.assertIn("--paths tasks/b/plan.md --paths tasks/b/todo.md --spec spec/b.md", out)
        self.assertNotIn("--previous-report", out)
        self.assertIn(f"codex/C{self.n}-r1.json", out)

    def test_blocking_twice_then_the_user(self):
        from module_crew import review
        code, out = self.note(report(self.files(), [finding("缺回滚步骤"), finding("缺字段", severity=None)]))
        self.assertEqual(code, 0, out)
        self.assertIn("返工第 1 轮", out)
        rec = store.get(self.db, "item", str(self.n))
        self.assertEqual(review.review_state(self.db, self.n), "rework")
        body = [e for e in store.events(self.db, kind="item") if e["type"] == "item.rework-sent"][-1]["data"]["body"]
        text = store.read_body(self.db, body)
        self.assertIn("--state codex-reviewed --review", text)
        self.assertIn("2. 缺字段", text)                   # missing severity is blocking
        again = self.cli("review", "codex", f"C{self.n}")[1]
        self.assertNotIn("--previous-report", again)        # Task 13: a snapshot recheck carries the findings in text
        self.assertIn("逐条核对是否已解决", again)
        self.assertIn("缺回滚步骤", again)
        code, out = self.note(report(self.files(), [finding("还缺")]))   # Task 14: spec-guard's cap, two blocking rounds
        self.assertEqual(code, 5, out)
        self.assertIn("Codex 两轮都有阻断", out)
        self.assertIn("交用户决定（不降档）", out)
        self.assertIn("【等待用户】", out)
        self.assertIn("类型：卡住选做法", out)
        self.assertTrue(store.get(self.db, "item", str(self.n))["overLimit"])
        self.assertEqual(self.cli("review", "codex", f"C{self.n}")[0], 3)
        self.assertNotIn("tier-lowered", "".join(e["type"] for e in store.events(self.db)))
        self.assertEqual(rec["reviewer"], "codex")

    def resubmit(self, relay: int) -> int:
        from module_crew import review
        spec = store.get(self.db, "item", str(self.n))["node"] == "spec"
        f = self.wt["b"] / ("spec/b.md" if spec else "tasks/b/plan.md")
        f.write_text(f.read_text() + f"\n改了一轮 {relay}\n", encoding="utf-8")
        git(self.wt["b"], "commit", "-qam", f"rework {relay}")
        return review.add(self.db, (self.spec_review if spec else self.plan_review)("b"), "shop-b", relay).number

    def test_rounds_add_up_across_resubmissions(self):
        """Task 10 (M1 notes 2, 3): a resubmission keeps counting Codex rounds for the module and node."""
        first = self.files()
        self.assertEqual(self.note(report(first, [finding("缺回滚步骤")]))[0], 0)
        old = store.get(self.db, "item", str(self.n))["codexReports"][-1]
        m = self.resubmit(3)
        code, out = self.cli("review", "codex", f"C{m}")
        self.assertEqual(code, 0, out)
        what = "Spec" if store.get(self.db, "item", str(self.n))["node"] == "spec" else "Plan"
        self.assertIn(f"C{m}（b 的 {what}）第 2 次交 Codex 审", out)
        self.assertNotIn("--previous-report", out)          # Task 13 (delegate-owner #22282): interim
        self.assertIn("1. 缺回滚步骤", out)
        self.assertIn(f"codex/C{m}-r2.json", out)
        code, out = self.note(report(self.files(m)), m)
        self.assertEqual(code, 0, out)
        self.assertEqual(store.get(self.db, "item", str(m))["reviews"][-1]["ref"], "R-2")
        approval = next(v for v in store.records(self.db, "item").values() if v.get("kind") == "codex-approval")
        self.assertEqual(approval["codex"]["rounds"], 2)
        self.assertTrue(approval["codex"]["report"].endswith(f"C{m}-r2.json"))
        self.assertEqual(json.loads(self.cli("status", "--json")[1])["store"]["takeover"]["codex"]["reworked"], 1)
        self.assertIn("其中返工后才放行 1 次", self.cli("status")[1])

    def over_limit(self) -> tuple[int, str]:
        """Blocking rounds, resubmitting between them, until codex-note stops for the user: (item, output)."""
        n, relay = self.n, 10
        for _ in range(5):
            code, out = self.note(report(self.files(n), [finding(f"还缺 {relay}")]), n)
            if code == 5:
                return n, out
            self.assertEqual(code, 0, out)
            relay += 1
            n = self.resubmit(relay)
        self.fail("never over the limit")

    def test_cited_project_files_go_as_context(self):
        """Task 15 (report G): files the Plan cites that exist in the repository go to delegate as --spec context,
        with a line saying they are not reviewed themselves; a cited path that does not exist is left out."""
        spec = store.get(self.db, "item", str(self.n))["node"] == "spec"
        f = self.wt["b"] / ("spec/b.md" if spec else "tasks/b/plan.md")
        (self.wt["b"] / "scripts").mkdir(exist_ok=True)
        (self.wt["b"] / "scripts" / "check.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        f.write_text(f.read_text() + "\n由 `scripts/check.sh` 调用，结果写到 `out/none.txt`\n", encoding="utf-8")
        git(self.wt["b"], "add", "-A")
        git(self.wt["b"], "commit", "-qm", "cite")
        from module_crew import review
        m = review.add(self.db, (self.spec_review if spec else self.plan_review)("b"), "shop-b", 60).number
        out = self.cli("review", "codex", f"C{m}")[1]
        self.assertIn("--spec scripts/check.sh", out)
        self.assertNotIn("--spec out/none.txt", out)
        self.assertIn("context_files", out)
        self.assertIn("不据此阻断", out)

    def test_land_failure_cleans_up_and_says_what_next(self):
        """Task 14 (report C): a refused landing removes the files it created in the integration checkout, the item
        says what comes next, and codex-fallback records the real reason."""
        import os
        os.environ["FAKE_REVIEW_FAIL"] = "b"
        self.addCleanup(lambda: os.environ.pop("FAKE_REVIEW_FAIL", None))
        code, out = self.note(report(self.files()))
        self.assertEqual(code, 4, out)
        self.assertIn("review codex-fallback", out)
        self.assertEqual(git(self.repo, "status", "--porcelain", "--untracked-files=all").strip(), "", out)
        kept = self.db.path / "codex" / f"leftover-C{self.n}"     # moved out, never deleted
        self.assertTrue([p for p in kept.rglob("*") if p.is_file()], out)
        rec = store.get(self.db, "item", str(self.n))
        self.assertTrue(rec.get("landFailed"))
        self.assertIn("落地失败", self.cli("review", "batch")[1])
        self.assertEqual(self.cli("review", "codex-note", f"C{self.n}", "--report", rec["codexReports"][-1])[0], 3)
        os.environ.pop("FAKE_REVIEW_FAIL")
        self.assertEqual(self.cli("review", "codex-fallback", f"C{self.n}", "--original", "我来批")[0], 0)
        self.assertEqual(store.get(self.db, "item", str(self.n))["fallback"], "codex-land-failed")

    def test_unavailable_draft_names_the_cause(self):
        """Task 16 (B): diagnostics in the draft; a run that would fail the same way again is not the recommendation."""
        doc = dict(report(self.files(), status="conditions_missing"), diagnostics=["previous_report_scope_mismatch"],
                   backend_started=False)
        code, out = self.note(doc)
        self.assertEqual(code, 5, out)
        self.assertIn("previous_report_scope_mismatch", out)
        self.assertIn("推荐 B", out)
        self.assertIn("你该回：B", out)
        code, out = self.note(report(self.files(), status="failed"))
        self.assertEqual(code, 5, out)
        self.assertIn("推荐 A", out)

    def test_over_limit_counted_after_fallback_and_rework_goes_to_the_user(self):
        """Task 16 (D, E, F): the count survives the fallback; choosing B sends the resubmission to the user; the
        default reply block for the over-limit item agrees with itself."""
        from module_crew import review
        n, out = self.over_limit()
        self.assertIn("不再交 Codex", out)              # option B says where the resubmission goes
        self.assertEqual(self.cli("review", "codex-fallback", f"C{n}", "--original", "我来定")[0], 0)
        self.assertEqual(json.loads(self.cli("status", "--json")[1])["store"]["takeover"]["codex"]["overLimit"], 1)
        b = review.batch(self.repo)
        blocks = review.batch_reply_blocks(b, review.numbered_decisions(b, "c"))
        self.assertIn(f"C{n} A；C{n}-1 A", blocks)
        self.assertNotIn("改了 3 轮", "\n".join(review.question_lines(review.numbered_decisions(b, "c"))))
        code, out = self.cli("review", "answer", f"C{n}", "--original", "照阻断意见再改一轮")
        self.assertEqual(code, 0, out)
        m = self.resubmit(30)
        rec = store.get(self.db, "item", str(m))
        self.assertNotEqual(rec.get("reviewer"), "codex")
        self.assertIn("Codex 已审满两轮仍有阻断", rec.get("humanReason") or "")
        self.assertEqual(json.loads(self.cli("status", "--json")[1])["store"]["takeover"]["codex"]["overLimit"], 1)

    def test_disagree_question_carries_the_refuted_finding(self):
        """Task 16 (I): the pending question quotes the Codex finding the module refutes; the default block says a B
        overrides the A in front of it (F)."""
        from module_crew import review
        self.assertEqual(self.note(report(self.files(), [finding("缺回滚步骤")]))[0], 0)
        spec = store.get(self.db, "item", str(self.n))["node"] == "spec"
        text = (self.spec_review if spec else self.plan_review)("b").replace("要点：", "不同意：R-1：回滚不归本模块管\n要点：")
        m = review.add(self.db, text, "shop-b", 40).number
        self.assertIsNotNone(m)
        b = review.batch(self.repo)
        questions = "\n".join(review.question_lines(review.numbered_decisions(b, "c")))
        self.assertIn("缺回滚步骤", questions)
        self.assertNotIn("见审查结论", questions)
        self.assertIn("覆盖", self.cli("review", "batch")[1])

    def test_show_uses_one_numbering(self):
        """Task 16 (K): a Codex row is labelled by its cumulative R-<n> only."""
        self.assertEqual(self.note(report(self.files(), [finding("缺回滚步骤")]))[0], 0)
        m = self.resubmit(50)
        self.assertEqual(self.note(report(self.files(m), [finding("还缺")]), m)[0] in (0, 5), True)
        out = self.cli("review", "show", f"C{m}")[1]
        self.assertIn("R-2 · codex", out)
        self.assertNotIn("第 1 轮 · R-2", out)

    def test_suggestions_only_lands_as_codex_approval(self):
        code, out = self.note(report(self.files(), [finding("可以更短", severity="suggestion")]))
        self.assertEqual(code, 0, out)
        self.assertIn("Codex 放行记录", out)
        marks = self.marks()
        self.assertEqual((marks[-1]["state"], marks[-1]["target"]), ("codex-approved", "plan"))
        self.assertTrue(marks[-1]["review"].endswith(f"C{self.n}-r1.json"))
        approvals = [v for v in store.records(self.db, "item").values() if v.get("kind") == "codex-approval"]
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0]["codex"]["suggestions"], 1)
        self.assertIn("Codex 放行事项", git(self.repo, "log", "-1", "--format=%s"))
        self.assertIn("发送 【协调通知】 → shop-b", out)        # start notice: Spec by the user, Plan by Codex
        self.assertNotIn("【用户答复】", out)
        notice = [e for e in store.events(self.db, kind="item") if e["type"] == "item.created"]
        self.assertTrue(notice)
        self.assertEqual(json.loads(self.cli("status", "--json")[1])["store"]["takeover"]["codex"]["plan"], 1)

    def test_mismatch_is_refused(self):
        files = self.files()
        files["tasks/b/plan.md"] = "0" * 64
        code, _ = self.note(report(files))
        self.assertEqual(code, 3)
        self.assertEqual([m["state"] for m in self.marks()], ["approved"])      # only the Spec from setUp
        code, _ = self.note(report({"tasks/b/todo.md": self.files()["tasks/b/todo.md"]}))
        self.assertEqual(code, 3)

    def test_no_conclusion_stops_and_approve_needs_the_users_choice(self):
        from module_crew import review
        for doc in (report(self.files(), status="failed"), report(self.files(), outcome="inconclusive"),
                    report(self.files(), backend="claude-code")):
            code, out = self.note(doc)
            self.assertEqual(code, 5, out)
            self.assertIn("不会改由 Claude 自己审", out)
        bad = self.tmp / "garbage.json"
        bad.write_text("not json")
        self.assertEqual(self.cli("review", "codex-note", f"C{self.n}", "--report", str(bad))[0], 5)
        self.assertEqual(store.get(self.db, "item", str(self.n)).get("reviews"), None)
        res = review.approve(self.repo, [self.n], "批")
        self.assertNotEqual(res.code, 0)
        self.assertEqual(self.marks()[-1]["state"], "approved")       # only the earlier Spec approval
        self.assertEqual(self.cli("review", "codex-fallback", f"C{self.n}", "--original", " ")[0], 3)
        code, out = self.cli("review", "codex-fallback", f"C{self.n}", "--original", "这次我来批")
        self.assertEqual(code, 0, out)
        res = review.approve(self.repo, [self.n], "这次我来批")
        self.assertEqual(res.code, 0, res.lines)
        rec = store.get(self.db, "item", str(self.n))
        self.assertEqual((rec["reviewer"], rec["fallback"]), ("human", "codex-unavailable"))
        self.assertEqual(self.marks()[-1]["state"], "approved")


# ---------------------------------------------------------------- spec-guard 0.91.0 reviewMark template (mc-coord #22000)

import test_spec_revision as _spec_revision        # module attribute, so its own tests are not collected twice here


def use_template_115(case):
    """Install spec-guard 0.91.0's real reviewMark.command (copied from its interface.json) and a fake 1.15 script."""
    import os
    from pathlib import Path
    root = Path(case.plugins.entries["spec-guard@m"][-1]["installPath"])
    doc = json.loads((root / "interface.json").read_text())
    doc["reviewMark"] = {"command": REVIEW_MARK_115}
    (root / "interface.json").write_text(json.dumps(doc))
    (root / "hooks" / "review_mark.py").write_text(FAKE_MARK_115)
    case.mark_log = case.tmp / "marks.jsonl"
    os.environ["FAKE_MARK_LOG"] = str(case.mark_log)
    case.addCleanup(lambda: os.environ.pop("FAKE_MARK_LOG", None))


class Template115Test(ReviewCase):
    """review approve with 0.91.0's template: no placeholder left, the optional --review dropped."""

    def test_args_and_review_approve(self):
        from pathlib import Path
        from module_crew import review
        root = Path(self.plugins.entries["spec-guard@m"][-1]["installPath"])
        doc = {"reviewMark": {"command": REVIEW_MARK_115}}
        args = review.mark_args(root, doc, Path("/x"), "b", "spec")
        self.assertEqual(args[-6:], ["--module", "b", "--target", "spec", "--state", "approved"])
        self.assertFalse([a for a in args if a.startswith("<") or a.startswith("[")])
        args = review.mark_args(root, doc, Path("/x"), "b", "plan", "codex-approved", "/r.json")
        self.assertEqual(args[-4:], ["--state", "codex-approved", "--review", "/r.json"])
        use_template_115(self)
        db = store.open_store(self.repo)
        n = review.add(db, self.spec_review("b"), "shop-b", 1).number
        res = review.approve(self.repo, [n], "批 b 的 Spec")
        self.assertEqual(res.code, 0, res.lines)
        logged = [json.loads(x) for x in self.mark_log.read_text().splitlines()]
        self.assertEqual((logged[-1]["state"], logged[-1]["review"]), ("approved", None))


class SpecRevision115Test(_spec_revision.SpecRevisionTest):
    """merge run records a revised Spec's approval with 0.91.0's template (the inherited cases, template swapped)."""

    def setUp(self):
        super().setUp()
        use_template_115(self)


# ---------------------------------------------------------------- Task 6: narrowing after an incident

FAKE_CONFIG_115 = '''import json, os, sys
args = sys.argv[1:]
project = args[args.index("--project") + 1]
path = os.path.join(project, ".agent", "config.json")
cfg = json.load(open(path))
if args[0] == "show":
    value = cfg.get("takeover", "none")
    print(json.dumps({"items": [{"key": "takeover", "value": value,
                                 "source": ".agent/config.json" if "takeover" in cfg else "default"}], "problems": []}))
    sys.exit(0)
with open(os.environ["FAKE_NARROW_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\\n")
if os.environ.get("FAKE_NARROW_FAIL"):
    sys.exit(2)
def step(v):
    if isinstance(v, dict):
        for k in ("release", "merge", "plan", "spec"):
            if v.get(k, "human") != "human":
                v = dict(v, **{k: "human"})
                return v if any(x != "human" for x in v.values()) else "none"
        return "none"
    return {"merge": "plan", "plan": "none"}.get(v, "none")
if "--module" in args:
    m = args[args.index("--module") + 1]
    mods = cfg.setdefault("moduleTakeover", {})
    mods[m] = step(mods.get(m, cfg.get("takeover", "none")))
else:
    before = cfg.get("takeover", "none")
    if before == "none":
        sys.exit(0)
    cfg["takeover"] = step(before)
json.dump(cfg, open(path, "w"))
'''


class NarrowMixin(TakeoverMixin):
    def with_narrow(self, value="merge", module_entry: dict | None = None, spec: str = "codex"):
        import os
        from pathlib import Path
        self.with_takeover()
        root = Path(self.plugins.entries["spec-guard@m"][-1]["installPath"])
        (root / "hooks" / "project_config.py").write_text(FAKE_CONFIG_115)
        self.narrow_log = self.tmp / "narrow.jsonl"
        os.environ["FAKE_NARROW_LOG"] = str(self.narrow_log)
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in ("FAKE_NARROW_LOG", "FAKE_NARROW_FAIL")])
        path = self.repo / ".agent" / "config.json"
        cfg = json.loads(path.read_text())
        cfg["takeover"] = value
        if module_entry:
            cfg["moduleTakeover"] = module_entry
        path.write_text(json.dumps(cfg))
        git(self.repo, "commit", "-qam", "takeover")
        rows = {m: takeover_row(spec=spec, plan="codex", merge="auto",
                                source=f"moduleTakeover.{m}" if m in (module_entry or {}) else ".agent/config.json")
                for m in ("b", "c")}
        self.set_takeover(value, rows)

    def calls(self):
        return [json.loads(x) for x in self.narrow_log.read_text().splitlines()] if self.narrow_log.exists() else []

    def project_value(self):
        return json.loads((self.repo / ".agent" / "config.json").read_text()).get("takeover")


class NarrowTest(TierMixin, NarrowMixin, MergeCase):
    """Task 6, acceptance 9."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def test_merge_returned_narrows_once_and_commits(self):
        from module_crew import autonomy, merge
        self.with_narrow("merge")
        n = self.approve_final("b", 1)
        res = merge.run(self.repo, check_command=self.check_script(fail_if="src/b.py"))
        self.assertEqual(res.code, 5)
        text = "\n".join(res.lines)
        self.assertIn("接管档位已收窄（项目 接管到合并 → 只接管 Plan）：合并因模块的原因退回", text)
        self.assertIn("马上告诉用户", text)
        self.assertEqual(self.project_value(), "plan")
        args = self.calls()[0]
        self.assertEqual(args[args.index("--source") + 1], "module-crew")
        self.assertIn("--confirm", args)
        self.assertNotIn("--module", args)
        self.assertIn("接管档位收窄", git(self.repo, "log", "-1", "--format=%s"))
        self.assertEqual(git(self.repo, "status", "--porcelain", "--", ".agent/config.json").strip(), "")
        self.assertIsNone(autonomy.incident(self.db, self.repo, "merge-returned", str(n)))    # same item: once
        self.assertEqual(len(self.calls()), 1)

    def test_env_return_does_not_narrow(self):
        from module_crew import merge
        self.with_narrow("merge")
        self.approve_final("b", 1)
        res = merge.run(self.repo, check_command=self.check_script(sleep=3))
        self.assertNotIn("接管档位", "\n".join(res.lines))
        self.assertEqual(self.calls(), [])

    def test_revoke_and_order(self):
        from module_crew import autonomy, merge
        self.with_narrow({"spec": "codex", "plan": "codex", "merge": "auto"})
        n = self.approve_final("b", 1)
        note = merge.revoke(self.db, n, "撤回")
        self.assertIn("用户撤销合并批准", note.tier_line)
        self.assertEqual(self.project_value(), {"spec": "codex", "plan": "codex", "merge": "human"})
        autonomy.incident(self.db, self.repo, "baseline-red", "t1")
        self.assertEqual(self.project_value(), {"spec": "codex", "plan": "human", "merge": "human"})
        self.assertIsNone(autonomy.incident(self.db, self.repo, "baseline-red", "t2"))   # same red, no new commit
        autonomy.incident(self.db, self.repo, "external", "x3")             # all human: written as none
        self.assertEqual(self.project_value(), "none")
        self.assertIsNone(autonomy.incident(self.db, self.repo, "external", "x4"))       # nothing taken over

    def test_module_entry_narrowed_too(self):
        from module_crew import autonomy
        self.with_narrow("plan", {"b": "merge"})
        line = autonomy.incident(self.db, self.repo, "rework-over-limit", "77", "C77，b", module="b")
        self.assertIsNotNone(line)
        targets = [a[a.index("--module") + 1] if "--module" in a else "项目" for a in self.calls()]
        self.assertEqual(targets, ["项目", "b"])
        cfg = json.loads((self.repo / ".agent" / "config.json").read_text())
        self.assertEqual((cfg["takeover"], cfg["moduleTakeover"]["b"]), ("none", "plan"))

    def test_nothing_taken_over_never_calls(self):
        from module_crew import autonomy
        self.with_narrow("none")
        self.assertIsNone(autonomy.incident(self.db, self.repo, "revoked", "9"))
        self.assertEqual(self.calls(), [])

    def test_failure_only_costs_the_line(self):
        import os
        from module_crew import autonomy
        self.with_narrow("merge")
        os.environ["FAKE_NARROW_FAIL"] = "1"
        line = autonomy.incident(self.db, self.repo, "revoked", "9")
        self.assertIn("接管档位没能收窄", line)

    def test_degrade_cli(self):
        self.with_narrow("merge")
        code, out = self.cli("tier", "degrade", "--reason", "CI 连红", "--ref", "https://example.test/i/7")
        self.assertEqual(code, 0, out)
        self.assertIn("外部信号（CI 连红）", out)
        doc = json.loads(self.cli("tier", "--json")[1])
        self.assertEqual((doc["lastIncident"]["kind"], doc["lastIncident"]["ref"]), ("external", "https://example.test/i/7"))
        code, out = self.cli("tier", "degrade", "--reason", "again", "--ref", "https://example.test/i/7")
        self.assertEqual(code, 0)
        self.assertIn("已经收窄过", out)
        self.assertEqual(len(self.calls()), 1)
        import io
        from contextlib import redirect_stderr
        with redirect_stderr(io.StringIO()):
            self.assertEqual(self.cli("tier", "degrade", "--reason", " ", "--ref", "x")[0], 3)


class ReworkNarrowTest(TierMixin, NarrowMixin, MergeCase):
    def test_rework_over_limit_narrows(self):
        from module_crew import review, sources
        from test_review_nearby import CHANGES, conclusion
        self.with_narrow("merge", spec="human")         # the Spec goes to the human reviewer here
        db = store.open_store(self.repo)
        sources.add(db, "arch", "lead", "登记审查会话", scope=sources.ALL_SCOPE)
        rid = 5000

        def submit():
            nonlocal rid
            rid += 1
            return review.add(db, self.spec_review("b"), "shop-b", rid).number
        n = submit()
        for _ in range(3):
            review.note(db, n, "arch", conclusion("有须修改项2条", CHANGES))
            n = submit()
        res = review.note(db, n, "arch", conclusion("有须修改项2条", CHANGES))
        self.assertIn("接管档位已收窄", "\n".join(res.lines))
        self.assertIn("返工满 3 次", "\n".join(res.lines))


class BaselineNarrowTest(TierMixin, NarrowMixin, MergeCase):
    def test_new_red_baseline_narrows_old_record_does_not(self):
        import test_check_ledger as tcl
        from module_crew import hooks
        self.with_narrow("merge")
        ledger = tcl.BaselineTest.__new__(tcl.BaselineTest)
        ledger.__dict__.update(self.__dict__)
        ledger.db = store.open_store(self.repo)
        hooks.bind(ledger.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")
        ledger.red_switch()
        ledger.commit_main("fail.flag")
        out = ledger.baseline()
        self.assertEqual(out.returncode, 5, out.stdout + out.stderr)
        self.assertIn("接管档位已收窄（项目 接管到合并 → 只接管 Plan）：基线完整检查新跑出失败", out.stdout)
        out = ledger.baseline()
        self.assertNotIn("接管档位", out.stdout)


# ---------------------------------------------------------------- Task 7: the 放行 notice (contract v2.9)

class ReleaseNoticeTest(CodexReviewTest):
    """Codex releases only the Spec: a 放行 notice names it, no start notice; the module accepts it."""

    def setUp(self):
        ReviewCase.setUp(self)
        import os
        from pathlib import Path
        self.with_takeover()
        root = Path(self.plugins.entries["spec-guard@m"][-1]["installPath"])
        doc = json.loads((root / "interface.json").read_text())
        doc["reviewMark"] = {"command": REVIEW_MARK_115}
        (root / "interface.json").write_text(json.dumps(doc))
        (root / "hooks" / "review_mark.py").write_text(FAKE_MARK_115)
        self.mark_log = self.tmp / "marks.jsonl"
        os.environ["FAKE_MARK_LOG"] = str(self.mark_log)
        self.addCleanup(lambda: os.environ.pop("FAKE_MARK_LOG", None))
        self.set_takeover({"spec": "codex"}, {"b": takeover_row(spec="codex")})
        from module_crew import review
        self.db = store.open_store(self.repo)
        self.n = review.add(self.db, self.spec_review("b"), "shop-b", 1).number

    def test_spec_release_notice(self):
        from pathlib import Path
        from module_crew import protocol
        code, out = self.note(report(self.files()))
        self.assertEqual(code, 0, out)
        import re
        bodies = [Path(x).read_text(encoding="utf-8") for x in re.findall(r"正文文件：(\S+)", out)]
        notices = [protocol.parse(b) for b in bodies if b.startswith("【协调通知】")]
        kinds = [m.fields.get("类型") for m in notices]
        self.assertIn("放行", kinds)
        self.assertNotIn("开工", kinds)
        rel = next(m for m in notices if m.fields.get("类型") == "放行")
        self.assertEqual(rel.problems, ())
        self.assertEqual(rel.contract()["notice"]["node"], "spec")
        self.assertIn("写 tasks/b/plan.md、todo.md 交审", rel.fields["要你做什么"])
        self.assertEqual(self.marks()[-1]["state"], "codex-approved")

    # the inherited Plan cases do not apply to this setup
    test_command = test_blocking_twice_then_the_user = test_suggestions_only_lands_as_codex_approval = None
    test_mismatch_is_refused = test_no_conclusion_stops_and_approve_needs_the_users_choice = None


class NoticeRenderTest(ReviewCase):
    def test_render_needs_ref_and_node(self):
        from module_crew import protocol
        text = protocol.render_coordination_notice("approved-by-review", "C7（b 的 Plan 由 Codex 审过放行；交审 C3）", "等")
        self.assertEqual(protocol.parse(text).contract()["notice"]["node"], "plan")
        for basis in ("b 的 Spec 由 Codex 放行", "C7（b 由 Codex 放行）", "C7（SPEC.md）"):
            with self.assertRaises(ValueError):
                protocol.render_coordination_notice("approved-by-review", basis, "等")


class SkillTest(unittest.TestCase):
    """Acceptance 12 (replaces crew-autonomy-tier's skill test)."""

    def test_coordinator_and_dev_skills(self):
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        for d in ("skills", "codex-skills"):
            coord = (root / d / "crew-coordinator" / "SKILL.md").read_text(encoding="utf-8")
            for words in ("module-crew tier --preflight", "/spec-guard:config", "review codex C<n>", "review codex-note",
                          "review codex-fallback", "绝不自己审", "马上告诉用户", "一次升一档", "config set --digest",
                          "module-crew tier digest", "能力图永远人批"):
                self.assertIn(words, coord, (d, words))
            self.assertNotIn("自治档位已从", coord)
            dev = (root / d / "crew-dev" / "SKILL.md").read_text(encoding="utf-8")
            for words in ("不改变你的停点", "gate", "--state codex-reviewed", "「放行」类【协调通知】"):
                self.assertIn(words, dev, (d, words))
