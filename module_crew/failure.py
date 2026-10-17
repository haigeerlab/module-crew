"""When things go wrong: suspend a module session, list the facts about each session, prepare a recovery kit,
fall back to serial (see spec/crew-failure.md). Nothing here judges whether a session has stopped.
"""

from __future__ import annotations

from datetime import datetime

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


def _related(event: dict, name: str, module: str) -> bool:
    if event.get("actor") == name:
        return True
    kind = event["type"].split(".")[0]
    if kind == "session":
        return event["key"] == name
    if kind not in ("item", "request", "ticket"):
        return False
    rec = (event.get("data") or {}).get("record") or {}
    return name in (rec.get("from"), rec.get("to")) or rec.get("module") == module


def _ago(at: str, now: datetime) -> str:
    minutes = max(int((now - datetime.fromisoformat(at)).total_seconds() // 60), 0)
    if minutes < 60:
        return f"{minutes} 分钟前"
    if minutes < 60 * 24:
        return f"{minutes // 60} 小时前"
    return f"{minutes // (60 * 24)} 天前"


def sessions(db: store.Store, now: datetime | None = None) -> list[dict]:
    """Facts about each active module session; no thresholds, no verdicts."""
    from module_crew import hooks
    now = now or datetime.now().astimezone()
    events = store.events(db)
    items = store.records(db, "item")
    tickets = store.records(db, "ticket")
    rows = []
    for name, rec in sorted(store.records(db, "session").items()):
        if rec.get("role") != "dev" or rec.get("status") != "active":
            continue
        module = rec.get("module")
        last = next((e["at"] for e in reversed(events) if _related(e, name, module)), None)
        rows.append({
            "name": name, "module": module, "worktree": rec.get("worktree"),
            "lastActivity": last, "ago": _ago(last, now) if last else None,
            "openTickets": sorted(int(k) for k, v in tickets.items() if v.get("from") == name and v.get("state") != "closed"),
            "openItems": sorted(int(k) for k, v in items.items()
                                if v.get("state") != "closed" and (v.get("from") == name or v.get("module") == module)),
            "stage": hooks._stage(items, module),
            "suspended": (rec.get("suspended") or {}).get("reason"),
        })
    return rows


def render_sessions(rows: list[dict]) -> list[str]:
    if not rows:
        return ["没有在用的模块会话"]
    lines = []
    for r in rows:
        lines.append(f"{r['module']}（{r['name']}）" + (f"　挂起：{r['suspended']}" if r["suspended"] else ""))
        lines.append(f"  最后动静：{r['lastActivity'] or '无记录'}" + (f"（{r['ago']}）" if r["ago"] else ""))
        lines.append("  未关等待单：" + ("、".join(f"#{n}" for n in r["openTickets"]) or "无")
                     + "；未关事项：" + ("、".join(f"#{n}" for n in r["openItems"]) or "无"))
        lines.append(f"  当前：{r['stage']}")
    return lines
