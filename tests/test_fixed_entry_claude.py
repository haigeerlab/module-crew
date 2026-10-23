"""crew-command-entry decision 6 (0.12.1): Claude rules and the hook's command entry use the store's fixed launcher."""

import json
import os
import unittest
from pathlib import Path

from test_permissions import PermCase

from module_crew import hooks, launcher, permissions, probe, store

ROOT = Path(__file__).resolve().parents[1]


class ClaudeRulesTest(PermCase):
    """Acceptance 8."""

    def test_apply_allows_fixed_entry_not_plugin_path(self):
        entry = str(launcher.entry(self.db.path))
        lines = permissions.apply(self.repo, "按清单预配权限")
        self.assertIn(f"固定入口：{entry}", "\n".join(lines))
        allow = self.settings(self.wt["b"])["permissions"]["allow"]
        self.assertIn(f"Bash({entry} *)", allow)
        self.assertFalse([e for e in allow if str(ROOT) in e], allow)

    def test_apply_writes_missing_launcher(self):
        target = launcher.entry(self.db.path)
        os.replace(target, target.with_name("moved-away"))          # a store from before 0.12.0
        lines = permissions.apply(self.repo, "按清单预配权限")
        self.assertTrue(os.access(target, os.X_OK))
        self.assertIn(f"固定入口：{target}（已写入）", "\n".join(lines))

    def test_verify_list_names_fixed_entry(self):
        text = "\n".join(permissions.verify_list(self.repo))
        self.assertIn(f"{launcher.entry(self.db.path)} status", text)
        self.assertNotIn(str(ROOT / "bin"), text)

    def test_status_stale_only_without_fixed_entry(self):
        permissions.apply(self.repo, "按清单预配权限")
        self.assertEqual(probe.run(self.repo).store["permissionsStale"], [])
        settings = self.wt["b"] / ".claude" / "settings.local.json"
        doc = json.loads(settings.read_text(encoding="utf-8"))
        doc["permissions"]["allow"] = [f"Bash({permissions.CREW_BIN} *)"]      # only the versioned plugin path
        settings.write_text(json.dumps(doc), encoding="utf-8")
        self.assertIn(str(settings), probe.run(self.repo).store["permissionsStale"])


class HookEntryTest(PermCase):
    """Acceptance 9."""

    def test_hook_names_fixed_entry(self):
        version = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
        text = hooks.session_start(self.wt["b"], "startup")
        self.assertIn(f"module-crew 命令入口：`{launcher.entry(self.db.path)}`（固定入口，转到本机当前安装的 module-crew；"
                      f"本次钩子来自版本 {version}）", text)
        self.assertNotIn(str(ROOT / "bin"), text)

    def test_hook_falls_back_without_launcher(self):
        target = launcher.entry(self.db.path)
        os.replace(target, target.with_name("moved-away"))
        text = hooks.session_start(self.repo, "startup")
        self.assertIn(f"module-crew 命令入口：`{ROOT / 'bin' / 'module-crew'}`", text)
        self.assertIn("permissions apply", text)
        self.assertFalse(target.exists())                                # the hook only reads

    def test_hooks_still_no_subprocess(self):
        source = (ROOT / "module_crew" / "hooks.py").read_text(encoding="utf-8")
        self.assertNotIn("import subprocess", source)
        self.assertNotIn("launcher", [l.split()[-1] for l in source.splitlines() if l.startswith(("import", "from"))])


if __name__ == "__main__":
    unittest.main()
