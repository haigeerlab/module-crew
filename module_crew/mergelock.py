"""One merge at a time while `merge run` runs in the background (see spec/crew-background-checks.md).

`merge.lock` next to the store is held with flock by the running `merge run` for its whole life; the system lets it
go when that process ends, however it ends. What is running is written beside it in `merge-running.json`
(replaced atomically, never deleted — the store deletes nothing). Running but not locked means the process is gone:
that record is cleared only when the integration checkout is clean and no merge is half done.
"""

from __future__ import annotations

import fcntl
import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from module_crew import probe, store

LOCK = "merge.lock"
INFO = "merge-running.json"


@dataclass
class Lock:
    approval: int
    unit: str
    fd: int


@dataclass(frozen=True)
class Held:
    info: dict


def read(db: store.Store) -> dict | None:
    """What a merge recorded as running; None when nothing is."""
    try:
        info = json.loads((db.path / INFO).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {"running": True, "unreadable": True}
    return info if info.get("running") else None


def _write(db: store.Store, info: dict) -> None:
    store._atomic_write_bytes(db.path / INFO, json.dumps(info, ensure_ascii=False).encode("utf-8"))


def locked(db: store.Store) -> bool:
    """Whether some process holds the merge lock right now (read only: never creates the lock file)."""
    try:
        fd = os.open(db.path / LOCK, os.O_RDWR)
    except FileNotFoundError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def acquire(db: store.Store, approval: int, unit: str) -> Lock | Held:
    fd = os.open(db.path / LOCK, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return Held(read(db) or {})
    _write(db, {"running": True, "approval": approval, "unit": unit, "pid": os.getpid(), "host": socket.gethostname(),
                "startedAt": store.now()})
    return Lock(approval, unit, fd)


def release(db: store.Store, lock: Lock) -> None:
    if lock.fd < 0:
        return
    _write(db, {"running": False, "approval": lock.approval, "unit": lock.unit, "endedAt": store.now()})
    fcntl.flock(lock.fd, fcntl.LOCK_UN)
    os.close(lock.fd)
    lock.fd = -1


def stale(db: store.Store, info: dict) -> bool:
    """Recorded as running, but nobody holds the lock: the merge process is gone."""
    return bool(info) and not locked(db)


def minutes(info: dict) -> int | None:
    try:
        started = datetime.fromisoformat(str(info.get("startedAt")))
    except ValueError:
        return None
    return max(int((datetime.now(started.tzinfo) - started).total_seconds() // 60), 0)


def describe(info: dict) -> str:
    took = minutes(info)
    return (f"合并 C{info.get('approval')}（{info.get('unit') or '?'}）正在后台跑"
            + (f"（已跑 {took} 分钟）" if took is not None else ""))


def guard(db: store.Store, project: str | os.PathLike) -> tuple[str | None, str | None]:
    """(reason to refuse, note) for a command about to write the integration checkout."""
    info = read(db)
    if info is None and not locked(db):
        return None, None
    if info is None or info.get("unreadable"):
        return f"合并锁被占着，但记录读不出（{db.path / INFO}）：等它结束，或请用户核对", None
    if not stale(db, info):
        return describe(info) + "，等它结束再做", None
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch")
    checkout = probe._checkout_of(Path(project), branch) if branch else None
    if checkout is None:
        return "合并锁已失效（合并进程不在了），但找不到集成 checkout：请用户核对", None
    gitdir = probe._git(checkout, "rev-parse", "--git-dir").stdout.strip()
    mid = (Path(checkout) / gitdir / "MERGE_HEAD").exists() if gitdir else False
    dirty = bool(probe._git(checkout, "status", "--porcelain").stdout.strip())
    if mid or dirty:
        return (f"合并锁已失效（C{info.get('approval')} 的合并进程不在了），集成 checkout {checkout} "
                + ("有做到一半的合并" if mid else "不干净") + "：没有清锁，请用户核对"), None
    _write(db, {**info, "running": False, "clearedAt": store.now(), "cleared": "stale"})
    return None, f"合并锁已失效（C{info.get('approval')} 的合并进程不在了），集成 checkout 干净，已清掉"
