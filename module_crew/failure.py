"""When things go wrong: suspend a module session, list the facts about each session, prepare a recovery kit,
fall back to serial (see spec/crew-failure.md). Nothing here judges whether a session has stopped.
"""

from __future__ import annotations

from dataclasses import dataclass
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


RECOVERY_NOTE = ("这是换会话后的恢复：上一个会话已经不在了，你在原 worktree 里接着做。"
                 "先请用户在协调会话里同意接管（协调会话运行 `module-crew takeover {name}`），"
                 "再用 agent-relay 的 bridge_register 以同一个名字 {name} 重新注册（wake: \"auto\"；提示名字被占用或已退役时按提示传接管／恢复参数），"
                 "然后跑 `module-crew status`、读自己未关的等待单，以状态库为准，不按记忆重做。")


@dataclass(frozen=True)
class Kit:
    name: str
    module: str
    worktree: str
    body: int
    path: str


def resume_kit(db: store.Store, module: str) -> Kit:
    """Store the first message for a new conversation that takes over `module` in its original worktree."""
    from module_crew import hooks
    name, rec = _dev_of(store.records(db, "session"), module)
    context = hooks.session_start(rec["worktree"], "compact") or ""
    text = "\n".join([f"模块：{module}　邮箱名：{name}　worktree：{rec['worktree']}", "", context, "",
                      RECOVERY_NOTE.format(name=name)]) + "\n"
    with db.transaction(actor="coordinator") as tx:
        n = tx.allocate_number()
        tx.write_body(n, text)
    return Kit(name, module, rec["worktree"], n, str(db.path / "bodies" / f"{n}.txt"))


SERIAL_BLOCKER = "已退回串行：不再开新模块，已开的模块照常推进（用户说恢复并行后运行 serial --off）"


def set_mode(db: store.Store, serial: bool, original: str) -> None:
    """Fall back to serial (no new modules) or back to parallel; both need the user's own words."""
    _need(original)
    with db.transaction(actor="coordinator") as tx:
        cfg = tx.get("config", "main")
        if not cfg:
            raise FailureRefused("还没有开过模块（没有运行配置），不需要切换")
        if (cfg.get("mode") == "serial") == serial:
            raise FailureRefused("已经是串行模式" if serial else "已经是并行模式")
        tx.put("config", "main", {**cfg, "mode": "serial" if serial else None},
               action="serial" if serial else "parallel", data={"original": original})
