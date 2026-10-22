"""crew-command-entry: bin/module-crew runs its own plugin's code; Codex sessions use a fixed launcher."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import PLUGIN_ROOT, FakePlugins, RepoCase, StartCase

from module_crew import coordinator, hooks, launcher, permissions, probe, start, store

BIN = PLUGIN_ROOT / "bin" / "module-crew"


class WrapperTest(unittest.TestCase):
    """Acceptance 6: the plugin's own code wins over a module_crew package in the current directory."""

    def test_cwd_package_does_not_shadow(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "module_crew"
            fake.mkdir()
            (fake / "__init__.py").write_text("")
            (fake / "__main__.py").write_text("print('WRONG CODE')\n")
            run = subprocess.run([str(BIN), "--help"], cwd=tmp, capture_output=True, text=True, timeout=60)
        self.assertNotIn("WRONG CODE", run.stdout + run.stderr)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("usage: module-crew", run.stdout)


STUB = "#!/bin/sh\necho \"ran $0 $*\"\nexit 7\n"


class LauncherCase(RepoCase):
    def setUp(self):
        super().setUp()
        self.plugins = FakePlugins(self.tmp / "claude")
        self.script = self.tmp / "store-bin" / "module-crew"
        self.script.parent.mkdir()
        self.script.write_bytes(Path(launcher.__file__).read_bytes())
        self.script.chmod(0o755)

    def plugin(self, scope="user", project=None, stub=True):
        path = self.plugins.install("module-crew", None, scope=scope, project=project)
        if stub:
            (path / "bin").mkdir()
            (path / "bin" / "module-crew").write_text(STUB)
            (path / "bin" / "module-crew").chmod(0o755)
        return path

    def run_launcher(self, *args, records=None):
        env = dict(os.environ, MODULE_CREW_PLUGINS_FILE=str(records or self.plugins.records))
        return subprocess.run([sys.executable, str(self.script), *args], cwd=self.repo, env=env,
                              capture_output=True, text=True, timeout=60)


class ForwardTest(LauncherCase):
    """Acceptance 2."""

    def test_forwards_args_and_exit_code(self):
        path = self.plugin()
        r = self.run_launcher("status", "--json")
        self.assertEqual(r.returncode, 7, r.stderr)
        self.assertEqual(r.stdout.strip(), f"ran {path / 'bin' / 'module-crew'} status --json")

    def test_project_scope_wins(self):
        self.plugin()
        mine = self.plugin(scope="project", project=self.repo)
        self.assertIn(str(mine), self.run_launcher("x").stdout)

    def test_follows_reinstall(self):
        self.plugin()
        self.run_launcher("x")
        newer = self.plugin(scope="project", project=self.repo)
        self.assertIn(str(newer), self.run_launcher("x").stdout)

    def test_directory_marketplace_source(self):
        cached = self.plugin()
        src = self.tmp / "src-repo"
        live = src / "plugins" / "crew"
        (live / ".claude-plugin").mkdir(parents=True)
        (live / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "module-crew", "version": "1.0.0"}))
        (live / "bin").mkdir()
        (live / "bin" / "module-crew").write_text(STUB)
        (live / "bin" / "module-crew").chmod(0o755)
        (src / ".claude-plugin").mkdir()
        (src / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps({"plugins": [{"name": "module-crew", "source": "./plugins/crew"}]}))
        (self.plugins.records.parent / "known_marketplaces.json").write_text(
            json.dumps({"m": {"source": {"source": "directory", "path": str(src)}}}))
        out = self.run_launcher("x").stdout
        self.assertIn(str(live.resolve()), out)
        self.assertNotIn(str(cached), out)


class NotFoundTest(LauncherCase):
    """Acceptance 3."""

    def test_reasons(self):
        bad = self.tmp / "bad.json"
        bad.write_text("not json")
        cases = {"记录缺失": self.tmp / "none.json", "读不出": bad, "没装": self.plugins.records}
        for name, records in cases.items():
            with self.subTest(name):
                r = self.run_launcher("status", records=records)
                self.assertEqual(r.returncode, 2)
                self.assertIn("module-crew", r.stderr)
                self.assertEqual(r.stdout, "")
        self.plugin(stub=False)
        r = self.run_launcher("status")
        self.assertEqual(r.returncode, 2)
        self.assertIn("bin/module-crew", r.stderr)


class AgreeTest(LauncherCase):
    """Acceptance 4: the launcher and probe.find_plugin choose the same plugin directory."""

    def test_same_choice(self):
        old = os.environ.get("MODULE_CREW_PLUGINS_FILE")
        os.environ["MODULE_CREW_PLUGINS_FILE"] = str(self.plugins.records)
        self.addCleanup(lambda: os.environ.__setitem__("MODULE_CREW_PLUGINS_FILE", old) if old
                        else os.environ.pop("MODULE_CREW_PLUGINS_FILE", None))
        self.plugin()
        steps = [lambda: None, lambda: self.plugin(scope="project", project=self.tmp / "other"),
                 lambda: self.plugin(scope="project", project=self.repo)]
        for i, step in enumerate(steps):
            step()
            with self.subTest(step=i):
                self.assertEqual(launcher.locate(self.repo), probe.find_plugin("module-crew", self.repo).root)


class InstallTest(StartCase):
    """Acceptance 1."""

    def target(self):
        return launcher.entry(store.open_store(self.repo).path)

    def test_prepare_writes_once(self):
        res = start.prepare(self.repo, ["b"], "开 b", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        path = self.target()
        self.assertEqual(path.read_bytes(), Path(launcher.__file__).read_bytes())
        self.assertTrue(os.access(path, os.X_OK))
        self.assertIn(f"Codex 会话的固定入口：{path}（已写入）", res.lines)
        before = path.stat().st_mtime_ns
        self.assertEqual(launcher.install(path.parent.parent), (path, False))
        self.assertEqual(path.stat().st_mtime_ns, before)
        path.write_text("# old template\n")
        self.assertEqual(launcher.install(path.parent.parent), (path, True))
        self.assertEqual(path.read_bytes(), Path(launcher.__file__).read_bytes())

    def test_coordinator_up_writes(self):
        code, lines = coordinator.up(self.repo, "shop", "升级为模块协调", session_id="sid-1")
        self.assertEqual(code, 0, lines)
        self.assertIn(f"Codex 会话的固定入口：{self.target()}（已写入）", lines)
        code, lines = coordinator.up(self.repo, None, "再升级", session_id="sid-1")
        self.assertEqual(code, 0, lines)
        self.assertIn(f"Codex 会话的固定入口：{self.target()}（没有变化）", lines)


class CodexSideTest(StartCase):
    """Acceptance 5: Codex kickoff, Codex rules and the Codex skill name the fixed entry; the Claude side is unchanged."""

    def test_codex_side_uses_fixed_entry(self):
        res = start.prepare(self.repo, ["b"], "开 b", short="shop", host="codex")
        self.assertEqual(res.code, 0, res.lines)
        db = store.open_store(self.repo)
        fixed = str(launcher.entry(db.path))
        kick = store.read_body(db, res.prepared[0]["kickoff"])
        self.assertEqual(kick.count(fixed), 3, kick)
        self.assertNotIn(str(PLUGIN_ROOT), kick)
        rules = permissions.render_codex(permissions.codex_rules({}, launcher.entry(db.path)))
        self.assertIn(fixed, rules)
        self.assertNotIn(str(PLUGIN_ROOT), rules)
        skill = (PLUGIN_ROOT / "codex-skills" / "crew-dev" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("<插件目录>/bin/module-crew", skill)
        self.assertIn("固定入口", skill)

    def test_claude_side_unchanged(self):
        res = start.prepare(self.repo, ["b"], "开 b", short="shop")
        db = store.open_store(self.repo)
        kick = store.read_body(db, res.prepared[0]["kickoff"])
        self.assertIn(hooks.ENTRY_LINE, kick)
        self.assertNotIn(str(launcher.entry(db.path)), kick)
        allow = permissions.claude_entries({})["allow"]
        self.assertIn(f"Bash({permissions.CREW_BIN} *)", allow)


if __name__ == "__main__":
    unittest.main()
