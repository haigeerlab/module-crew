"""crew-coordinator-switch: per-session coordinator switch (see spec/crew-coordinator-switch.md)."""

from __future__ import annotations

import json
import os
import unittest

from helpers import ProbeCase, StartCase, git, spec_guard_interface

from module_crew import probe


class EnabledCheckTest(ProbeCase):
    """Acceptance 2 (part): a project that never ran setup-convention is a blocker."""

    def setUp(self):
        super().setUp()
        self.plugins.install("agent-relay", {"interface": "2.0"})
        self.plugins.install("spec-guard", spec_guard_interface("1.7"), map_script=True)

    def test_enabled_when_config_present(self):
        report = probe.run(self.repo)
        self.assertEqual(report.checks["spec-guard-enabled"].state, "ok")

    def test_blocker_without_config(self):
        git(self.repo, "rm", "-q", ".agent/config.json")
        git(self.repo, "commit", "-q", "-m", "drop")
        check = probe.run(self.repo).checks["spec-guard-enabled"]
        self.assertEqual(check.state, "blocker")
        self.assertIn("setup-convention", check.fix)

    def test_no_capability_map_has_code(self):
        os.environ["FAKE_MAP_MODE"] = "exit3"
        check = probe.run(self.repo).checks["spec-guard"]
        self.assertEqual((check.state, check.code), ("blocker", "no-capability-map"))


if __name__ == "__main__":
    unittest.main()
