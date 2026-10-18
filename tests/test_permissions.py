"""crew-host-permissions: permission rules the host honours, written only with the user's words (spec/crew-host-permissions.md)."""

import json
import os
import unittest
from pathlib import Path

from helpers import StartCase, git

from module_crew import permissions, start, store

IGNORE = ".claude/settings.local.json\n.codex/\n"


class PermCase(StartCase):
    """Integration checkout plus module b (Claude) and c (Codex); local settings files are git-ignored."""

    def setUp(self):
        super().setUp()
        (self.repo / ".gitignore").write_text(IGNORE, encoding="utf-8")
        git(self.repo, "add", ".gitignore")
        git(self.repo, "commit", "-q", "-m", "ignore local settings")
        assert start.prepare(self.repo, ["b"], "开 b", short="shop").code == 0
        assert start.prepare(self.repo, ["c"], "开 c", host="codex").code == 0
        self.db = store.open_store(self.repo)
        sessions = store.records(self.db, "session")
        self.wt = {rec["module"]: Path(rec["worktree"]) for rec in sessions.values() if rec.get("role") == "dev"}
        self.codex_home = self.tmp / "codex-home"
        self.codex_home.mkdir()
        old = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = str(self.codex_home)
        self.addCleanup(lambda: os.environ.__setitem__("CODEX_HOME", old) if old else os.environ.pop("CODEX_HOME", None))

    def settings(self, checkout: Path) -> dict:
        return json.loads((checkout / ".claude" / "settings.local.json").read_text(encoding="utf-8"))


class PlanTest(PermCase):
    def test_plan_lists_every_checkout_and_writes_nothing(self):
        p = permissions.plan(self.repo)
        by = {t["role"] + ":" + (t["module"] or ""): t for t in p["targets"]}
        self.assertEqual(set(by), {"integration:", "dev:b", "dev:c"})
        claude = by["dev:b"]
        self.assertEqual(claude["host"], "claude-desktop")
        self.assertEqual(claude["file"], str(self.wt["b"] / ".claude" / "settings.local.json"))
        self.assertTrue(claude["ignored"])
        self.assertIn("Bash(git push *)", claude["deny"])
        self.assertIn("Bash(git commit *)", claude["allow"])
        self.assertIn(f"Bash({permissions.CREW_BIN} *)", claude["allow"])
        self.assertNotIn("ask", claude)
        codex = by["dev:c"]
        self.assertEqual(codex["file"], str(self.wt["c"] / ".codex" / "rules" / "module-crew.rules"))
        self.assertEqual(codex["trust"], "not-set")
        self.assertTrue(p["hook"]["installable"])
        for t in p["targets"]:
            self.assertFalse(Path(t["file"]).exists())

    def test_plan_reports_files_not_ignored(self):
        (self.repo / ".gitignore").write_text("", encoding="utf-8")
        git(self.repo, "config", "core.excludesFile", "/dev/null")      # this machine's global ignore lists the file too
        by = {t["role"]: t for t in permissions.plan(self.repo)["targets"]}
        self.assertFalse(by["integration"]["ignored"])

    def test_check_command_is_allowed_exactly(self):
        with self.db.transaction(actor="test") as tx:
            tx.put("config", "main", dict(tx.get("config", "main"), checkCommand="pnpm test"), action="set")
        target = next(t for t in permissions.plan(self.repo)["targets"] if t["role"] == "integration")
        self.assertIn("Bash(pnpm test)", target["allow"])
        self.assertIn("Bash(pnpm test *)", target["allow"])

    def test_codex_trust_is_read_from_codex_home(self):
        (self.codex_home / "config.toml").write_text(f'[projects."{self.wt["c"]}"]\ntrust_level = "trusted"\n', encoding="utf-8")
        codex = next(t for t in permissions.plan(self.repo)["targets"] if t["module"] == "c")
        self.assertEqual(codex["trust"], "trusted")

    def test_hook_not_installable_with_hooks_path(self):
        git(self.repo, "config", "core.hooksPath", ".husky")
        hook = permissions.plan(self.repo)["hook"]
        self.assertFalse(hook["installable"])
        self.assertIn("core.hooksPath", hook["reason"])

    def test_cli_plan(self):
        out = self.run_cli("permissions", "plan")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Bash(git push *)", out.stdout)
        self.assertIn("项目没有被 Codex 信任", out.stdout)
        doc = json.loads(self.run_cli("permissions", "plan", "--json").stdout)
        self.assertEqual(len(doc["targets"]), 3)


class ApplyClaudeTest(PermCase):
    def test_apply_merges_and_records(self):
        mine = self.repo / ".claude" / "settings.local.json"
        mine.parent.mkdir()
        mine.write_text(json.dumps({"permissions": {"allow": ["Bash(ls *)", "Bash(git add *)"]}, "model": "x"}), encoding="utf-8")
        permissions.apply(self.repo, "按清单预配权限")
        doc = self.settings(self.repo)
        self.assertEqual(doc["model"], "x")
        self.assertEqual(doc["permissions"]["allow"].count("Bash(git add *)"), 1)
        self.assertIn("Bash(ls *)", doc["permissions"]["allow"])
        self.assertIn("Bash(git push *)", doc["permissions"]["deny"])
        self.assertIn("Bash(git push *)", self.settings(self.wt["b"])["permissions"]["deny"])
        rec = permissions.read_record(self.db)
        self.assertTrue(rec["applied"])
        self.assertEqual(rec["original"], "按清单预配权限")
        self.assertNotIn("Bash(git add *)", rec["files"][str(mine)]["allow"])     # it was already there
        self.assertEqual(permissions.plan(self.repo)["targets"][0]["allow"], [])     # nothing left to add

    def test_refuses_all_when_one_file_is_not_ignored(self):
        git(self.repo, "config", "core.excludesFile", "/dev/null")
        (self.wt["b"] / ".gitignore").write_text("", encoding="utf-8")
        with self.assertRaises(permissions.Refused):
            permissions.apply(self.repo, "预配")
        self.assertFalse((self.repo / ".claude" / "settings.local.json").exists())
        self.assertFalse((self.wt["c"] / ".codex").exists())
        self.assertEqual(permissions.read_record(self.db), {})

    def test_refuses_broken_json_and_empty_words(self):
        bad = self.wt["b"] / ".claude" / "settings.local.json"
        bad.parent.mkdir()
        bad.write_text("{not json", encoding="utf-8")
        with self.assertRaises(permissions.Refused):
            permissions.apply(self.repo, "预配")
        self.assertEqual(bad.read_text(encoding="utf-8"), "{not json")
        bad.unlink()
        with self.assertRaises(permissions.Refused):
            permissions.apply(self.repo, "  ")

    def test_remove_only_takes_out_what_was_added(self):
        permissions.apply(self.repo, "预配")
        path = self.repo / ".claude" / "settings.local.json"
        doc = self.settings(self.repo)
        doc["permissions"]["allow"].append("Bash(make *)")
        path.write_text(json.dumps(doc), encoding="utf-8")
        permissions.remove(self.repo, "撤掉预配")
        self.assertEqual(self.settings(self.repo)["permissions"], {"allow": ["Bash(make *)"], "deny": []})
        self.assertFalse(permissions.read_record(self.db)["applied"])

    def test_cli_apply_exit_codes(self):
        self.assertEqual(self.run_cli("permissions", "apply", "--original", " ").returncode, 3)
        out = self.run_cli("permissions", "apply", "--original", "预配")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("已写", out.stdout)


if __name__ == "__main__":
    unittest.main()
