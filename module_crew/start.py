"""Expansion point: propose which modules to open, then prepare worktrees, registrations and kickoffs
(see spec/crew-start.md). Opening the sessions themselves is done by the coordinator with the desktop tools.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from module_crew import probe, store

DEFAULT_MAX = 3


@dataclass
class Proposal:
    slots: int
    modules: list[dict] = field(default_factory=list)      # {"id", "responsibility", "dependsOn"}
    conflicts: list[dict] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


def _open_store(project: Path) -> store.Store | None:
    try:
        return store.open_store(project)
    except store.StoreNotFound:
        return None


def _config(db: store.Store | None) -> dict:
    return (store.get(db, "config", "main") or {}) if db else {}


def _active_devs(db: store.Store | None) -> dict[str, dict]:
    if db is None:
        return {}
    return {k: v for k, v in store.records(db, "session").items()
            if v.get("role") == "dev" and v.get("status") == "active"}


def plan(project: str | os.PathLike, max_modules: int | None = None) -> Proposal:
    """Read-only: free slots and the first startable modules in Build order."""
    project = Path(project)
    report = probe.run(project)
    db = _open_store(project)
    limit = _config(db).get("maxModules") or max_modules or DEFAULT_MAX
    slots = max(limit - len(_active_devs(db)), 0)
    blockers = [f"{c.id}：{c.reason}" for c in report.checks.values() if c.state == "blocker"]
    if blockers:
        return Proposal(slots, blockers=blockers)
    modules = {m.get("id"): m for m in report.map.get("modules") or [] if isinstance(m, dict)}
    picked = [{"id": mid, "responsibility": modules.get(mid, {}).get("responsibility", ""),
               "dependsOn": list(modules.get(mid, {}).get("dependsOn") or [])}
              for mid in (report.startable or {}).get("modules", [])][:slots]
    return Proposal(slots, picked, list((report.startable or {}).get("conflicts", [])))
