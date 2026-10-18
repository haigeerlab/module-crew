"""Commit messages and commit-hook failures for module-crew's own commits.

Projects such as the LIVE-SAAS frontend run husky: commitlint (Conventional Commits) on commit-msg and
lint-staged on pre-commit.  Every commit module-crew makes therefore starts with a Conventional type, and a
commit refused by a hook is reported as such instead of being folded into another reason.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

PREFIX = "chore(crew): "
HOOKS = ("pre-commit", "pre-merge-commit", "prepare-commit-msg", "commit-msg")


def message(text: str) -> str:
    """A Conventional Commits subject (header at most 100 characters)."""
    head = PREFIX + text
    return head if len(head) <= 100 else head[:99] + "…"


def _hooks_dir(checkout: Path) -> Path:
    run = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], cwd=checkout, capture_output=True, text=True)
    custom = subprocess.run(["git", "config", "core.hooksPath"], cwd=checkout, capture_output=True, text=True).stdout.strip()
    path = Path(custom or run.stdout.strip())
    return path if path.is_absolute() else Path(checkout) / path


def hooks_active(checkout: Path) -> bool:
    d = _hooks_dir(checkout)
    return any((d / name).is_file() and os.access(d / name, os.X_OK) for name in HOOKS)


def failure(checkout: Path, run: subprocess.CompletedProcess, what: str) -> str:
    """Reason line for a failed commit or merge commit."""
    out = (run.stderr.strip() or run.stdout.strip()).splitlines()
    first = out[0][:200] if out else f"退出码 {run.returncode}"
    if hooks_active(checkout):
        return f"{what}：提交钩子拒绝：{first}"
    return f"{what}：{first}"
