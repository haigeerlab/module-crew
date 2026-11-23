"""spec-guard flow v2 (S110, interface 1.18): requirement -> design (with regression) -> build -> final acceptance by the
regression cases, the Plan never reviewed. One place decides whether a module follows it and what that changes for
reviews, starting and display (see spec/crew-flow-v2.md). A module without a tier is an old module, unchanged."""

from __future__ import annotations

import os
from pathlib import Path

from module_crew import store

TIERS = ("bug", "small", "normal", "important")
STEP_WORDS = {"design": "写技术方案", "regression": "写回归"}


def tier_of(row: dict | None) -> str | None:
    """Decision 1: the tier /map --json gives the module (interface 1.18); None for an old module or an older spec-guard.
    spec-guard already reads an unknown tier as normal; a stray non-empty value is read the same way here."""
    value = (row or {}).get("tier") if isinstance(row, dict) else None
    if value is None or value == "":
        return None
    return value if value in TIERS else "normal"


def row_of(map_doc: dict | str | None, module_id: str) -> dict | None:
    if not isinstance(map_doc, dict):
        return None
    return next((m for m in map_doc.get("modules") or [] if isinstance(m, dict) and m.get("id") == module_id), None)


def _map(db: store.Store, project: str | os.PathLike) -> dict | str:
    from module_crew import takeover
    return takeover._map(takeover.checkout(db, project))


def tier(db: store.Store, project: str | os.PathLike, module_id: str, map_doc: dict | None = None) -> str | None:
    """The module's flow v2 tier, read from the integration checkout's /map --json; None when unreadable (old flow)."""
    doc = map_doc if map_doc is not None else _map(db, Path(project))
    return tier_of(row_of(doc, module_id))


def is_v2(tier_value: str | None) -> bool:
    return tier_value is not None


def full_docs(tier_value: str | None) -> bool:
    """normal and important write the design and the regression document; bug and small one document."""
    return tier_value in ("normal", "important")


def step_word(row: dict | None) -> str | None:
    """The document step a flow v2 module is on (/map step design or regression), for display."""
    return STEP_WORDS.get((row or {}).get("step")) if isinstance(row, dict) else None


def summarize(map_doc: dict | None) -> dict[str, str]:
    """module id -> tier for every flow v2 module in the map (probe / status)."""
    return {m["id"]: t for m in (map_doc or {}).get("modules") or []
            if isinstance(m, dict) and isinstance(m.get("id"), str) and (t := tier_of(m)) is not None}
