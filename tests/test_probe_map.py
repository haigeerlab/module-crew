import os
import unittest

from helpers import ProbeCase, spec_guard_interface

from module_crew import probe


class SpecGuardTest(ProbeCase):
    def install(self, version="1.0", command=None, mode="plain"):
        os.environ["FAKE_MAP_MODE"] = mode
        return self.plugins.install("spec-guard", spec_guard_interface(version, command), map_script=True)

    def checks(self, timeout=3):
        sg, planning, doc = probe.check_spec_guard(self.repo, timeout=timeout)
        return sg, planning, doc

    def test_interface_1_0_means_planning_layer_not_released(self):
        self.install("1.0")
        sg, planning, doc = self.checks()
        self.assertEqual(sg.state, "ok", sg.reason)
        self.assertEqual(planning.state, "blocker")
        self.assertIn("需要 interface 1.1", planning.reason)
        self.assertEqual(doc["activeModule"], "b")

    def test_interface_1_1_switch_on_with_startable(self):
        self.install("1.1", mode="on")
        sg, planning, doc = self.checks()
        self.assertEqual((sg.state, planning.state), ("ok", "ok"), planning.reason)
        self.assertEqual(doc["startable"]["modules"], ["c"])

    def test_interface_1_1_switch_off(self):
        self.install("1.1", mode="plain")
        _, planning, _ = self.checks()
        self.assertEqual(planning.state, "blocker")
        self.assertIn("moduleConcurrency", planning.reason)

    def test_interface_1_1_without_startable(self):
        self.install("1.1", mode="on-no-startable")
        _, planning, _ = self.checks()
        self.assertEqual(planning.state, "blocker")
        self.assertIn("startable", planning.reason)

    def test_unsafe_commands_are_not_run(self):
        marker = self.tmp / "ran"
        bad = {
            "not python3": ["sh", "-c", f"touch {marker}"],
            "escapes with ..": ["python3", "../../evil.py"],
            "absolute script": ["python3", str(self.tmp / "evil.py")],
        }
        (self.tmp / "evil.py").write_text(f"open({str(marker)!r}, 'w')\n")
        for name, command in bad.items():
            with self.subTest(name):
                self.plugins.entries.clear()
                self.install("1.0", command=command)
                sg, planning, doc = self.checks()
                self.assertEqual(sg.state, "blocker")
                self.assertIn("不安全", sg.reason)
                self.assertIsNone(doc)
                self.assertEqual(planning.state, "blocker")
                self.assertFalse(marker.exists())

    def test_map_failures_have_different_reasons(self):
        reasons = {}
        for mode in ("slow", "exit3", "garbage"):
            with self.subTest(mode):
                self.plugins.entries.clear()
                self.install("1.0", mode=mode)
                sg, _, doc = self.checks(timeout=1)
                self.assertEqual(sg.state, "blocker")
                self.assertIsNone(doc)
                reasons[mode] = sg.reason
        self.assertIn("超时", reasons["slow"])
        self.assertIn("没有能力图", reasons["exit3"])
        self.assertIn("不是 JSON", reasons["garbage"])

    def test_not_installed_or_wrong_major(self):
        sg, planning, _ = self.checks()
        self.assertEqual((sg.state, planning.state), ("blocker", "blocker"))
        self.plugins.install("spec-guard", {"interface": "2.0"})
        sg, _, _ = self.checks()
        self.assertIn("主版本", sg.reason)


if __name__ == "__main__":
    unittest.main()
