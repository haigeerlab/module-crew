"""Read spec-guard's checkout role marker (interface 1.1 checkoutRole.marker) with plain file reads.

The marker is the file at `git rev-parse --git-path spec-guard/role` of a checkout: inside that checkout's own
git directory, so each worktree has its own.  Only one line `module <id>` or `coordinator` is valid.
No subprocess here: the hooks import this module.
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

MARKER = Path("spec-guard") / "role"
MAX_BYTES = 256
LINE = re.compile(r"^(?:module ([a-z0-9]+(?:-[a-z0-9]+)*)|(coordinator))$")


def checkout_root(cwd: str | os.PathLike) -> Path | None:
    """The nearest directory at or above `cwd` that holds a `.git` directory or file."""
    here = Path(os.path.realpath(cwd))
    for d in (here, *here.parents):
        if os.path.lexists(d / ".git"):
            return d
    return None


def git_dir(root: Path) -> Path | None:
    dot = root / ".git"
    if dot.is_dir() and not dot.is_symlink():
        return dot
    try:
        text = dot.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    if not text.startswith("gitdir:"):
        return None
    path = Path(text[len("gitdir:"):].strip())
    return path if path.is_absolute() else (root / path).resolve()


def marker_path(root: Path) -> Path | None:
    gd = git_dir(root)
    return gd / MARKER if gd else None


def read(root: Path) -> tuple[str, str | None]:
    """("none"|"invalid"|"module"|"coordinator", module id or None) for the checkout at `root`."""
    path = marker_path(root)
    if path is None:
        return "none", None
    if path.parent.is_symlink() or (os.path.lexists(path.parent) and not path.parent.is_dir()):
        return "invalid", None
    if not os.path.lexists(path):
        return "none", None
    try:
        if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
            return "invalid", None
        raw = path.read_bytes()[:MAX_BYTES + 1]
        lines = raw.decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return "invalid", None
    match = LINE.match(lines[0]) if len(raw) <= MAX_BYTES and len(lines) == 1 else None
    if match is None:
        return "invalid", None
    return ("module", match.group(1)) if match.group(1) else ("coordinator", None)
