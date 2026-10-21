"""Commit messages and commit-hook failures for module-crew's own commits.

The subject prefix is project configuration (`commitPrefix`, set by `start prepare --commit-prefix`; 0.9.4).
It defaults to a Conventional Commits type because the first project, the LIVE-SAAS frontend, runs commitlint
on commit-msg; an empty prefix means none.  A commit refused by a hook is reported as such instead of being
folded into another reason.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

PREFIX = "chore(crew): "
HOOKS = ("pre-commit", "pre-merge-commit", "prepare-commit-msg", "commit-msg")


def prefix_of(db) -> str:
    """The project's commit prefix: `commitPrefix` from the run configuration, PREFIX when never set."""
    from module_crew import store
    cfg = store.get(db, "config", "main") or {}
    return cfg["commitPrefix"] if isinstance(cfg.get("commitPrefix"), str) else PREFIX


def message(text: str, prefix: str = PREFIX) -> str:
    """The commit subject: prefix + text, at most 100 characters."""
    head = prefix + text
    return head if len(head) <= 100 else head[:99] + "…"


def _hooks_dir(checkout: Path) -> Path:
    run = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], cwd=checkout, capture_output=True, text=True)
    custom = subprocess.run(["git", "config", "core.hooksPath"], cwd=checkout, capture_output=True, text=True).stdout.strip()
    path = Path(custom or run.stdout.strip())
    return path if path.is_absolute() else Path(checkout) / path


def hooks_active(checkout: Path) -> bool:
    d = _hooks_dir(checkout)
    return any((d / name).is_file() and os.access(d / name, os.X_OK) for name in HOOKS)


HOOK_TAIL = 10


def hook_lines(checkout: Path, run: subprocess.CompletedProcess) -> list[str]:
    """R20⑥: when commit hooks are active, their exit code and last lines, so a report shows they really ran."""
    if not hooks_active(checkout):
        return []
    out = [line for line in (run.stdout + run.stderr).splitlines() if line.strip()][-HOOK_TAIL:]
    return [f"提交钩子：退出码 {run.returncode}" + ("；最后几行输出：" if out else "；没有输出")] + [f"  {line}" for line in out]


def failure(checkout: Path, run: subprocess.CompletedProcess, what: str) -> str:
    """Reason line for a failed commit or merge commit."""
    out = (run.stderr.strip() or run.stdout.strip()).splitlines()
    first = out[0][:200] if out else f"退出码 {run.returncode}"
    if hooks_active(checkout):
        return f"{what}：提交钩子拒绝：{first}"
    return f"{what}：{first}"
