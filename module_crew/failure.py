"""When things go wrong: suspend a module session, list the facts about each session, prepare a recovery kit,
fall back to serial (see spec/crew-failure.md). Nothing here judges whether a session has stopped.
"""

from __future__ import annotations

from module_crew import store


class FailureRefused(Exception):
    """The operation cannot be done; nothing was written."""


def _dev_of(records: dict, module: str) -> tuple[str, dict]:
    for name, rec in sorted(records.items()):
        if rec.get("role") == "dev" and rec.get("status") == "active" and rec.get("module") == module:
            return name, rec
    raise FailureRefused(f"模块 {module} 没有在用的模块会话")


def _need(original: str | None) -> None:
    if not original or not original.strip():
        raise FailureRefused("用户原话不能为空：只记用户在本会话亲手输入的话")


def suspend(db: store.Store, module: str, reason: str, original: str) -> str:
    """Mark the module session as waiting on an outside condition; it stops counting against the limit."""
    _need(original)
    if not reason or not reason.strip():
        raise FailureRefused("挂起原因不能为空")
    with db.transaction(actor="coordinator") as tx:
        name, rec = _dev_of(tx.records("session"), module)
        if rec.get("suspended"):
            raise FailureRefused(f"模块 {module} 已挂起（{rec['suspended'].get('reason')}）")
        mark = {"reason": reason.strip(), "at": store.now(), "original": original}
        tx.put("session", name, {**rec, "suspended": mark}, action="suspended")
    return name


def resume(db: store.Store, module: str) -> str:
    with db.transaction(actor="coordinator") as tx:
        name, rec = _dev_of(tx.records("session"), module)
        if not rec.get("suspended"):
            raise FailureRefused(f"模块 {module} 没有挂起")
        tx.put("session", name, {**rec, "suspended": None}, action="resumed")
    return name
