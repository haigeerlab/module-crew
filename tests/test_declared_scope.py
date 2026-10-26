"""crew-declared-scope: declared public files edited in the module branch, early landing, the final-review section,
modules with a dependency not opened together (see spec/crew-declared-scope.md)."""

import json
import os
import unittest
from pathlib import Path

from helpers import MergeCase, ReviewCase, StartCase, git

from module_crew import declared, store

FAKE_DECLARED = '''import json, os, sys
args = sys.argv[1:]
log = os.environ.get("FAKE_DECLARED_ARGS")
if log:
    with open(log, "a") as f:
        f.write(json.dumps(args) + "\\n")
module = args[args.index("--module") + 1]
spec = json.load(open(os.environ["FAKE_DECLARED_OUT"]))
mine = spec.get(module, spec.get("*", {"code": 0, "out": {"declared": False}}))
out = dict(mine.get("out") or {})
out.setdefault("module", module)
print(json.dumps(out, ensure_ascii=False))
sys.exit(mine.get("code", 0))
'''

DECLARED_COMMAND = ["python3", "-B", "hooks/module_scope.py", "declared", "--project", "<project-root>",
                    "--module", "<module-id>"]


def usable(paths=("config/app.json", "shared/"), configs=(), patches=(), deps=(), commit="abc123"):
    return {"code": 0, "out": {"planApproved": True, "approvedCommit": commit, "declared": True,
                               "publicPaths": list(paths), "configs": list(configs), "patches": list(patches),
                               "dependencies": [{"name": n, "range": r} for n, r in deps]}}


class DeclaredMixin:
    """A fake spec-guard 1.11 whose declaredScope answers from FAKE_DECLARED_OUT, per module."""

    def with_declared(self, answers: dict, version: str = "1.11"):
        root = Path(self.plugins.entries["spec-guard@m"][-1]["installPath"])
        doc = json.loads((root / "interface.json").read_text())
        doc["interface"] = version
        if version >= "1.11":
            doc["declaredScope"] = {"command": DECLARED_COMMAND}
        else:
            doc.pop("declaredScope", None)
        (root / "interface.json").write_text(json.dumps(doc))
        (root / "hooks" / "module_scope.py").write_text(FAKE_DECLARED)
        out = self.tmp / "declared-out.json"
        out.write_text(json.dumps(answers))
        self.args_log = self.tmp / "declared-args.jsonl"
        os.environ["FAKE_DECLARED_OUT"], os.environ["FAKE_DECLARED_ARGS"] = str(out), str(self.args_log)
        self.addCleanup(lambda: [os.environ.pop(k, None) for k in ("FAKE_DECLARED_OUT", "FAKE_DECLARED_ARGS")])

    def switch(self, value: str | None):
        db = store.open_store(self.repo)
        with db.transaction(actor="test") as tx:
            cfg = dict(tx.get("config", "main") or {})
            if value is None:
                cfg.pop("declaredScope", None)
            else:
                cfg["declaredScope"] = value
            tx.put("config", "main", cfg, action="set")
        return db


class ReadTest(DeclaredMixin, ReviewCase):
    """Acceptance 3 at the read layer; Spec assumption 1 and 2."""

    def test_usable_and_inside(self):
        self.with_declared({"b": usable(configs=["tsconfig.base.json"], patches=["patches/x.patch"],
                                        deps=[("zod", "^3")])})
        d = declared.read(self.repo, "b")
        self.assertTrue(d.usable, d.reason)
        self.assertIsNone(d.reason)
        self.assertEqual(d.approved_commit, "abc123")
        self.assertEqual(d.dependencies, [{"name": "zod", "range": "^3"}])
        for path in ("config/app.json", "shared/a/b.ts", "tsconfig.base.json", "patches/x.patch"):
            self.assertTrue(d.inside(path), path)
        for path in ("package.json", "config/app.json.bak", "sharedx/a.ts", "config/other.json"):
            self.assertFalse(d.inside(path), path)
        call = json.loads(self.args_log.read_text().splitlines()[-1])
        self.assertEqual(call[:2], ["declared", "--project"])
        self.assertEqual(call[-2:], ["--module", "b"])

    def unusable(self, answers, version="1.11"):
        self.with_declared(answers, version)
        d = declared.read(self.repo, "b")
        self.assertFalse(d.usable)
        self.assertFalse(d.inside("config/app.json"))
        return d.reason

    def test_plan_not_approved(self):
        answer = usable()
        answer["out"].update(planApproved=False, approvedCommit=None)
        self.assertIn("Plan 批准后改过或未批准", self.unusable({"b": answer}))

    def test_no_section(self):
        self.assertIn("没有预先声明一节", self.unusable({"b": {"code": 0, "out": {"planApproved": True, "declared": False}}}))

    def test_malformed(self):
        self.assertIn("bad-path", self.unusable({"b": {"code": 4, "out": {"error": "bad-path"}}}))

    def test_old_spec_guard(self):
        self.assertIn("低于 1.11", self.unusable({"b": usable()}, version="1.10"))

    def test_command_fails(self):
        self.assertIn("没跑成", self.unusable({"b": {"code": 2, "out": {}}}))

    def test_switch(self):
        db = store.open_store(self.repo)
        self.assertFalse(declared.enabled(db))
        self.switch("on")
        self.assertTrue(declared.enabled(db))
        self.switch("off")
        self.assertFalse(declared.enabled(db))


class ConfigSetTest(DeclaredMixin, ReviewCase):
    """Acceptance 1."""

    def test_on_with_original(self):
        self.with_declared({})
        out = self.run_cli("config", "set", "--declared-scope", "on", "--original", "打开声明范围")
        self.assertEqual(out.returncode, 0, out.stderr)
        db = store.open_store(self.repo)
        self.assertEqual(store.get(db, "config", "main")["declaredScope"], "on")
        ev = [e for e in store.events(db) if e["data"].get("declaredScope") == "on"]
        self.assertEqual(ev[-1]["data"]["original"], "打开声明范围")
        self.assertNotIn("低于 1.11", out.stdout)

    def test_empty_original(self):
        out = self.run_cli("config", "set", "--declared-scope", "on", "--original", " ")
        self.assertEqual(out.returncode, 3)
        self.assertNotIn("declaredScope", store.get(store.open_store(self.repo), "config", "main"))

    def test_old_spec_guard_warns_but_writes(self):
        self.with_declared({}, version="1.10")
        out = self.run_cli("config", "set", "--declared-scope", "on", "--original", "打开")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("低于 1.11", out.stdout)
        self.assertEqual(store.get(store.open_store(self.repo), "config", "main")["declaredScope"], "on")

    def test_off(self):
        self.switch("on")
        out = self.run_cli("config", "set", "--declared-scope", "off", "--original", "关掉")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(store.get(store.open_store(self.repo), "config", "main")["declaredScope"], "off")


if __name__ == "__main__":
    unittest.main()
