#!/usr/bin/env python3
"""Full check, one process per test file, run in parallel (T802).

`scripts/validate.sh` runs this. Each `tests/test_*.py` runs as `python3 -m unittest <module>` in its own process
(the same PYTHONPATH as scripts/quick_check.py), at most `--jobs` at a time (default: the CPU count). The tests do not
share files outside their own temp dirs, and the environment variables they set live in their own process.
Files in ALONE assert a wall-clock bound (test_hub_output: `sessions --json` within 1 s, spec crew-hub-bridge #8) that
CPU contention breaks; they run one at a time after the parallel phase, with nothing else running.

Output: the full output of every file that failed or errored, then one summary in unittest's words (`Ran N tests`,
`OK` / `FAILED (...)`), then the 10 slowest files and a warning when the whole run took longer than 15 minutes.
Exit code: 0 when every file passed, otherwise the exit code of the first failing file (unittest's 1).
Standard library only, Python 3.9.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLOWEST = 10
WARN_SECONDS = 15 * 60
ALONE = ("test_hub_output",)

_RAN = re.compile(r"^Ran (\d+) tests? in ", re.M)
_COUNTS = re.compile(r"(failures|errors|skipped|expected failures|unexpected successes)=(\d+)")


class Result:
    def __init__(self, name: str, code: int, output: str, seconds: float):
        self.name, self.code, self.output, self.seconds = name, code, output, seconds
        found = _RAN.findall(output)
        self.ran = int(found[-1]) if found else 0
        tail = output[output.rfind("\nRan "):] if "\nRan " in output else ""
        self.counts = {k: int(v) for k, v in _COUNTS.findall(tail)}


def list_test_files(start: Path) -> list[str]:
    return sorted(p.stem for p in start.glob("test_*.py"))


def run_one(root: Path, start: Path, name: str) -> Result:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(start), str(root), env.get("PYTHONPATH")]))
    began = time.monotonic()
    done = subprocess.run([sys.executable, "-m", "unittest", name], cwd=root, env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return Result(name, done.returncode, done.stdout, time.monotonic() - began)


def summary(results: list[Result]) -> list[str]:
    """unittest's closing lines for the whole run."""
    ran = sum(r.ran for r in results)
    totals: dict[str, int] = {}
    for r in results:
        for k, v in r.counts.items():
            totals[k] = totals.get(k, 0) + v
    failed = [r for r in results if r.code != 0]
    for r in failed:   # a file that crashed before unittest reported counts its failure here
        if not r.counts.get("failures") and not r.counts.get("errors"):
            totals["errors"] = totals.get("errors", 0) + 1
    order = ("failures", "errors", "skipped", "expected failures", "unexpected successes")
    detail = ", ".join(f"{k}={totals[k]}" for k in order if totals.get(k))
    word = "FAILED" if failed else "OK"
    return [f"Ran {ran} tests in {len(results)} files", f"{word} ({detail})" if detail else word]


def timing_report(results: list[Result], wall: float, limit: int = SLOWEST, warn: float = WARN_SECONDS) -> list[str]:
    slow = sorted(results, key=lambda r: (-r.seconds, r.name))[:limit]
    lines = [f"最慢的 {len(slow)} 个测试文件："]
    lines += [f"  {r.seconds:7.1f}s  {r.name}" for r in slow]
    lines.append(f"全量检查墙钟 {wall:.1f}s")
    if wall > warn:
        lines.append(f"提醒：全量检查用了 {wall / 60:.1f} 分钟，超过 {warn / 60:.0f} 分钟，要提速"
                     "（并行、复用准备环境、去掉真等待），不能靠删测试、跳过测试或砍 CI 矩阵")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按测试文件并行跑全量检查")
    parser.add_argument("--jobs", "-j", type=int, default=os.cpu_count() or 1, help="同时跑几个测试文件（默认 CPU 核数）")
    parser.add_argument("--start-dir", default="tests", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs 至少为 1")
    start = (ROOT / args.start_dir).resolve()
    names = list_test_files(start)
    if not names:
        print(f"{start} 下没有 test_*.py", file=sys.stderr)
        return 5
    began = time.monotonic()
    shared = [n for n in names if n not in ALONE]
    results = []
    if shared:
        with ThreadPoolExecutor(max_workers=min(args.jobs, len(shared))) as pool:
            results = list(pool.map(lambda n: run_one(ROOT, start, n), shared))
    results += [run_one(ROOT, start, n) for n in names if n in ALONE]
    results.sort(key=lambda r: r.name)
    wall = time.monotonic() - began
    failed = [r for r in results if r.code != 0]
    for r in failed:
        print(f"===== {r.name}（退出码 {r.code}）=====")
        print(r.output.rstrip())
        print()
    print("----------------------------------------------------------------------")
    print("\n".join(summary(results)))
    if failed:
        print("失败的测试文件：" + "、".join(r.name for r in failed))
    print("\n".join(timing_report(results, wall)))
    sys.stdout.flush()
    return failed[0].code if failed else 0


if __name__ == "__main__":
    sys.exit(main())
