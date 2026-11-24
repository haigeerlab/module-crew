#!/usr/bin/env bash
# Unified check entry (plugin development standard C2). CI, Codex review and autopilot all call this.
#   scripts/validate.sh          full check: python3 -m unittest discover -s tests
#   scripts/validate.sh --quick  quick check: scripts/quick_check.py (only the tests this branch touches)
# Uses whichever python3 is first on PATH. Bash 3.2 compatible.
set -eu

cd "$(dirname "$0")/.."

case "${1:-}" in
  "")
    exec python3 -m unittest discover -s tests
    ;;
  --quick)
    exec python3 scripts/quick_check.py
    ;;
  *)
    echo "用法：scripts/validate.sh [--quick]" >&2
    exit 2
    ;;
esac
