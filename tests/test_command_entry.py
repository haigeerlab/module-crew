"""0.11.1 (O8): the hook names the command entry of the loaded plugin; status reports a running/installed mismatch."""

import json
import unittest
from pathlib import Path
from unittest import mock

from helpers import MergeCase, make_worktree

from module_crew import hooks, permissions, probe, start, store, tasks

ROOT = Path(__file__).resolve().parents[1]


def plugin_dir(base: Path, version: str | None) -> Path:
    (base / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    if version is not None:
        (base / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "module-crew", "version": version}))
    return base


class HookEntryTest(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        self.version = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
        self.line = f"module-crew 命令入口：`{ROOT / 'bin' / 'module-crew'}`（版本 {self.version}）"

    def test_every_role_every_source(self):
        n = tasks.add(self.db, self.repo, "feature", "改文档", "补一段说明", ["docs/t.md"], "说明写好", "加一段说明").number
        wt = make_worktree(self.repo, f"task-t{n}")
        with self.db.transaction(actor="t") as tx:
            tx.put("session", f"shop-t{n}", {"role": "task", "host": "claude-desktop", "status": "active", "task": n,
                                             "worktree": str(wt)}, action="registered")
        for cwd in (self.repo, self.wt["b"], wt):
            for source in ("startup", "compact", "clear"):
                with self.subTest(cwd=cwd.name, source=source):
                    self.assertIn(self.line, hooks.session_start(cwd, source))
            self.assertNotIn("命令入口", hooks.prompt_line(cwd) or "")

    def test_version_unknown(self):
        fake = plugin_dir(self.tmp / "plugin", None)
        with mock.patch.object(hooks, "PLUGIN_ROOT", fake):
            text = hooks.session_start(self.wt["b"], "startup")
        self.assertIn(f"module-crew 命令入口：`{fake / 'bin' / 'module-crew'}`（版本未知）", text)
        self.assertIn("模块 b", text)

    def test_skills_and_kickoffs_name_no_path(self):
        for rel in ("skills/crew-coordinator/SKILL.md", "skills/crew-dev/SKILL.md"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("插件目录下的 `bin/module-crew`", text)
            self.assertIn("不要把带版本号的绝对路径记进记忆", text)
        cfg = store.get(self.db, "config", "main")
        kick = start.render_kickoff("b", {"responsibility": "r"}, self.wt["b"], cfg, "shop-b", "shop-coord", 1)
        self.assertIn(hooks.ENTRY_LINE, kick)
        self.assertNotIn(str(ROOT), kick)
        codex = start.render_kickoff("b", {"responsibility": "r"}, self.wt["b"], cfg, "shop-b", "shop-coord", 1,
                                     host="codex-desktop")
        self.assertNotIn(hooks.ENTRY_LINE, codex)          # Codex has no hooks: the kickoff keeps the path
        n = tasks.add(self.db, self.repo, "feature", "改文档", "补", ["docs/t.md"], "好", "加").number
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")
        d = tasks.dispatch(self.db, self.repo, n)
        self.assertIn(hooks.ENTRY_LINE, store.read_body(self.db, d.kickoff))


class StatusVersionTest(MergeCase):
    def install_crew(self, version):
        path = self.plugins.install("module-crew", None)
        plugin_dir(path, version)
        self.plugins.entries["module-crew@m"][-1]["version"] = version
        self.plugins.write()
        return path

    def check(self, running="0.11.1"):
        with mock.patch.object(probe, "RUNNING_ROOT", plugin_dir(self.tmp / "running", running)):
            return probe.run(self.repo).checks["module-crew"]

    def test_mismatch_blocks(self):
        path = self.install_crew("0.11.0")
        c = self.check("0.11.1")
        self.assertEqual(c.state, "blocker")
        for words in ("0.11.1", "0.11.0", str(self.tmp / "running"), str(path)):
            self.assertIn(words, c.reason)
        self.assertIn(str(path / "bin" / "module-crew"), c.fix)

    def test_same_version_other_path_ok(self):
        self.install_crew("0.11.1")
        self.assertEqual(self.check("0.11.1").state, "ok")

    def test_not_installed_warning(self):
        self.assertEqual(self.check().state, "warning")

    def test_stale_permission_rules(self):
        settings = self.wt["b"] / ".claude" / "settings.local.json"
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({"permissions": {"allow": ["Bash(/old/v0.10.0/bin/module-crew *)"]}}))
        db = store.open_store(self.repo)
        with db.transaction(actor="coordinator") as tx:
            cfg = tx.get("config", "main")
            tx.put("config", "main", dict(cfg, permissions={"applied": True, "files": {str(settings): {}}}),
                   action="updated")
        before = sorted((p, p.stat().st_mtime_ns) for p in db.path.rglob("*") if p.is_file())
        self.assertEqual(probe.run(self.repo).store["permissionsStale"], [str(settings)])
        self.assertEqual(sorted((p, p.stat().st_mtime_ns) for p in db.path.rglob("*") if p.is_file()), before)
        settings.write_text(json.dumps({"permissions": {"allow": [f"Bash({permissions.CREW_BIN} *)"]}}))
        self.assertEqual(probe.run(self.repo).store["permissionsStale"], [])


if __name__ == "__main__":
    unittest.main()
