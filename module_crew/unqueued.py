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
               data={"old": old, "new": new, "source": source})
    return new


def mark_integration(db: store.Store, project: str | os.PathLike, source: str, only_if_unset: bool = False) -> str | None:
    """mark() on the checkout that has the integration branch checked out."""
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch")
    checkout = probe._checkout_of(Path(project), branch) if branch else None
    return mark(db, checkout, source, only_if_unset) if checkout else None
