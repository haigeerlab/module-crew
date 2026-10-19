"""When things go wrong: suspend a module session, list the facts about each session, prepare a recovery kit,
fall back to serial (see spec/crew-failure.md). Nothing here judges whether a session has stopped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from module_crew import store, sync


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


@dataclass
class Changed:
    name: str
    sends: list[dict]        # {"to", "kind", "body", "path"}: bodies the coordinator sends unchanged


SUSPEND_TODO = ("停在当前停点，不构建、不发交审；挂起期间收到同步基线也先不动。"
                "在本 worktree 用 spec-guard 挂起（/spec-guard:module-suspend，原因照抄）")
RESUME_TODO = "在本 worktree 取消 spec-guard 的挂起，从原停点继续"


def _approval(tx, kind: str, module: str, original: str) -> int:
    """An answered item recording the user's words; suspend/resume notices cite it (contract v1.8)."""
    n = tx.allocate_number()
    tx.put("item", str(n), {"state": "closed", "kind": kind, "module": module, "closedReason": "answered",
                            "answer": {"original": original, "answeredAt": store.now(), **store.source_field()}},
           action="answered")
    return n


def _send(tx, db: store.Store, sends: list[dict], to: str, kind: str, text: str) -> None:
    n = tx.allocate_number()
    meta = tx.write_body(n, text)
    sends.append({"to": to, "kind": kind, "body": n, "path": str(db.path / meta["path"])})


def suspend(db: store.Store, module: str, reason: str, original: str) -> Changed:
    """Mark the module session as waiting on an outside condition; it stops counting against the limit."""
    from module_crew import protocol
    _need(original)
    if not reason or not reason.strip():
        raise FailureRefused("挂起原因不能为空")
    sends: list[dict] = []
    with db.transaction(actor="coordinator") as tx:
        name, rec = _dev_of(tx.records("session"), module)
        if rec.get("suspended"):
            raise FailureRefused(f"模块 {module} 已挂起（{rec['suspended'].get('reason')}）")
        n = _approval(tx, "suspend", module, original)
        mark = {"reason": reason.strip(), "at": store.now(), "original": original, "approval": n}
        tx.put("session", name, {**rec, "suspended": mark}, action="suspended")
        _send(tx, db, sends, name, "suspend", protocol.render_coordination_notice(
            kind="suspend", reason=reason.strip(), basis=f"用户批准事项 C{n}（挂起 {module}）", todo=SUSPEND_TODO))
    return Changed(name, sends)


def resume(db: store.Store, module: str, original: str) -> Changed:
    """Lift the suspension; the notice says to sync first when modules were merged meanwhile."""
    from module_crew import protocol
    _need(original)
    sends: list[dict] = []
    with db.transaction(actor="coordinator") as tx:
        name, rec = _dev_of(tx.records("session"), module)
        mark = rec.get("suspended")
        if not mark:
            raise FailureRefused(f"模块 {module} 没有挂起")
        n = _approval(tx, "resume", module, original)
        tx.put("session", name, {**rec, "suspended": None}, action="resumed", data={"original": original})
        log = store.events(db)
        since = max((e["seq"] for e in log if e["type"] == "session.suspended" and e["key"] == name), default=0)
        items = tx.records("item")
        merged = [(e["key"], items.get(e["key"]) or {}) for e in log if e["type"] == "item.merged" and e["seq"] > since]
        basis = f"用户批准事项 C{n}（恢复 {module}）" + (f"，挂起依据 C{mark['approval']}" if mark.get("approval") else "")
        todo = RESUME_TODO
        if merged:
            done = "、".join(f"{r.get('module')}（合并批准事项 C{k}，{(r.get('mergeCommit') or '')[:7]}）" for k, r in merged)
            todo = f"集成分支在挂起期间合入了 {done}：先{sync.STEP}、跑完整检查，再{RESUME_TODO}"
        _send(tx, db, sends, name, "resume", protocol.render_coordination_notice(kind="resume", basis=basis, todo=todo))
    return Changed(name, sends)


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


SESSIONS_SCHEMA = 1  # sessions --json export (spec/crew-hub-bridge.md): fields only ever added


def stage_code(text: str) -> str:
    """The export's stage enum, derived from the hook's stage sentence."""
    from module_crew import hooks
    if text == hooks.STAGE_WRITE:
        return "spec-plan"
    if text == hooks.STAGE_WAIT_MERGE:
        return "wait-merge"
    if text == hooks.STAGE_MERGED:
        return "merged"
    return "returned" if "上次最终验收被退回" in text else "build"


def sessions(db: store.Store, now: datetime | None = None) -> list[dict]:
    """Facts about each active module session; no thresholds, no verdicts."""
    from module_crew import hooks
    now = now or datetime.now().astimezone()
    events = store.events(db)
    items = store.records(db, "item")
    tickets = store.records(db, "ticket")
    from module_crew import review, stall
    stall.forget()
    nearby = review.progress(db)
    integration = (store.get(db, "config", "main") or {}).get("integrationBranch")
    rows = []
    for name, rec in sorted(store.records(db, "session").items()):
        if rec.get("role") != "dev" or rec.get("status") != "active":
            continue
        module = rec.get("module")
        last = next((e["at"] for e in reversed(events) if _related(e, name, module)), None)
        text = hooks._stage(items, module)
        rows.append({
            "name": name, "relayName": name, "module": module, "worktree": rec.get("worktree"), "host": rec.get("host"),
            "stage": stage_code(text), "stageText": text,
            "lastActivity": last, "ago": _ago(last, now) if last else None,
            "openTickets": sorted(int(k) for k, v in tickets.items() if v.get("from") == name and v.get("state") != "closed"),
            "openTicketRefs": [f"W{k}" for k in sorted(int(k) for k, v in tickets.items()
                                                       if v.get("from") == name and v.get("state") != "closed")],
            "openItems": sorted(int(k) for k, v in items.items()
                                if v.get("state") != "closed" and (v.get("from") == name or v.get("module") == module)),
            "suspended": (rec.get("suspended") or {}).get("reason"),
            "review": nearby.get(module),       # crew-review-nearby: rework visible to the decision inbox
            # crew-stall-signals: facts only, the decision inbox judges
            "startedAt": (started := stall.started_at(events, name)),
            "commits": stall.commit_facts(rec.get("worktree"), integration, started),
            "asks": stall.asks(events, items, module),
            "returns": stall.returns(events, items, module),
            "waitUser": stall.wait_user(events, items, name),
            "answers": stall.answers(items, module, name, rec.get("worktree"), integration, started),
        })
    return rows


def _commit_line(r: dict, now: datetime) -> str:
    """crew-stall-signals: the latest commit, as a fact."""
    c = r["commits"]
    if c["error"]:
        return f"  最近提交读不到：{c['error']}"
    if c["last"] is None:
        return "  最近提交：开工以来没有提交" + (f"（开工 {_ago(r['startedAt'], now)}）" if r["startedAt"] else "")
    at = datetime.fromisoformat(c["last"]["at"])
    return f"  最近提交：{at.strftime('%Y-%m-%d %H:%M')}（{_ago(c['last']['at'], now)}），未合入集成分支 {c['ahead']} 个"


def _asks_line(r: dict) -> str:
    from module_crew import review
    asked = "、".join(f"{review.NODE_NAME[a['node']]} {a['count']} 次（{'、'.join(a['refs'])}）" for a in r["asks"])
    return "  问过你：" + (asked or "无") + (f"；合并退回 {len(r['returns'])} 次" if r["returns"] else "")


def render_sessions(rows: list[dict], now: datetime | None = None) -> list[str]:
    if not rows:
        return ["没有在用的模块会话"]
    now = now or datetime.now().astimezone()
    lines = []
    for r in rows:
        lines.append(f"{r['module']}（{r['name']}）" + (f"　挂起：{r['suspended']}" if r["suspended"] else ""))
        lines.append(f"  最后动静：{r['lastActivity'] or '无记录'}" + (f"（{r['ago']}）" if r["ago"] else ""))
        lines.append("  未关等待记录：" + ("、".join(f"W{n}" for n in r["openTickets"]) or "无")
                     + "；未关事项：" + ("、".join(f"C{n}" for n in r["openItems"]) or "无"))
        lines.append(f"  当前：{r['stageText']}")
        lines += [_commit_line(r, now), _asks_line(r)]
    return lines


RECOVERY_NOTE = ("这是换会话后的恢复：上一个会话已经不在了，你在原 worktree 里接着做。"
                 "先请用户在模块协调里同意接管（模块协调运行 `module-crew takeover {name}`），"
                 "再用 agent-relay 的 bridge_register 以同一个名字 {name} 重新注册（wake: \"auto\"；提示名字被占用或已退役时按提示传接管／恢复参数），"
                 "然后跑 `module-crew status`、读自己未关的等待记录，以状态库为准，不按记忆重做。")


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
    context = hooks.session_start(rec["worktree"], "startup") or ""
    lines = [f"模块：{module}　邮箱名：{name}　worktree：{rec['worktree']}", "", context, "", RECOVERY_NOTE.format(name=name)]
    if rec.get("host") == "codex-desktop":
        from module_crew.start import codex_lines
        lines += codex_lines(name)
    text = "\n".join(lines) + "\n"
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
        if "crewDir" not in (cfg or {}):  # sources alone don't mean a module was ever opened
            raise FailureRefused("还没有开过模块（没有运行配置），不需要切换")
        if (cfg.get("mode") == "serial") == serial:
            raise FailureRefused("已经是串行模式" if serial else "已经是并行模式")
        tx.put("config", "main", {**cfg, "mode": "serial" if serial else None},
               action="serial" if serial else "parallel", data={"original": original})
