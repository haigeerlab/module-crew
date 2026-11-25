"""T802: the full check runs one process per test file in parallel and reports the slowest files."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import unittest.mock
from pathlib import Path

from helpers import PLUGIN_ROOT

_spec = importlib.util.spec_from_file_location("run_tests_parallel", PLUGIN_ROOT / "scripts" / "run_tests_parallel.py")
rtp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rtp)

PASSING = textwrap.dedent("""\
    import unittest
    class T(unittest.TestCase):
        def test_a(self): pass
        def test_b(self): pass
    """)
FAILING = textwrap.dedent("""\
    import unittest
    class T(unittest.TestCase):
        def test_ok(self): pass
        def test_broken(self): self.assertEqual(1, 2, "deliberate-failure-marker")
    """)


def fake(name: str, seconds: float) -> "rtp.Result":
    return rtp.Result(name, 0, "Ran 1 test in 0.0s\n\nOK\n", seconds)


class RunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="crew-rtp-")).resolve()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def run_runner(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(PLUGIN_ROOT / "scripts" / "run_tests_parallel.py"),
                               "--start-dir", str(self.dir), *args], capture_output=True, text=True)

    def test_all_pass_counts_every_test_and_exits_zero(self):
        (self.dir / "test_one.py").write_text(PASSING)
        (self.dir / "test_two.py").write_text(PASSING)
        done = self.run_runner("--jobs", "2")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("Ran 4 tests in 2 files", done.stdout)
        self.assertIn("\nOK\n", done.stdout)
        self.assertIn("最慢的 2 个测试文件：", done.stdout)
        self.assertNotIn("提醒：", done.stdout)

    def test_a_failing_test_exits_nonzero_and_shows_its_output(self):
        (self.dir / "test_good.py").write_text(PASSING)
        (self.dir / "test_bad.py").write_text(FAILING)
        done = self.run_runner()
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("===== test_bad（退出码 1）=====", done.stdout)
        self.assertIn("deliberate-failure-marker", done.stdout)
        self.assertIn("Ran 4 tests in 2 files", done.stdout)
        self.assertIn("FAILED (failures=1)", done.stdout)
        self.assertIn("失败的测试文件：test_bad", done.stdout)
        self.assertNotIn("===== test_good", done.stdout)

    def test_a_file_that_cannot_import_counts_as_an_error(self):
        (self.dir / "test_crash.py").write_text("import no_such_module_t802\n")
        done = self.run_runner("--jobs", "1")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("no_such_module_t802", done.stdout)
        self.assertIn("FAILED (errors=1)", done.stdout)

    def test_jobs_must_be_positive(self):
        (self.dir / "test_one.py").write_text(PASSING)
        done = self.run_runner("--jobs", "0")
        self.assertEqual(done.returncode, 2)

    def test_jobs_defaults_to_cpu_count(self):
        with unittest.mock.patch.object(rtp.os, "cpu_count", return_value=7), \
                unittest.mock.patch.object(rtp, "ThreadPoolExecutor", wraps=rtp.ThreadPoolExecutor) as pool:
            (self.dir / "test_one.py").write_text(PASSING)
            for i in range(8):
                (self.dir / f"test_n{i}.py").write_text(PASSING)
            with unittest.mock.patch("sys.stdout"):
                code = rtp.main(["--start-dir", str(self.dir)])
        self.assertEqual(code, 0)
        self.assertEqual(pool.call_args.kwargs["max_workers"], 7)


    def test_alone_files_start_after_every_other_file_finished(self):
        stamp = textwrap.dedent("""\
            import os, time, unittest
            from pathlib import Path
            class T(unittest.TestCase):
                def test_stamp(self):
                    here = Path(__file__).with_suffix(".stamp")
                    began = time.time(); time.sleep(0.3)
                    here.write_text(f"{began} {time.time()}")
            """)
        for name in ("test_a", "test_b", "test_late"):
            (self.dir / f"{name}.py").write_text(stamp)
        with unittest.mock.patch.object(rtp, "ALONE", ("test_late",)), unittest.mock.patch("sys.stdout"):
            code = rtp.main(["--start-dir", str(self.dir), "--jobs", "4"])
        self.assertEqual(code, 0)
        times = {n: [float(x) for x in (self.dir / f"{n}.stamp").read_text().split()] for n in ("test_a", "test_b", "test_late")}
        self.assertGreaterEqual(times["test_late"][0], max(times["test_a"][1], times["test_b"][1]))
        self.assertIn("test_hub_output", rtp.ALONE)


class TimingReportTest(unittest.TestCase):
    def test_lists_only_the_ten_slowest_slowest_first(self):
        results = [fake(f"test_{i:02d}", float(i)) for i in range(12)]
        lines = rtp.timing_report(results, wall=30.0)
        self.assertEqual(lines[0], "最慢的 10 个测试文件：")
        names = [line.split()[-1] for line in lines[1:11]]
        self.assertEqual(names, [f"test_{i:02d}" for i in range(11, 1, -1)])
        self.assertEqual(lines[11], "全量检查墙钟 30.0s")
        self.assertEqual(len(lines), 12)

    def test_warns_only_past_fifteen_minutes(self):
        results = [fake("test_a", 1.0)]
        self.assertFalse(any(l.startswith("提醒：") for l in rtp.timing_report(results, wall=15 * 60)))
        warned = rtp.timing_report(results, wall=15 * 60 + 1)
        self.assertTrue(warned[-1].startswith("提醒：全量检查用了 15.0 分钟，超过 15 分钟"), warned[-1])


class ValidateEntryTest(unittest.TestCase):
    def test_validate_rejects_unknown_arguments(self):
        done = subprocess.run(["bash", str(PLUGIN_ROOT / "scripts" / "validate.sh"), "--nope"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)
        self.assertIn("--jobs N", done.stderr)

    def test_validate_full_check_uses_the_parallel_runner(self):
        text = (PLUGIN_ROOT / "scripts" / "validate.sh").read_text(encoding="utf-8")
        self.assertIn('exec python3 scripts/run_tests_parallel.py ${1+"$@"}', text)


if __name__ == "__main__":
    unittest.main()
