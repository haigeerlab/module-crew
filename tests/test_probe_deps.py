import json
import os
import unittest

from helpers import ProbeCase

from module_crew import probe


class FindPluginTest(ProbeCase):
    def test_project_scope_wins_over_user(self):
        user = self.plugins.install("agent-relay", {"interface": "2.0"})
        local = self.plugins.install("agent-relay", {"interface": "2.0"}, scope="local", project=self.repo)
        found = probe.find_plugin("agent-relay", self.repo)
        self.assertEqual(found.root, local)
        self.assertNotEqual(found.root, user)

    def test_only_installed_for_another_project(self):
        self.plugins.install("agent-relay", {"interface": "2.0"}, scope="local", project=self.tmp / "other")
        found = probe.find_plugin("agent-relay", self.repo)
        self.assertIsInstance(found, str)
        self.assertIn("只装在别的项目里", found)
        check = probe.check_relay(self.repo)
        self.assertEqual(check.state, "blocker")
        self.assertIn("只装在别的项目里", check.reason)

    def test_not_installed(self):
        self.assertIn("没有安装", probe.check_relay(self.repo).reason)

    def test_directory_marketplace_uses_source(self):
        src = self.tmp / "src-market"
        (src / ".claude-plugin").mkdir(parents=True)
        (src / "relay" / ".claude-plugin").mkdir(parents=True)
        (src / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps({"plugins": [{"name": "agent-relay", "source": "./relay"}]}))
        (src / "relay" / ".claude-plugin" / "plugin.json").write_text(json.dumps({"version": "0.7.0"}))
        (self.plugins.records.parent / "known_marketplaces.json").write_text(
            json.dumps({"m": {"source": {"source": "directory", "path": str(src)}}}))
        self.plugins.install("agent-relay", {"interface": "2.0"})
        found = probe.find_plugin("agent-relay", self.repo)
        self.assertEqual(found.root, (src / "relay").resolve())
        self.assertEqual(found.version, "0.7.0")


class RelayInterfaceTest(ProbeCase):
    def test_versions(self):
        cases = {"2.0": ("ok", None), "2.3": ("ok", None), "1.0": ("blocker", "主版本"),
                 "3.0": ("blocker", "主版本")}
        for version, (state, words) in cases.items():
            with self.subTest(version):
                self.plugins.entries.clear()
                self.plugins.install("agent-relay", {"interface": version})
                check = probe.check_relay(self.repo)
                self.assertEqual(check.state, state, check.reason)
                if words:
                    self.assertIn(words, check.reason)

    def test_missing_and_broken_files_have_different_reasons(self):
        self.plugins.install("agent-relay", None)
        missing = probe.check_relay(self.repo)
        self.plugins.entries.clear()
        self.plugins.install("agent-relay", "{broken")
        broken = probe.check_relay(self.repo)
        self.assertEqual((missing.state, broken.state), ("blocker", "blocker"))
        self.assertIn("没有 interface.json", missing.reason)
        self.assertIn("读不出", broken.reason)
        self.assertTrue(missing.fix and broken.fix)

    def test_env_var_is_set_in_tests(self):
        self.assertTrue(os.environ["MODULE_CREW_PLUGINS_FILE"].startswith(str(self.tmp)))


if __name__ == "__main__":
    unittest.main()
