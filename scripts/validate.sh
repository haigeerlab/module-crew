#!/usr/bin/env bash
# Unified check entry (plugin development standard C2). CI, Codex review and autopilot all call this.
#   scripts/validate.sh            full check: scripts/run_tests_parallel.py (every tests/test_*.py, one process
#                                  per file, CPU-count files at a time; prints the 10 slowest files)
#   scripts/validate.sh --jobs N   full check, N files at a time
#   scripts/validate.sh --quick    quick check: scripts/quick_check.py (only the tests this branch touches)
# Uses whichever python3 is first on PATH. Bash 3.2 compatible.
set -eu

cd "$(dirname "$0")/.."

case "${1:-}" in
  ""|--jobs|-j)
    exec python3 scripts/run_tests_parallel.py ${1+"$@"}
    ;;
  --quick)
    exec python3 scripts/quick_check.py
    ;;
  *)
    echo "用法：scripts/validate.sh [--quick | --jobs N]" >&2
    exit 2
    ;;
esac
