"""S20 (T61): handover guide and README fixes found in the LIVE-SAAS rehearsal."""

import json
import re
import unittest
from pathlib import Path
from unittest import mock

from helpers import PLUGIN_ROOT, StartCase

from module_crew import handover, permissions, store
from test_host_handover import close_batch
from test_permissions import PermCase

README = (PLUGIN_ROOT / "README.md").read_text(encoding="utf-8")


def section(title: str) -> str:
    return README.split(f"## {title}", 1)[1].split("\n## ", 1)[0]


class ReadmeTest(unittest.TestCase):
    def test_permissions_section_says_coordinator_up_first(self):
        text = section("权限预配")
        self.assertIn("coordinator up", text)
        self.assertLess(text.index("coordinator up"), text.index("module-crew permissions plan"))

    def test_codex_section_names_both_codex_skills(self):
        step = section("Codex 模块会话").split("\n1. ", 1)[1].split("\n2. ", 1)[0]
        self.assertNotIn("只提供 Codex 版 `crew-dev` skill", step)
        self.assertIn("crew-coordinator", step)


class PlanWithoutCoordinatorTest(StartCase):
    def test_no_store_says_coordinator_up(self):
        r = self.run_cli("permissions", "plan")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("coordinator up", r.stdout + r.stderr)

    def test_no_active_coordinator_says_coordinator_up(self):
        db, _ = store.init_store(self.repo)
        lines = permissions.render_plan(permissions.plan(self.repo))
        self.assertIn("coordinator up", lines[0])


class GuideTest(PermCase):
    def to(self, host="codex"):
        skill = self.tmp / "SKILL.md"
        skill.write_text("x", encoding="utf-8")
        with mock.patch.object(handover, "codex_coordinator_skill", return_value=skill):
            return handover.handover(self.repo, host, "换到 Codex")

    def guide(self) -> str:
        return sorted((self.db.path / "handover-guide").glob("*.md"))[-1].read_text(encoding="utf-8")

    def test_trust_step_comes_before_pasting_opening(self):
        close_batch(self.db)
        self.assertEqual(self.to()[0], 0)
        text = self.guide()
        steps = text.split("## 开场文字", 1)[0]
        self.assertLess(steps.index("信任这个项目"), steps.index("开场文字」整段贴进去"))

    def test_codex_rules_not_ignored_adds_gitignore_step(self):
        permissions.apply(self.repo, "按清单预配权限")
        close_batch(self.db)
        (self.repo / ".gitignore").write_text(".claude/settings.local.json\n", encoding="utf-8")
        code, lines = self.to()
        self.assertEqual(code, 0, lines)
        text = self.guide()
        self.assertIn(".codex/rules/module-crew.rules", text)
        self.assertIn(".gitignore", text)
        self.assertIn("公共文件", text)
        self.assertRegex(text, r"### 第 \d+ 步[^#]*\.gitignore[^#]*permissions apply")


class StatusHostTest(PermCase):
    def host(self) -> str:
        return json.loads(self.run_cli("status", "--json").stdout)["host"]

    def test_host_follows_registered_coordinator(self):
        self.assertIn("模块协调：Claude", self.host())
        close_batch(self.db)
        skill = self.tmp / "SKILL.md"
        skill.write_text("x", encoding="utf-8")
        with mock.patch.object(handover, "codex_coordinator_skill", return_value=skill):
            self.assertEqual(handover.handover(self.repo, "codex", "换")[0], 0)
        self.assertIn("模块协调：Codex", self.host())


if __name__ == "__main__":
    unittest.main()
