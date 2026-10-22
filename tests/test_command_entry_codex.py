"""crew-command-entry: bin/module-crew runs its own plugin's code; Codex sessions use a fixed launcher."""

import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import PLUGIN_ROOT

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


if __name__ == "__main__":
    unittest.main()
