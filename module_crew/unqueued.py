"""Commits on the integration branch that did not come through module-crew (see spec/crew-unqueued-commits.md).

module-crew remembers the last integration-branch head it knows (`integrationSeen`): set when the coordinator is
upgraded or the first modules start, moved after each of its own commits there. Anything after it on the first-parent
line was committed some other way: the user is told once and the modules are asked to sync, nothing is blocked.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from module_crew import probe, store


def seen(db: store.Store) -> str | None:
    return (store.get(db, "config", "main") or {}).get("integrationSeen")


def _head(checkout: Path) -> str | None:
    out = probe._git(checkout, "rev-parse", "HEAD")
    return out.stdout.strip() or None if out.returncode == 0 else None


def mark(db: store.Store, checkout: str | os.PathLike, source: str, only_if_unset: bool = False) -> str | None:
    """Remember the checkout's HEAD as the head module-crew knows; returns it (None when unreadable)."""
    new = _head(Path(checkout))
    if new is None:
        return None
    with db.transaction(actor="coordinator") as tx:
        cfg = tx.get("config", "main") or {}
        old = cfg.get("integrationSeen")
        if (only_if_unset and old) or old == new:
            return old
        tx.put("config", "main", {**cfg, "integrationSeen": new}, action="integration-seen",
               data={"old": old, "new": new, "by": source})   # not "source": that key is the approval source
    return new


def mark_integration(db: store.Store, project: str | os.PathLike, source: str, only_if_unset: bool = False) -> str | None:
    """mark() on the checkout that has the integration branch checked out."""
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch")
    checkout = probe._checkout_of(Path(project), branch) if branch else None
    return mark(db, checkout, source, only_if_unset) if checkout else None


@dataclass
class Found:
    seen: str | None
    head: str | None
    commits: list[dict] = field(default_factory=list)     # newest first: commit, short, author, at, subject
    missing_seen: bool = False                             # an older project: nothing remembered yet
    not_in_history: bool = False                           # the remembered head is no longer on the branch


def _iso(text: str) -> str:
    text = text.strip()
    return text[:-1] + "+00:00" if text.endswith("Z") else text


def find(db: store.Store, project: str | os.PathLike) -> Found:
    """Read-only: commits after the remembered head on the integration branch's first-parent line."""
    project = Path(project)
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch")
    known = seen(db)
    tip = probe._git(project, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").stdout.strip() if branch else ""
    found = Found(known, tip or None)
    if not tip:
        return found
    if not known:
        found.missing_seen = True
        return found
    if probe._git(project, "merge-base", "--is-ancestor", known, tip).returncode != 0:
        found.not_in_history = True
        ids = [tip]
    else:
        ids = probe._git(project, "rev-list", "--first-parent", f"{known}..{tip}").stdout.split()
    if ids:
        log = probe._git(project, "log", "--no-walk=unsorted", "--format=%H%x00%h%x00%an%x00%cI%x00%s", *ids)
        for line in log.stdout.splitlines():
            c, short, author, at, subject = (line.split("\0") + [""] * 5)[:5]
            found.commits.append({"commit": c, "short": short, "author": author, "at": _iso(at), "subject": subject})
    return found


def describe(found: Found) -> str:
    """One line for people: how many, from which to which."""
    if not found.commits:
        return "集成分支上没有不经合并队列的提交"
    span = found.commits[-1]["short"] + ("～" + found.commits[0]["short"] if len(found.commits) > 1 else "")
    return f"集成分支上有 {len(found.commits)} 个不经合并队列的提交（{span}）"


def notify(db: store.Store, project: str | os.PathLike) -> list[dict]:
    """Sync-baseline notices for in-use modules and working tasks (merge's skip rules), then move the remembered head."""
    from module_crew import merge, sync
    found = find(db, project)
    if found.missing_seen:
        mark_integration(db, project, "unqueued")
        return []
    if not found.commits:
        return []
    basis = describe(found) + "；module-crew 没有经手，请照常同步"
    result = merge.RunResult(0)
    with db.transaction(actor="coordinator") as tx:
        for name, task in merge.sync_targets(tx):
            merge._notice(tx, db, result, name, "sync-baseline", basis=basis, todo=f"{sync.STEP}，跑完整检查后继续",
                          task=task)
    mark_integration(db, project, "unqueued")
    return result.sends
