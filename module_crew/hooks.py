"""Role-aware context for SessionStart / UserPromptSubmit hooks, and takeover (see spec/crew-recovery-hooks.md).

Read-only and fast: only the store and git metadata files are read; no probe, no /map.
Anything unexpected means "not a module-crew session" and the hook stays silent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from module_crew import store


@dataclass(frozen=True)
class Role:
    kind: str                     # dev / coordinator
    name: str                     # relay name
    module: str | None
    db: store.Store


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _ref(head_file: Path) -> str | None:
    try:
        text = head_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text[len("ref: refs/heads/"):] if text.startswith("ref: refs/heads/") else None


def _checkout_of(common: Path, branch: str) -> Path | None:
    """The checkout that has `branch` checked out, read from git metadata files only."""
    if common.name == ".git" and _ref(common / "HEAD") == branch:
        return common.parent
    worktrees = common / "worktrees"
    if worktrees.is_dir():
        for entry in sorted(worktrees.iterdir()):
            if _ref(entry / "HEAD") == branch:
                try:
                    gitfile = Path((entry / "gitdir").read_text(encoding="utf-8").strip())
                except OSError:
                    continue
                return gitfile.parent
    return None


def detect(cwd: str | os.PathLike) -> Role | None:
    try:
        db = store.open_store(cwd)
    except store.StoreError:
        return None
    here = os.path.realpath(cwd)
    sessions = store.records(db, "session")
    for name, s in sorted(sessions.items()):
        if s.get("role") == "dev" and s.get("status") == "active" and s.get("worktree"):
            if _inside(here, os.path.realpath(s["worktree"])):
                return Role("dev", name, s.get("module"), db)
    coord = next((n for n, s in sorted(sessions.items())
                  if s.get("role") == "coordinator" and s.get("status") == "active"), None)
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch")
    if coord and branch:
        checkout = _checkout_of(db.path.parent, branch)
        if checkout is not None and _inside(here, os.path.realpath(checkout)):
            return Role("coordinator", coord, None, db)
    return None


def session_start(cwd: str | os.PathLike, source: str = "startup") -> str | None:
    return None


def prompt_line(cwd: str | os.PathLike) -> str | None:
    return None
