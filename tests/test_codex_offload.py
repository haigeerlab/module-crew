"""crew-codex-offload: Codex runs a module's Tasks through delegate, the coordinator checks and commits for it
(see spec/crew-codex-offload.md)."""

import json
import os
import unittest
from pathlib import Path

from helpers import MergeCase, git

from module_crew import offload, store

DELEGATE_11 = {"interface": "1.1", "run": {
    "command": "/delegate:run", "backends": ["codex"], "write": "explicit",
    "resume": {"optIn": "--resumable", "option": "--resume", "backends": ["codex"], "statuses": ["done", "needs-input"]}}}
DELEGATE_12 = json.loads(json.dumps(DELEGATE_11))
DELEGATE_12["interface"] = "1.2"
DELEGATE_12["run"]["resume"]["statuses"].append("timeout")

SCOPE_COMMAND = ["python3", "-B", "hooks/module_scope.py", "check", "--project", "<project-root>", "--module", "<module-id>",
                 "--base", "<base-ref>", "--format", "json"]

# A fake spec-guard scopeCheck: changed files since --base, scoped by name (src/ and lib/ exclusive, the module's
# spec and tasks own, anything else outside). FAKE_SCOPE_CODE forces an exit code.
FAKE_SCOPE = '''import json, os, subprocess, sys
a = sys.argv[1:]
if os.environ.get("FAKE_SCOPE_CODE"):
    sys.exit(int(os.environ["FAKE_SCOPE_CODE"]))
root, module, base = a[a.index("--project") + 1], a[a.index("--module") + 1], a[a.index("--base") + 1]
run = lambda *x: subprocess.run(["git", "-C", root] + list(x), capture_output=True, text=True).stdout
files = []
for line in run("diff", "--no-renames", "--name-status", base, "--").splitlines():
    st, path = line.split("\\t", 1)
    files.append((st, path))
files += [("?", p) for p in run("ls-files", "--others", "--exclude-standard").splitlines() if p]
out = []
for st, p in files:
    if p.startswith(("src/", "lib/")):
        scope = "exclusive"
    elif p == "spec/%s.md" % module or p.startswith("tasks/%s/" % module):
        scope = "own"
    else:
        scope = "outside"
    out.append({"path": p, "status": st, "scope": scope})
print(json.dumps({"module": module, "base": base, "files": out, "outside": sum(f["scope"] == "outside" for f in out)}))
'''


class OffloadCase(MergeCase):
    """Module b with an approved-looking Spec and Plan, quick check and ledger on, delegate 1.1, scopeCheck."""

    def setUp(self) -> None:
        super().setUp()
        self.delegate = self.plugins.install("delegate", DELEGATE_11)
        root = Path(self.plugins.entries["spec-guard@m"][-1]["installPath"])
        doc = json.loads((root / "interface.json").read_text())
        doc["interface"] = "1.11"
        doc["scopeCheck"] = {"command": SCOPE_COMMAND}
        (root / "interface.json").write_text(json.dumps(doc))
        (root / "hooks" / "module_scope.py").write_text(FAKE_SCOPE)
        self.addCleanup(lambda: os.environ.pop("FAKE_SCOPE_CODE", None))
        self.codex_home = self.tmp / "codex-home"
        self.codex_home.mkdir()
        old = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = str(self.codex_home)
        self.addCleanup(lambda: os.environ.__setitem__("CODEX_HOME", old) if old else os.environ.pop("CODEX_HOME", None))
        self.quick = self.tmp / "quick.py"
        self.quick_calls = self.tmp / "quick-calls"
        self.quick.write_text(
            "import os, sys\n"
            f"open({str(self.quick_calls)!r}, 'a').write('x')\n"
            "sys.exit(1 if os.path.exists('BROKEN') else 0)\n", encoding="utf-8")
        self.db = store.open_store(self.repo)
        with self.db.transaction(actor="test") as tx:
            cfg = dict(tx.get("config", "main") or {})
            cfg.update({"checkCommand": self.check_script(), "quickCheckCommand": f"python3 {self.quick}",
                        "checkLedger": "on"})
            tx.put("config", "main", cfg, action="set")

    def set_cfg(self, **kv):
        with self.db.transaction(actor="test") as tx:
            cfg = dict(tx.get("config", "main") or {})
            for k, v in kv.items():
                if v is None:
                    cfg.pop(k, None)
                else:
                    cfg[k] = v
            tx.put("config", "main", cfg, action="set")

    def switch_on(self):
        self.set_cfg(codexOffload="on")

    def quick_count(self) -> int:
        return len(self.quick_calls.read_text()) if self.quick_calls.exists() else 0


class SwitchTest(OffloadCase):
    """Acceptance 1."""

    def test_on_with_words(self):
        out = self.run_cli("config", "set", "--codex-offload", "on", "--original", "打开额度外包")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("已打开额度外包", out.stdout)
        db = store.open_store(self.repo)
        self.assertEqual(store.get(db, "config", "main")["codexOffload"], "on")
        events = [json.loads(line) for line in (db.path / "events.jsonl").read_text().splitlines()]
        self.assertTrue(any((e.get("data") or {}).get("original") == "打开额度外包" and "codexOffload" in (e.get("data") or {})
                            for e in events))

    def test_refused_without_ledger(self):
        self.set_cfg(checkLedger=None)
        out = self.run_cli("config", "set", "--codex-offload", "on", "--original", "打开额度外包")
        self.assertEqual(out.returncode, 3)
        self.assertIn("checkLedger", out.stderr)
        self.assertNotIn("codexOffload", store.get(store.open_store(self.repo), "config", "main"))

    def test_empty_words_refused(self):
        out = self.run_cli("config", "set", "--codex-offload", "on", "--original", " ")
        self.assertEqual(out.returncode, 3)

    def test_warns_when_not_ready(self):
        (self.delegate / "interface.json").write_text(json.dumps({"interface": "1.0", "run": {"command": "/delegate:run"}}))
        out = self.run_cli("config", "set", "--codex-offload", "on", "--original", "打开额度外包")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("⚠️", out.stdout)
        self.assertIn("delegate", out.stdout)

    def test_off(self):
        self.switch_on()
        out = self.run_cli("config", "set", "--codex-offload", "off", "--original", "关掉额度外包")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertFalse(offload.enabled(store.open_store(self.repo)))


class ReadyTest(OffloadCase):
    """Acceptance 3: each of the six conditions."""

    def setUp(self) -> None:
        super().setUp()
        self.switch_on()

    def test_all_met(self):
        self.assertIsNone(offload.ready(self.db, self.repo))

    def test_switch_off(self):
        self.set_cfg(codexOffload=None)
        self.assertIn("codexOffload", offload.ready(self.db, self.repo))

    def test_ledger_off(self):
        self.set_cfg(checkLedger="off")
        self.assertIn("checkLedger", offload.ready(self.db, self.repo))

    def test_delegate_10(self):
        (self.delegate / "interface.json").write_text(json.dumps({"interface": "1.0", "run": {"command": "/delegate:run"}}))
        self.assertIn("1.1", offload.ready(self.db, self.repo))

    def test_delegate_without_resume(self):
        doc = json.loads(json.dumps(DELEGATE_11))
        del doc["run"]["resume"]
        (self.delegate / "interface.json").write_text(json.dumps(doc))
        self.assertIn("run.resume", offload.ready(self.db, self.repo))

    def test_delegate_missing(self):
        del self.plugins.entries["delegate@m"]
        self.plugins.write()
        self.assertIn("delegate", offload.ready(self.db, self.repo))

    def test_no_scope_check(self):
        root = Path(self.plugins.entries["spec-guard@m"][-1]["installPath"])
        doc = json.loads((root / "interface.json").read_text())
        del doc["scopeCheck"]
        (root / "interface.json").write_text(json.dumps(doc))
        self.assertIn("scopeCheck", offload.ready(self.db, self.repo))

    def test_concurrency_off(self):
        from helpers import START_MAP
        self.set_map({**START_MAP, "moduleConcurrency": "off"})
        self.assertIn("moduleConcurrency", offload.ready(self.db, self.repo))

    def test_coordinator_on_codex(self):
        with self.db.transaction(actor="test") as tx:
            for name, rec in store.records(self.db, "session").items():
                if rec.get("role") == "coordinator":
                    tx.put("session", name, {**rec, "host": "codex-desktop", "hostHandover": {
                        "from": "claude-desktop", "to": "codex-desktop", "at": "2026-10-26T00:00:00+08:00",
                        "original": "换到 Codex", "pending": False}}, action="set")
        self.assertIn("Codex", offload.ready(self.db, self.repo))

    def test_untrusted(self):
        (self.codex_home / "config.toml").write_text(f'[projects."{self.repo}"]\ntrust_level = "untrusted"\n')
        self.assertIn("untrusted", offload.ready(self.db, self.repo))

    def test_not_set_trust_is_fine(self):
        (self.codex_home / "config.toml").write_text("")
        self.assertIsNone(offload.ready(self.db, self.repo))

    def test_resume_timeout_flag(self):
        self.assertFalse(offload.delegate_interface(self.repo).resume_timeout)
        (self.delegate / "interface.json").write_text(json.dumps(DELEGATE_12))
        self.assertTrue(offload.delegate_interface(self.repo).resume_timeout)


if __name__ == "__main__":
    unittest.main()
