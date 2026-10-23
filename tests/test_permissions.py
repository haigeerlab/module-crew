"""crew-host-permissions: permission rules the host honours, written only with the user's words (spec/crew-host-permissions.md)."""

import json
import os
import unittest
import unittest.mock
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
        assert start.prepare(self.repo, ["b"], "开 b", short="shop", max_modules=3).code == 0   # room for d
        assert start.prepare(self.repo, ["c"], "开 c", host="codex").code == 0
        self.db = store.open_store(self.repo)
        sessions = store.records(self.db, "session")
        self.wt = {rec["module"]: Path(rec["worktree"]) for rec in sessions.values() if rec.get("role") == "dev"}
        self.codex_home = self.tmp / "codex-home"
        self.codex_home.mkdir()
        old = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = str(self.codex_home)
        self.addCleanup(lambda: os.environ.__setitem__("CODEX_HOME", old) if old else os.environ.pop("CODEX_HOME", None))
        self.claude_home = self.tmp / "claude-home"     # keep the real ~/.claude/settings.json out of the tests
        self.claude_home.mkdir()
        old_claude = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.claude_home)
        self.addCleanup(lambda: os.environ.__setitem__("CLAUDE_CONFIG_DIR", old_claude) if old_claude
                        else os.environ.pop("CLAUDE_CONFIG_DIR", None))
        managed = unittest.mock.patch.object(permissions, "MANAGED_SETTINGS", self.tmp / "managed-settings.json")
        managed.start()
        self.addCleanup(managed.stop)

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
        self.assertIn(f"Bash({self.db.path / 'bin' / 'module-crew'} *)", claude["allow"])   # fixed entry (0.12.1)
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
        self.assertEqual(self.settings(self.repo)["permissions"], {"allow": ["Bash(make *)"]})
        self.assertFalse(permissions.read_record(self.db)["applied"])

    def test_remove_restores_the_original_text_byte_for_byte(self):
        mine = self.wt["b"] / ".claude" / "settings.local.json"
        mine.parent.mkdir()
        original = '{"permissions":{"allow":["Bash(ls *)"]},\n "model":"x"}\n'
        mine.write_text(original, encoding="utf-8")
        permissions.apply(self.repo, "预配")
        self.assertNotEqual(mine.read_text(encoding="utf-8"), original)
        permissions.remove(self.repo, "撤掉")
        self.assertEqual(mine.read_text(encoding="utf-8"), original)
        self.assertEqual(json.loads((self.repo / ".claude" / "settings.local.json").read_text(encoding="utf-8")), {})

    def test_cli_apply_exit_codes(self):
        self.assertEqual(self.run_cli("permissions", "apply", "--original", " ").returncode, 3)
        out = self.run_cli("permissions", "apply", "--original", "预配")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("已写", out.stdout)


def parse_rules(text: str) -> list[tuple[list, str]]:
    """(pattern, decision) of every prefix_rule in a generated file."""
    import re
    return [(json.loads(m.group(1)), json.loads(m.group(2)))
            for m in re.finditer(r"pattern = (\[.*?\]),\n    decision = (\"\w+\")", text)]


class CodexRulesTest(PermCase):
    def rules_file(self):
        return self.wt["c"] / ".codex" / "rules" / "module-crew.rules"

    def test_apply_writes_codex_rules_only_for_codex_worktrees(self):
        lines = permissions.apply(self.repo, "预配")
        text = self.rules_file().read_text(encoding="utf-8")
        self.assertEqual(text.splitlines()[0], permissions.CODEX_MARK)
        rules = dict((" ".join(p), d) for p, d in parse_rules(text))
        self.assertEqual(rules["git push"], "forbidden")
        self.assertEqual(rules["rm -rf"], "forbidden")
        self.assertEqual(rules["git commit"], "allow")
        self.assertEqual(text.count("prefix_rule("), text.count("\n    match = ["))
        self.assertEqual(text.count("prefix_rule("), text.count("not_match = ["))
        self.assertFalse((self.wt["b"] / ".codex").exists())
        self.assertFalse((self.wt["c"] / ".claude" / "settings.local.json").exists())
        self.assertTrue(any("规则不会生效" in l for l in lines))

    def test_foreign_rules_file_is_not_overwritten(self):
        self.rules_file().parent.mkdir(parents=True)
        self.rules_file().write_text("prefix_rule(pattern=[\"ls\"])\n", encoding="utf-8")
        with self.assertRaises(permissions.Refused):
            permissions.apply(self.repo, "预配")
        self.assertIn("ls", self.rules_file().read_text(encoding="utf-8"))

    def test_remove_empties_the_rules_file(self):
        permissions.apply(self.repo, "预配")
        permissions.remove(self.repo, "撤掉")
        text = self.rules_file().read_text(encoding="utf-8")
        self.assertEqual(text.splitlines()[0], permissions.CODEX_MARK)
        self.assertNotIn("prefix_rule(", text)


class WorktreeEditTest(PermCase):
    """crew-stage-c-fixes Task 3 (MC-13): edits inside a module worktree are allowed, its .claude/ is not."""

    def edit_rules(self, wt: Path) -> tuple[str, str]:
        root = "//" + str(wt).lstrip("/")
        return f"Edit({root}/**)", f"Edit({root}/.claude/**)"

    def test_module_worktree_only(self):
        allow, deny = self.edit_rules(self.wt["b"])
        targets = {t["checkout"]: t for t in permissions.plan(self.repo)["targets"]}
        self.assertIn(allow, targets[str(self.wt["b"])]["allow"])
        self.assertIn(deny, targets[str(self.wt["b"])]["deny"])
        self.assertFalse(any(e.startswith("Edit(") for e in targets[str(self.repo)]["allow"] + targets[str(self.repo)]["deny"]))
        permissions.apply(self.repo, "预配")
        doc = self.settings(self.wt["b"])["permissions"]
        self.assertIn(allow, doc["allow"])
        self.assertIn(deny, doc["deny"])
        self.assertFalse(any(e.startswith("Edit(") for e in self.settings(self.repo)["permissions"]["allow"]))
        permissions.remove(self.repo, "撤掉")
        doc = self.settings(self.wt["b"]).get("permissions", {})
        self.assertNotIn(allow, doc.get("allow", []))
        self.assertNotIn(deny, doc.get("deny", []))

    def test_prepare_follows(self):
        permissions.apply(self.repo, "预配")
        res = start.prepare(self.repo, ["d"], "开 d")
        d = Path(res.prepared[0]["worktree"])
        allow, deny = self.edit_rules(d)
        self.assertIn(allow, self.settings(d)["permissions"]["allow"])
        self.assertIn(deny, self.settings(d)["permissions"]["deny"])


class FollowAndVerifyTest(PermCase):
    def test_prepare_follows_after_apply(self):
        permissions.apply(self.repo, "预配")
        res = start.prepare(self.repo, ["d"], "开 d")
        self.assertEqual(res.code, 0, res.lines)
        d = Path(res.prepared[0]["worktree"])
        self.assertIn("Bash(git push *)", self.settings(d)["permissions"]["deny"])
        self.assertTrue(any("已写权限规则" in l for l in res.lines))
        self.assertIn(str(d / ".claude" / "settings.local.json"), permissions.read_record(self.db)["files"])

    def test_prepare_does_not_write_before_apply(self):
        res = start.prepare(self.repo, ["d"], "开 d")
        self.assertFalse((Path(res.prepared[0]["worktree"]) / ".claude" / "settings.local.json").exists())

    def test_follow_failure_does_not_block_and_shows_in_status(self):
        from unittest import mock
        permissions.apply(self.repo, "预配")
        real = permissions._ignored
        with mock.patch.object(permissions, "_ignored", lambda c, rel: c.name != "d" and real(c, rel)):
            res = start.prepare(self.repo, ["d"], "开 d")
        self.assertEqual(res.code, 0, res.lines)
        self.assertTrue(any("没给 shop-d 写权限规则" in l for l in res.lines))
        line = next(l for l in self.run_cli("status").stdout.splitlines() if l.startswith("  shop-d"))
        self.assertIn("权限规则没写上", line)

    def test_verify_list_and_record(self):
        text = "\n".join(permissions.verify_list(self.repo))
        self.assertIn(permissions.DENIED_PROBE, text)
        self.assertIn("--record", text)
        line = next(l for l in self.run_cli("status").stdout.splitlines() if l.startswith("  shop-b"))
        self.assertIn("权限未实测", line)
        out = self.run_cli("permissions", "verify", "--record", "shop-b", "--allowed", "ok", "--denied", "ok")
        self.assertEqual(out.returncode, 0, out.stderr)
        line = next(l for l in self.run_cli("status").stdout.splitlines() if l.startswith("  shop-b"))
        self.assertIn("放行如预期、拒绝如预期", line)
        self.assertEqual(self.run_cli("permissions", "verify", "--record", "shop-x", "--allowed", "ok",
                                      "--denied", "ok").returncode, 3)
        self.assertEqual(self.run_cli("permissions", "verify", "--record", "shop-b").returncode, 3)


def _claude_matches(rule: str, cmd: str) -> bool:
    """Claude Code's Bash rule shape: `*` stands for any text; a lone trailing ` *` also matches the bare command."""
    import re
    body = rule[len("Bash("):-1]
    if body.endswith(" *") and body.count("*") == 1 and cmd == body[:-2]:
        return True
    return re.fullmatch(".*".join(map(re.escape, body.split("*"))), cmd) is not None


class ProjectInstallTest(PermCase):
    """R21 MC-1 after decision 62 (acceptance 13, 0.5.1): installs allowed, adding packages too; bare pip and global denied."""

    ALLOWED = ["npm ci", "npm ci --dry-run", "npm install", "pnpm install", "pnpm install --frozen-lockfile", "yarn install",
               "uv sync", "uv sync --frozen", "pip install -r requirements.txt", ".venv/bin/pip install -r requirements.txt",
               "npm install lodash", "npm install --save-dev vitest", "pnpm add zod", "yarn add react", "uv add httpx",
               "uv pip install httpx", ".venv/bin/pip install requests"]
    NO_RULE = ["pip install requests", "pip3 install requests"]
    DENIED = ["npm install -g lodash", "npm install lodash -g", "npm i -g lodash", "npm i --global lodash",
              "npm install --global lodash", "pnpm add -g zod", "pnpm add zod --global", "yarn global add serve",
              "uv pip install --system httpx", "brew install jq"]

    def decide(self, entries, cmd):
        if any(_claude_matches(r, cmd) for r in entries["deny"] if r.startswith("Bash(")):
            return "deny"
        if any(_claude_matches(r, cmd) for r in entries["allow"] if r.startswith("Bash(")):
            return "allow"
        return None

    def test_claude_lists(self):
        entries = permissions.claude_entries({}, "/x/.git/module-crew/bin/module-crew")
        for cmd in self.ALLOWED:
            self.assertEqual(self.decide(entries, cmd), "allow", cmd)
        for cmd in self.NO_RULE:                             # the host's own confirmation decides
            self.assertIsNone(self.decide(entries, cmd), cmd)
        for cmd in self.DENIED:
            self.assertEqual(self.decide(entries, cmd), "deny", cmd)
        self.assertNotIn("Bash(pip install *)", entries["allow"] + entries["deny"])

    def test_plan_preview_shows_both(self):
        target = next(t for t in permissions.plan(self.repo)["targets"] if t["role"] == "integration")
        self.assertIn("Bash(npm ci)", target["allow"])
        self.assertIn("Bash(pnpm add *)", target["allow"])
        self.assertIn("Bash(npm install -g *)", target["deny"])
        self.assertIn("Bash(npm * -g *)", target["deny"])

    @unittest.skipUnless(__import__("shutil").which("codex"), "本机没有 codex 命令")
    def test_codex_decisions(self):
        import subprocess, tempfile
        rules = permissions.render_codex(permissions.codex_rules({}, "/x/.git/module-crew/bin/module-crew"))
        with tempfile.NamedTemporaryFile("w", suffix=".rules", delete=False) as f:
            f.write(rules)
        def decide(cmd):
            out = subprocess.run(["codex", "execpolicy", "check", "--rules", f.name, *cmd.split()],
                                 capture_output=True, text=True, stdin=subprocess.DEVNULL)
            return json.loads(out.stdout).get("decision")
        self.assertEqual(decide("npm ci"), "allow")
        self.assertEqual(decide("pip install -r requirements.txt"), "allow")
        self.assertIsNone(decide("npm install lodash"))      # a prefix rule cannot stop `npm install x -g`
        self.assertIsNone(decide("pnpm add zod"))
        self.assertIsNone(decide("pip install requests"))
        for cmd in ("npm install -g lodash", "npm i -g lodash", "npm install --global lodash", "npm i --global lodash",
                    "pnpm add -g zod", "pnpm add --global zod", "yarn global add serve", "brew install jq"):
            self.assertEqual(decide(cmd), "forbidden", cmd)

def _write(path: Path, doc: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


class ShadowTest(PermCase):
    """Acceptance 14 (0.5.3): ask/deny rules elsewhere that would win over an allow module-crew writes."""

    def target(self, key):
        return next(t for t in permissions.plan(self.repo)["targets"] if t["role"] + ":" + (t["module"] or "") == key)

    def test_main_checkout_ask_shadows_the_worktree_allow(self):
        main = _write(self.repo / ".claude" / "settings.local.json", {"permissions": {"ask": ["Bash(npm install *)"]}})
        found = self.target("dev:b")["shadowed"]
        self.assertIn({"allow": "Bash(npm install *)", "file": str(main), "kind": "ask", "rule": "Bash(npm install *)"},
                      found)
        self.assertNotIn("Bash(npm ci *)", [f["allow"] for f in found])
        text = "\n".join(permissions.render_plan(permissions.plan(self.repo)))
        self.assertIn(f"会被盖过：Bash(npm install *) ← {main} 的 ask Bash(npm install *)", text)

    def test_user_settings_and_the_checkout_own_settings_json(self):
        user = _write(self.claude_home / "settings.json", {"permissions": {"deny": ["Bash(git commit:*)"]}})
        own = _write(self.wt["b"] / ".claude" / "settings.json", {"permissions": {"ask": ["Bash(pnpm add *)"]}})
        b = self.target("dev:b")["shadowed"]
        self.assertIn({"allow": "Bash(git commit *)", "file": str(user), "kind": "deny", "rule": "Bash(git commit:*)"}, b)
        self.assertIn({"allow": "Bash(pnpm add *)", "file": str(own), "kind": "ask", "rule": "Bash(pnpm add *)"}, b)
        integration = self.target("integration:")["shadowed"]
        self.assertIn("Bash(git commit *)", [f["allow"] for f in integration])
        self.assertNotIn("Bash(pnpm add *)", [f["allow"] for f in integration])
        text = "\n".join(permissions.render_plan(permissions.plan(self.repo)))
        self.assertIn(f"的 禁止 Bash(git commit:*)", text)

    def test_managed_settings_and_bare_tool_rules(self):
        _write(permissions.MANAGED_SETTINGS, {"permissions": {"ask": ["Bash"], "deny": ["mcp__agent-relay"]}})
        b = self.target("dev:b")["shadowed"]
        self.assertIn("Bash(npm ci)", [f["allow"] for f in b])
        self.assertIn("mcp__agent-relay", [f["allow"] for f in b])

    def test_nothing_to_report_without_conflicts(self):
        _write(self.claude_home / "settings.json", {"permissions": {"ask": ["Bash(terraform apply *)"],
                                                                     "deny": ["Bash(npm install -g *)"]}})
        p = permissions.plan(self.repo)
        self.assertTrue(all(t.get("shadowed") == [] for t in p["targets"] if "rules" not in t))
        self.assertNotIn("会被盖过", "\n".join(permissions.render_plan(p)))

    def test_apply_reports_but_still_writes_and_leaves_other_files(self):
        user = _write(self.claude_home / "settings.json", {"permissions": {"ask": ["Bash(npm install *)"]}})
        own = _write(self.wt["b"] / ".claude" / "settings.json", {"permissions": {"deny": ["Bash(git add *)"]}})
        before = (user.read_bytes(), own.read_bytes())
        lines = permissions.apply(self.repo, "预配")
        self.assertTrue(any("会被盖过：Bash(npm install *)" in l for l in lines))
        self.assertIn("Bash(npm install *)", self.settings(self.wt["b"])["permissions"]["allow"])
        self.assertEqual((user.read_bytes(), own.read_bytes()), before)


class CodexStaticTest(PermCase):
    @unittest.skipUnless(__import__("shutil").which("codex"), "本机没有 codex 命令")
    def test_execpolicy_check_on_the_written_rules(self):
        permissions.apply(self.repo, "预配")
        text = "\n".join(permissions.verify_list(self.repo, "codex"))
        self.assertIn("git push origin main → forbidden", text)
        self.assertIn("rm -rf build → forbidden", text)
        self.assertIn("git commit -m x → allow", text)


if __name__ == "__main__":
    unittest.main()
