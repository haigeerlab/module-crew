"""Read-only facts the decision inbox uses to notice a stalled module (see spec/crew-stall-signals.md).

No thresholds and no verdicts here: how long is too long, and how many asks are too many, is the inbox's call.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git(worktree: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(worktree), *args], capture_output=True, text=True)


def _error(out: subprocess.CompletedProcess) -> str:
    return (out.stderr.strip().splitlines() or [f"git 退出码 {out.returncode}"])[0]


def commit_facts(worktree: str | None, integration: str | None) -> dict:
    """Commits on the worktree's HEAD that are not on the integration branch: how many, and the latest one."""
    failed = {"ahead": None, "last": None}
    if not integration:
        return {**failed, "error": "运行配置没有集成分支"}
    path = Path(worktree) if worktree else None
    if path is None or not path.is_dir():
        return {**failed, "error": f"worktree 不存在：{worktree}"}
    span = f"{integration}..HEAD"
    count = _git(path, "rev-list", "--count", span)
    if count.returncode != 0:
        return {**failed, "error": _error(count)}
    ahead = int(count.stdout.strip())
    if ahead == 0:
        return {"ahead": 0, "last": None, "error": None}
    log = _git(path, "log", "-1", "--format=%H%x00%cI", span)
    if log.returncode != 0:
        return {**failed, "error": _error(log)}
    commit, at = log.stdout.strip().split("\0")
    return {"ahead": ahead, "last": {"commit": commit, "at": at}, "error": None}


def started_at(events: list[dict], name: str) -> str | None:
    """When `start prepare` registered this session; a takeover does not move it."""
    return next((e["at"] for e in reversed(events) if e["type"] == "session.registered" and e["key"] == name), None)
