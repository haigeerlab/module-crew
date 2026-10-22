"""One merge at a time while `merge run` runs in the background (see spec/crew-background-checks.md).

The lock is a file next to the store (`merge.lock`), created with O_EXCL so only one process can hold it.
Writing commands check it first; a lock whose process is gone on this machine is stale and is cleared only when
the integration checkout is clean and no merge is half done.
"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from module_crew import probe, store

NAME = "merge.lock"


@dataclass(frozen=True)
class Lock:
    approval: int
    unit: str
    pid: int
    started_at: str


@dataclass(frozen=True)
class Held:
    info: dict


def _path(db: store.Store) -> Path:
    return db.path / NAME


def read(db: store.Store) -> dict | None:
    try:
        return json.loads(_path(db).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {"unreadable": True}


def acquire(db: store.Store, approval: int, unit: str) -> Lock | Held:
    lock = Lock(approval, unit, os.getpid(), store.now())
    info = {"approval": approval, "unit": unit, "pid": lock.pid, "host": socket.gethostname(), "startedAt": lock.started_at}
    try:
        fd = os.open(_path(db), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return Held(read(db) or {})
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False)
    return lock


def release(db: store.Store, lock: Lock) -> None:
    """Remove the lock only when it is still the one this call took."""
    info = read(db)
    if info and info.get("pid") == lock.pid and info.get("startedAt") == lock.started_at:
        try:
            _path(db).unlink()
        except FileNotFoundError:
            pass


def stale(info: dict) -> bool:
    if info.get("host") != socket.gethostname() or not isinstance(info.get("pid"), int):
        return False
    try:
        os.kill(info["pid"], 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def minutes(info: dict) -> int | None:
    try:
        started = datetime.fromisoformat(str(info.get("startedAt")))
    except ValueError:
        return None
    return max(int((datetime.now(started.tzinfo) - started).total_seconds() // 60), 0)


def describe(info: dict) -> str:
    unit = info.get("unit") or "?"
    took = minutes(info)
    return f"合并 C{info.get('approval')}（{unit}）正在后台跑" + (f"（已跑 {took} 分钟）" if took is not None else "")


def guard(db: store.Store, project: str | os.PathLike) -> tuple[str | None, str | None]:
    """(reason to refuse, note) for a command about to write the integration checkout."""
    info = read(db)
    if info is None:
        return None, None
    if info.get("unreadable"):
        return f"合并锁 {_path(db)} 读不出：请用户核对后删除它", None
    if not stale(info):
        if info.get("host") != socket.gethostname():
            return f"合并锁是另一台机器（{info.get('host')}）留下的：{describe(info)}；请用户核对", None
        return describe(info) + "，等它结束再做", None
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch")
    checkout = probe._checkout_of(Path(project), branch) if branch else None
    if checkout is None:
        return "合并锁已失效（进程不在了），但找不到集成 checkout：请用户核对", None
    gitdir = probe._git(checkout, "rev-parse", "--git-dir").stdout.strip()
    mid = (Path(checkout) / gitdir / "MERGE_HEAD").exists() if gitdir else False
    dirty = bool(probe._git(checkout, "status", "--porcelain").stdout.strip())
    if mid or dirty:
        return (f"合并锁已失效（C{info.get('approval')} 的进程不在了），集成 checkout {checkout} "
                + ("有做到一半的合并" if mid else "不干净") + "：没有清锁，请用户核对"), None
    try:
        _path(db).unlink()
    except FileNotFoundError:
        pass
    return None, f"合并锁已失效（C{info.get('approval')} 的进程不在了），集成 checkout 干净，已清掉"
