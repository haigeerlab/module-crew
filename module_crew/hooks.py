"""Role-aware context for SessionStart / UserPromptSubmit hooks, and takeover (see spec/crew-recovery-hooks.md).

Read-only and fast: only the store and git metadata files are read; no probe, no /map.
Anything unexpected means "not a module-crew session" and the hook stays silent.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from module_crew import role as marker
from module_crew import store


@dataclass(frozen=True)
class Role:
    kind: str                     # dev / coordinator / task
    name: str                     # relay name
    module: str | None
    db: store.Store
    task: int | None = None       # crew-light-task: the task number of a task session


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _ref(head_file: Path) -> str | None:
    try:
        text = head_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text[len("ref: refs/heads/"):] if text.startswith("ref: refs/heads/") else None


def _checkout_of(common: Path, branch: str) -> Path | None:
    """The checkout that has `branch` checked out, read from git metadata files only."""
    if common.name == ".git" and _ref(common / "HEAD") == branch:
        return common.parent
    worktrees = common / "worktrees"
    if worktrees.is_dir():
        for entry in sorted(worktrees.iterdir()):
            if _ref(entry / "HEAD") == branch:
                try:
                    gitfile = Path((entry / "gitdir").read_text(encoding="utf-8").strip())
                except OSError:
                    continue
                return gitfile.parent
    return None


def detect(cwd: str | os.PathLike) -> Role | None:
    try:
        db = store.open_store(cwd)
    except store.StoreError:
        return None
    here = os.path.realpath(cwd)
    sessions = store.records(db, "session")
    root = marker.checkout_root(here)
    kind, module = marker.read(root) if root else ("none", None)
    if kind == "module":  # spec-guard's checkout role marker wins over the registered path
        name = next((n for n, s in sorted(sessions.items()) if s.get("role") == "dev"
                     and s.get("status") == "active" and s.get("module") == module), None)
        return Role("dev", name, module, db) if name else None
    if kind == "coordinator":
        name = next((n for n, s in sorted(sessions.items())
                     if s.get("role") == "coordinator" and s.get("status") == "active"), None)
        return Role("coordinator", name, None, db) if name else None
    for name, s in sorted(sessions.items()):            # crew-light-task: a light task's own worktree
        if s.get("role") == "task" and s.get("status") == "active" and s.get("worktree"):
            if _inside(here, os.path.realpath(s["worktree"])):
                return Role("task", name, None, db, s.get("task"))
    for name, s in sorted(sessions.items()):
        if s.get("role") == "dev" and s.get("status") == "active" and s.get("worktree"):
            if _inside(here, os.path.realpath(s["worktree"])):
                return Role("dev", name, s.get("module"), db)
    coord = next((n for n, s in sorted(sessions.items())
                  if s.get("role") == "coordinator" and s.get("status") == "active"), None)
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch")
    if coord and branch:
        checkout = _checkout_of(db.path.parent, branch)
        if checkout is not None and _inside(here, os.path.realpath(checkout)):
            return Role("coordinator", coord, None, db)
    return None


def integration_checkout(cwd: str | os.PathLike) -> Path | None:
    """The checkout that has the project's integration branch checked out, or None."""
    try:
        db = store.open_store(cwd)
    except store.StoreError:
        return None
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch")
    return _checkout_of(db.path.parent, branch) if branch else None


def stray_worktree(cwd: str | os.PathLike) -> tuple[Path, Path] | None:
    """S40: (this checkout, the integration checkout) when cwd is a git worktree of the project that is neither the
    integration checkout nor a registered module or task worktree, e.g. one the desktop app made for a new session."""
    checkout = integration_checkout(cwd)
    root = marker.checkout_root(cwd)
    if checkout is None or root is None or os.path.realpath(root) == os.path.realpath(checkout):
        return None
    role = detect(cwd)
    if role is not None and role.kind in ("dev", "task"):
        return None
    return Path(root), Path(checkout)


def stray_worktree_line(cwd: str | os.PathLike) -> str | None:
    found = stray_worktree(cwd)
    if found is None:
        return None
    return f"本会话在 worktree {found[0]} 里，模块协调要在集成 checkout {found[1]} 运行命令、提交"


CLEAR_NOTE = "刚清空过：先跑 `module-crew status`、读未完成的事项，以状态库为准，不按清空前的印象重做已经做过的事。"
HOOK_WAIT = 2.0          # seconds a hook may wait for the store lock before staying silent
CLEAR_WINDOW = 30        # SessionStart(clear) must follow SessionEnd(clear) within this many seconds
HANDOVER_TTL = 300       # an unclaimed CLI handover is void after this many seconds
DESKTOP_TTL = 7 * 24 * 3600   # the desktop app restarts a cleared session only on its next message
REMINDER = ("提醒：这个项目已有模块协调（{where}），派活、并行和合入一般由它统一安排。你在这里直接改也可以，"
            "只是这些改动不经它的合并队列，正在开发的模块要等它发现后才会收到同步通知。"
            "要交给模块协调的话，告诉我，我把要做的事整理成一段话，你贴给它就行。")
REMINDER_ASK = "（module-crew：请在你第一次回复用户时顺带说一次上面这段提醒，不要停下来问，之后照用户的意思做、不再重复。）"
COMPACT_NOTE = "刚压缩过：先跑 `module-crew status`、读未完成的事项，以状态库为准，不按压缩前的记忆重做已经做过的事。"
STAGE_WRITE = "写 Spec 与 Plan、发【交审】，收到开工通知之前不要构建"
STAGE_BUILD = "Spec 与 Plan 已批准，可以构建；做完发最终验收【交审】"
STAGE_WAIT_MERGE = "最终验收已批准，等模块协调合并"
STAGE_WAIT_FINAL = "最终验收已交审（交审事项 C{n}），等用户批准；不要重做或重发"
STAGE_ACCEPTED = "最终验收已接受（交审事项 C{n}），用户暂未授权合并：停在当前停点，不要再提交，等授权合并或退回"
STAGE_MERGED = "已合入集成分支，停止开发，等模块协调收回 worktree"


def _stage(items: dict, module: str, sessions: dict | None = None) -> str:
    """With `sessions`, a reopened module only counts this round (crew-reopen-module decision 4)."""
    items = store.round_items(items, sessions, module)
    reopen = store.reopen_of(sessions or {}, module) or {}
    approved = {"spec", "plan"} if reopen.get("review") == {"spec": "approved", "plan": "approved"} else set()
    for rec in items.values():
        if rec.get("kind") == "review-approval":
            for n in rec.get("reviews", []):
                r = items.get(str(n)) or {}
                if r.get("module") == module:
                    approved.add(r.get("node"))
    merges = sorted(((int(k), v) for k, v in items.items()
                     if v.get("kind") == "merge-approval" and v.get("module") == module), key=lambda kv: kv[0])
    if any(v.get("closedReason") == "merged" for _, v in merges):
        return STAGE_MERGED
    if any(v.get("state") == "open" for _, v in merges):
        return STAGE_WAIT_MERGE
    accepted = sorted(int(k) for k, v in items.items() if v.get("kind") == "review" and v.get("module") == module
                      and v.get("node") == "final" and v.get("state") == "accepted")
    if accepted:                                      # crew-final-accept-split
        return STAGE_ACCEPTED.format(n=accepted[-1])
    final = sorted(int(k) for k, v in items.items() if v.get("kind") == "review" and v.get("module") == module
                   and v.get("node") == "final" and v.get("state") == "open")
    if final:
        return STAGE_WAIT_FINAL.format(n=final[-1])
    if {"spec", "plan"} <= approved:
        last = merges[-1][1] if merges else None
        if last and last.get("closedReason") == "returned":
            return f"{STAGE_BUILD}（上次最终验收被退回：{(last.get('reason') or '').splitlines()[0]}）"
        return STAGE_BUILD
    return STAGE_WRITE


def _counts(db: store.Store) -> dict[str, int]:
    items = store.records(db, "item")
    return {
        "事项": sum(1 for v in items.values() if v.get("state") != "closed" and v.get("kind") != "merge-approval"),
        "请求": sum(1 for v in store.records(db, "request").values() if v.get("state") != "closed"),
        "等待记录": sum(1 for v in store.records(db, "ticket").values() if v.get("state") != "closed"),
        "待合并": sum(1 for v in items.values() if v.get("kind") == "merge-approval" and v.get("state") == "open"),
    }


def _count_text(c: dict[str, int]) -> str:
    return "未关 " + "／".join(f"{k} {n}" for k, n in c.items())


def _coordinator_name(db: store.Store) -> str:
    return next((n for n, s in sorted(store.records(db, "session").items())
                 if s.get("role") == "coordinator" and s.get("status") == "active"), "（没有在用的模块协调）")


# crew-recovery-hooks decision 7: kickoff texts point at the hook's line instead of naming a path
ENTRY_LINE = "命令入口：以本会话 module-crew 钩子注入的「module-crew 命令入口」那一行为准，不沿用别的会话给的带版本号路径。"
PLUGIN_ROOT = Path(__file__).resolve().parents[1]     # the plugin copy the host ran this hook from


def command_entry(db: store.Store) -> str:
    """crew-recovery-hooks decision 7: the command this session should use. The store's fixed launcher when it is
    there (crew-command-entry decision 6; same place as launcher.entry, which this module must not import), else the
    plugin that ran the hook. Reads only."""
    try:
        version = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError, TypeError):
        version = None
    fixed = Path(db.path) / "bin" / "module-crew"
    if os.access(fixed, os.X_OK):
        return (f"module-crew 命令入口：`{fixed}`（固定入口，转到本机当前安装的 module-crew；"
                f"本次钩子来自{f'版本 {version}' if version else '未知版本'}）；用这一行，不用记忆、开工背景或别的会话给的路径")
    return (f"module-crew 命令入口：`{PLUGIN_ROOT / 'bin' / 'module-crew'}`（{f'版本 {version}' if version else '版本未知'}）；"
            "用这一行，不用记忆、开工背景或别的会话给的路径；还没有固定入口，"
            "跑一次 `module-crew permissions apply` 或 `module-crew coordinator up` 写出后，升级就不用换路径")


def session_start(cwd: str | os.PathLike, source: str = "startup", role: Role | None = None) -> str | None:
    role = role or detect(cwd)
    if role is None:
        return None
    if role.kind == "task":
        t = store.get(role.db, "task", str(role.task)) or {}
        lines = [f"module-crew：你是轻任务 T{role.task} 的会话（邮箱名 {role.name}），模块协调是 {_coordinator_name(role.db)}，你只和它说话。",
                 "按 crew-dev skill 的「轻任务」一节做：只做任务单里的事，测试全过才交回，做大了就停下发升格请求。",
                 f"任务单：{t.get('what', '?')}；预计文件：{'、'.join(t.get('expectedFiles') or [])}；完成标准：{t.get('done', '?')}",
                 f"当前：{_task_stage(t)}"]
    elif role.kind == "dev":
        tickets = sorted(int(k) for k, v in store.records(role.db, "ticket").items()
                         if v.get("from") == role.name and v.get("state") == "open")
        lines = [f"module-crew：你是模块 {role.module} 的模块会话（邮箱名 {role.name}），模块协调是 {_coordinator_name(role.db)}，你只和它说话。",
                 "按 crew-dev skill 的规则做；被挡住必须发【等待其他会话】；发出前 module-crew protocol check。",
                 f"当前：{_stage(store.records(role.db, 'item'), role.module, store.records(role.db, 'session'))}",
                 "未关的等待记录：" + ("、".join(f"W{n}" for n in tickets) or "无")]
    else:
        lines = [f"module-crew：本会话是模块协调（{role.name}）。{_count_text(_counts(role.db))}。",
                 "先跑 `module-crew status` 再动手；看 agent-relay 在线状态里谁处于「等待审批」，提醒用户去那个会话点权限弹窗。",
                 "按 crew-coordinator skill 的规则做：只统筹不开发，只转达用户在本会话亲手输入的话。"]
    lines.append(command_entry(role.db))
    if source == "compact":
        lines.append(COMPACT_NOTE)
    elif source == "clear":
        lines.append(CLEAR_NOTE)
    return "\n".join(lines)


def _task_stage(t: dict) -> str:
    from module_crew.tasks import STATE_NAMES
    return STATE_NAMES.get(t.get("state"), t.get("state") or "?")


def prompt_line(cwd: str | os.PathLike, role: Role | None = None) -> str | None:
    role = role or detect(cwd)
    if role is None:
        return None
    if role.kind == "task":
        return f"module-crew：你是轻任务 T{role.task} 的会话（{role.name}），当前：{_task_stage(store.get(role.db, 'task', str(role.task)) or {})}"
    if role.kind == "dev":
        stage = _stage(store.records(role.db, "item"), role.module, store.records(role.db, "session")).split("，")[0].split("（")[0]
        return f"module-crew：你是 {role.module} 的模块会话（{role.name}），当前：{stage}"
    return f"module-crew：模块协调；{_count_text(_counts(role.db))}"


def registration_of(db: store.Store, session_id: str | None) -> tuple[str, dict] | None:
    """crew-session-handover decision 1: the registration in use that this conversation is bound to, wherever it runs."""
    if not session_id:
        return None
    return next(((n, s) for n, s in sorted(store.records(db, "session").items())
                 if s.get("status") == "active" and (s.get("hostSession") or {}).get("sessionId") == session_id), None)


def superseded(db: store.Store, session_id: str | None) -> str | None:
    """The registration this conversation used to be, before another conversation took it over (crew-session-handover)."""
    if not session_id:
        return None
    return next((n for n, s in sorted(store.records(db, "session").items()) if s.get("status") == "active"
                 and any(p.get("sessionId") == session_id for p in s.get("previousSessions") or [])), None)


def role_of(db: store.Store, name: str, rec: dict) -> Role:
    kind = rec.get("role")
    return Role(kind, name, rec.get("module") if kind == "dev" else None, db, rec.get("task") if kind == "task" else None)


def elsewhere_line(db: store.Store, name: str, rec: dict, cwd: str | os.PathLike) -> str | None:
    """One line when a registered conversation runs outside its registered directory (desktop sessions bring their own)."""
    home = _home_of(db, rec)
    here = os.path.realpath(cwd)
    if home is None or _inside(here, str(home)):
        return None
    return (f"module-crew：本会话在 {here}，{name} 登记的目录是 {home}：module-crew 命令在本仓库任一目录都能运行，"
            "改文件的事到登记目录做。")


def matches(role: Role, session_id: str | None) -> bool:
    """Whether the conversation the hook runs for is the one bound to this registration (crew-routing-fixes)."""
    bound = ((store.get(role.db, "session", role.name) or {}).get("hostSession") or {}).get("sessionId")
    return bool(bound) and bound == session_id


def stranger_line(role: Role) -> str:
    """The one line for any other conversation in a registered directory: whose it is, and that it is not you."""
    if role.kind == "task":
        return (f"module-crew：本目录属于轻任务 T{role.task}（登记会话 {role.name}）；你不是它的登记会话，不要按轻任务会话行事。"
                f"如果你刚收到这个任务的开工说明，先按说明运行 module-crew bind {role.name}。")
    if role.kind == "dev":
        return (f"module-crew：本目录属于模块 {role.module}（登记会话 {role.name}）；你不是它的登记会话，不要按模块会话行事。"
                f"如果你刚收到这个模块的开工说明或恢复说明，先按说明运行 module-crew bind {role.name}。")
    return (f"module-crew：本目录是 module-crew 的集成 checkout（模块协调 {role.name}）；你不是它的登记会话，不要按模块协调行事。"
            f"要换模块协调，请用户在本会话同意后运行 module-crew bind {role.name} --original-file <原话文件>。")


# ---------------------------------------------------------------- crew-coordinator-switch

def active_coordinator(db: store.Store) -> tuple[str, dict] | None:
    """The coordinator registration in use (bound or not); None means module-crew stays silent here."""
    return next(((n, s) for n, s in sorted(store.records(db, "session").items())
                 if s.get("role") == "coordinator" and s.get("status") == "active"), None)


def where(db: store.Store, rec: dict) -> str:
    """'在 <dir>，分支 <branch>' for a coordinator registration."""
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch") or "?"
    home = _home_of(db, rec)
    return f"在 {home or '（集成分支没有被检出）'}，分支 {branch}"


def _branch_here(cwd: str) -> str:
    """The branch checked out at cwd, from git metadata files only; '?' when it cannot be read."""
    root = marker.checkout_root(os.path.realpath(cwd))
    if root is None:
        return "?"
    dotgit = Path(root) / ".git"
    try:
        gitdir = dotgit if dotgit.is_dir() else Path(dotgit.read_text(encoding="utf-8").split("gitdir:", 1)[1].strip())
    except (OSError, IndexError):
        return "?"
    return _ref(gitdir / "HEAD") or "?"


def _bound_sessions(db: store.Store) -> dict[str, str]:
    """host session id -> registration name, for registrations in use."""
    return {s["hostSession"]["sessionId"]: n for n, s in store.records(db, "session").items()
            if s.get("status") == "active" and (s.get("hostSession") or {}).get("sessionId")}


def _age(at: str, now: float) -> float:
    from datetime import datetime
    return now - datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp()


def sight(db: store.Store, session_id: str, cwd: str, now: str | None = None) -> bool:
    """Record a conversation that is not a registered session; True only the first time (so it is reminded once)."""
    with db.transaction(actor="hook", wait=HOOK_WAIT) as tx:
        old = tx.get("sighting", session_id)
        if old is not None and not old.get("boundAs"):
            return False
        tx.put("sighting", session_id, {"cwd": os.path.realpath(cwd), "branch": _branch_here(cwd),
                                        "firstSeen": now or store.now(), "told": False}, action="sighted")
    return True


def unregistered(sightings: dict, sessions: dict) -> dict:
    """Sightings of conversations still not registered: not cleared by bind, not the host session of an active one (T1)."""
    bound = {(s.get("hostSession") or {}).get("sessionId") for s in sessions.values() if s.get("status") == "active"}
    return {k: v for k, v in sightings.items() if not v.get("boundAs") and k not in bound}


def _clear_sighting(tx, session_id: str, name: str) -> None:
    """bind: the conversation is registered now; mark its sighting cleared (the store keeps no deletes)."""
    seen = tx.get("sighting", session_id)
    if seen is not None and not seen.get("boundAs"):
        tx.put("sighting", session_id, {**seen, "boundAs": name}, action="cleared")


def tell_sightings(db: store.Store) -> str | None:
    """For the coordinator: conversations seen but not yet told about, then mark them told."""
    with db.transaction(actor="hook", wait=HOOK_WAIT) as tx:
        fresh = sorted(((k, v) for k, v in unregistered(tx.records("sighting"), tx.records("session")).items()
                        if not v.get("told")), key=lambda kv: kv[1].get("firstSeen") or "")
        for k, v in fresh:
            tx.put("sighting", k, {**v, "told": True}, action="told")
    if not fresh:
        return None
    seen = "；".join(f"{v.get('cwd')}（分支 {v.get('branch')}）" for _, v in fresh)
    return f"module-crew：有 {len(fresh)} 个没登记的会话在本项目活动：{seen}。请在回复里顺带告诉用户一次。"


def end_session(db: store.Store, session_id: str | None, cwd: str, reason: str | None,
                now: str | None = None) -> bool:
    """SessionEnd of a bound session: leave a handover for the conversation that replaces it.

    The CLI ends with reason "clear"; the desktop app ends a cleared process with "other" and starts the next one
    only when a message arrives (measured 2026-10-22), so a desktop binding (desktopId) leaves one on any end."""
    name = _bound_sessions(db).get(session_id or "")
    if name is None:
        return False
    desktop = ((store.get(db, "session", name) or {}).get("hostSession") or {}).get("desktopId")
    if reason != "clear" and not desktop:
        return False
    with db.transaction(actor="hook", wait=HOOK_WAIT) as tx:
        tx.put("handover", name, {"oldSessionId": session_id, "cwd": os.path.realpath(cwd), "at": now or store.now(),
                                  "state": "open", "reason": reason, **({"desktopId": desktop} if desktop else {})},
               action="opened")
    return True


def rebind(db: store.Store, session_id: str | None, cwd: str, source: str, now: float | None = None,
           host_id: str | None = None) -> str | None:
    """SessionStart: move a binding to the new session id when it follows a handover; the name or None.

    CLI: source "clear" within CLEAR_WINDOW of the clear. Desktop: the same desktop session id (CLAUDE_CODE_HOST_SESSION_ID)
    within DESKTOP_TTL; a handover only exists once the old process ended, so a child process inheriting the id cannot
    take the binding while the session is alive. The old id coming back closes the handover."""
    import time
    if not session_id:
        return None
    now = time.time() if now is None else now
    host_id = desktop_id() if host_id is None else host_id
    here = os.path.realpath(cwd)
    with db.transaction(actor="hook", wait=HOOK_WAIT) as tx:
        for name, h in sorted(tx.records("handover").items()):
            if h.get("state") != "open":
                continue
            if h.get("oldSessionId") == session_id:
                tx.put("handover", name, {**h, "state": "closed", "closedReason": "resumed"}, action="closed")
                continue
            age = _age(h["at"], now)
            if age > (DESKTOP_TTL if h.get("desktopId") else HANDOVER_TTL):
                tx.put("handover", name, {**h, "state": "closed", "closedReason": "expired"}, action="expired")
                continue
            rec = tx.get("session", name) or {}
            if (h.get("cwd") != here or rec.get("status") != "active"
                    or (rec.get("hostSession") or {}).get("sessionId") != h.get("oldSessionId")):
                continue
            by_clear = source == "clear" and age <= CLEAR_WINDOW
            by_desktop = bool(h.get("desktopId")) and host_id == h.get("desktopId")
            if not (by_clear or by_desktop):
                continue
            tx.put("session", name, {**rec, "hostSession": identity(session_id, host_id)},
                   action="rebound-after-clear", data={"oldSessionId": h.get("oldSessionId"), "sessionId": session_id,
                                                       "via": "desktop" if by_desktop else "clear"})
            tx.put("handover", name, {**h, "state": "closed", "closedReason": "rebound"}, action="closed")
            return name
    return None


def _store_at(cwd: str) -> store.Store | None:
    try:
        return store.open_store(cwd)
    except store.StoreError:
        return None


EVENT_NAMES = {"session-start": "SessionStart", "prompt": "UserPromptSubmit", "session-end": "SessionEnd"}


def _text_for(event: str, payload: dict, cwd: str) -> str | None:
    db = _store_at(cwd)
    if db is None:
        return None
    coord = active_coordinator(db)
    if coord is None:                       # no coordinator in this repository: module-crew is off here
        return None
    sid = payload.get("session_id")
    if event == "session-end":
        end_session(db, sid, cwd, payload.get("reason"))
        return None
    source = payload.get("source") or "startup"
    if event == "session-start" and rebind(db, sid, cwd, source):    # also closes a handover whose old id came back
        source = "clear"                    # say 「刚清空过」 whichever path matched
    reg = registration_of(db, sid)
    if reg is not None:                     # identity by session id, not by directory (crew-session-handover)
        role = role_of(db, *reg)
        if event == "session-start":
            return "\n".join(x for x in (session_start(cwd, source, role), elsewhere_line(db, *reg, cwd)) if x)
        line = prompt_line(cwd, role)
        if role.kind == "coordinator":
            told = tell_sightings(db)
            line = "\n".join(x for x in (line, told) if x)
        return line
    gone = superseded(db, sid)
    if gone is not None:
        return (f"module-crew：本会话已被接管：{gone} 现在登记在另一个会话上。不要再以 {gone} 的身份执行 module-crew 写命令"
                "（会被拒），也不要再替它收发消息；有要交接的事告诉用户。")
    role = detect(cwd)
    if role is not None and matches(role, sid):
        if event == "session-start":
            return session_start(cwd, source)
        line = prompt_line(cwd)
        if role.kind == "coordinator":
            told = tell_sightings(db)
            line = "\n".join(x for x in (line, told) if x)
        return line
    if event != "session-start" or sid in _bound_sessions(db):
        return None                         # strangers hear once, at start; a registered session elsewhere hears nothing
    if role is not None and role.kind in ("dev", "task"):
        return stranger_line(role)
    name, rec = coord
    if not (rec.get("hostSession") or {}).get("sessionId"):
        return stranger_line(role) if role is not None else None   # taken over, not bound yet: the bind hint only
    if not sid or not sight(db, sid, cwd):
        return None
    text = REMINDER.format(where=where(db, rec))
    if role is not None:                    # in the integration checkout itself
        text += (f"要把本会话换成模块协调，请用户明说接管后运行 module-crew takeover {name} --original-file <原话文件>，"
                 f"再在本会话运行 module-crew bind {name} --original-file <原话文件>。")
    return "module-crew：" + text + "\n" + REMINDER_ASK


def run_hook(event: str, stdin_text: str) -> str:
    """Hook entry: the JSON to print, or "" to stay silent. Never raises."""
    try:
        import json
        try:
            payload = json.loads(stdin_text) if stdin_text.strip() else {}
        except ValueError:
            payload = {}
        cwd = payload.get("cwd") or os.getcwd()
        if event not in EVENT_NAMES:
            return ""
        text = _text_for(event, payload, cwd)
        if not text or event == "session-end":
            return ""
        return json.dumps({"hookSpecificOutput": {"hookEventName": EVENT_NAMES[event], "additionalContext": text}},
                          ensure_ascii=False)
    except BaseException:  # a hook must never get in the way of the conversation
        return ""


class TakeoverRefused(Exception):
    """The takeover cannot be recorded; nothing was written."""


class BindRefused(Exception):
    """The identity cannot be recorded; nothing was written."""


def desktop_id() -> str | None:
    """The desktop app's own session id (local_…), stable across a clear; only when running under the desktop app.

    A CLI process started from inside a session inherits it too, which is why it is only trusted after a SessionEnd."""
    if (os.environ.get("CLAUDE_CODE_ENTRYPOINT") or "").strip() != "claude-desktop":
        return None
    return (os.environ.get("CLAUDE_CODE_HOST_SESSION_ID") or "").strip() or None


def identity(session_id: str, host_id: str | None = None) -> dict:
    """The hostSession record for a binding made now (crew-coordinator-switch: desktopId for the desktop clear path)."""
    host_id = desktop_id() if host_id is None else host_id
    return {"sessionId": session_id, "boundAt": store.now(), **({"desktopId": host_id} if host_id else {})}


def own_session_id() -> str | None:
    """This process's host session id: Claude Code's CLAUDE_CODE_SESSION_ID (the hook payload's session_id) or Codex's thread."""
    for key in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return None


def _home_of(db: store.Store, rec: dict) -> Path | None:
    """The directory a registration belongs to: a module's worktree, or the coordinator's integration checkout."""
    if rec.get("role") in ("dev", "task"):
        return Path(os.path.realpath(rec["worktree"])) if rec.get("worktree") else None
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch")
    checkout = _checkout_of(db.path.parent, branch) if branch else None
    return Path(os.path.realpath(checkout)) if checkout else None


PREVIOUS_KEPT = 20      # previousSessions entries kept on a registration


def bind(db: store.Store, name: str, session_id: str | None, cwd: str | os.PathLike, original: str | None = None,
         takeover: bool = False) -> str:
    """Record that the conversation running this command is the registered session `name` (crew-routing-fixes).

    0.9.3: only from the registration's own directory, and a coordinator outside `start` only with the user's words.
    takeover (crew-session-handover): the coordinator moves to this conversation in one step, from any directory of
    the repository, with the user's words; the old conversation is kept in previousSessions."""
    if not session_id or not session_id.strip():
        raise BindRefused("读不到本会话的会话 id（CLAUDE_CODE_SESSION_ID／CODEX_THREAD_ID）：只能在模块会话或模块协调自己的命令里运行")
    rec = store.get(db, "session", name)
    if rec is None or rec.get("status") != "active":
        raise BindRefused(f"{name} 不是状态库里在用的会话")
    if takeover:
        return _take_over(db, name, rec, session_id, original)
    home = _home_of(db, rec)
    if home is None or not _inside(os.path.realpath(cwd), str(home)):
        here = detect(cwd)
        owner = ("module-crew 登记以外的地方" if here is None else
                 f"模块 {here.module} 的 worktree（{here.name}）" if here.kind == "dev" else f"集成 checkout（{here.name}）")
        mine = (f"模块 {rec.get('module')} 的 worktree {home}" if rec.get("role") == "dev" else
                f"轻任务 T{rec.get('task')} 的 worktree {home}" if rec.get("role") == "task" else f"集成 checkout {home}")
        raise BindRefused(f"{name} 只能在它自己的目录里登记：这个目录属于{owner}，{name} 的是{mine}")
    coordinator = rec.get("role") == "coordinator"
    if coordinator and not (original and original.strip()):
        raise BindRefused(f"登记模块协调 {name} 的身份要用户原话：请用户在本会话同意后运行 module-crew bind {name} --original-file <原话文件>")
    with db.transaction(actor=name) as tx:
        rec = tx.get("session", name)
        bound = (rec.get("hostSession") or {}).get("sessionId")
        if bound == session_id:
            return f"{name} 已是本会话，没有改动"
        if bound:
            raise BindRefused(f"{name} 已登记为另一个会话：换会话要先请用户同意接管（模块协调运行 module-crew takeover {name}）")
        data = {"sessionId": session_id, **({"original": original} if coordinator else {})}
        tx.put("session", name, {**rec, "hostSession": identity(session_id)}, action="bound", data=data)
        _clear_sighting(tx, session_id, name)
    if rec.get("role") == "task":
        from module_crew import tasks
        tasks.bound(db, name)
    return f"已登记：本会话就是 {name}，module-crew 的钩子从现在起按这个会话注入角色"


def own_host() -> str:
    """The host of the conversation running this: Codex when only CODEX_THREAD_ID is set (crew-host-handover)."""
    if (os.environ.get("CLAUDE_CODE_SESSION_ID") or "").strip():
        return "claude-desktop"
    return "codex-desktop" if (os.environ.get("CODEX_THREAD_ID") or "").strip() else "claude-desktop"


def _take_over(db: store.Store, name: str, rec: dict, session_id: str, original: str | None) -> str:
    if rec.get("role") != "coordinator":
        raise BindRefused(f"{name} 不是模块协调：bind --takeover 只用于模块协调；模块会话与轻任务会话在自己的 worktree 里用 takeover 与 bind")
    if not (original and original.strip()):
        raise BindRefused(f"接手模块协调 {name} 要用户原话：请用户在本会话同意后运行 module-crew bind {name} --takeover --original-file <原话文件>")
    registered, mine = rec.get("host", "claude-desktop"), own_host()
    if registered != mine:
        to = "codex" if mine == "codex-desktop" else "claude"
        raise BindRefused(f"{name} 登记在 {registered}，本会话在 {mine}：换宿主要先在原会话运行 "
                          f"module-crew coordinator handover --to {to}（空档时才可以），再在本会话 bind --takeover")
    with db.transaction(actor=name) as tx:
        rec = tx.get("session", name)
        old = (rec.get("hostSession") or {}).get("sessionId")
        if old == session_id:
            return f"{name} 已是本会话，没有改动"
        prev = list(rec.get("previousSessions") or [])
        if old:
            prev = (prev + [{"sessionId": old, "at": store.now()}])[-PREVIOUS_KEPT:]
        moved = {**rec, "hostSession": identity(session_id), "previousSessions": prev}
        if (rec.get("hostHandover") or {}).get("pending"):      # crew-host-handover: the new host has arrived
            moved["hostHandover"] = {**rec["hostHandover"], "pending": False}
        tx.put("session", name, moved, action="taken-over",
               data={"original": original, "at": store.now(), "oldSessionId": old, "newSessionId": session_id})
        _clear_sighting(tx, session_id, name)
    return (f"已接管：本会话就是模块协调 {name}" + (f"，原来的会话 {old} 从现在起不能再执行模块协调的写命令" if old else "")
            + f"。请在本会话用同一个名字调用 agent-relay 的 bridge_register（name: \"{name}\"，按提示传接管参数），再跑 module-crew status。")


def takeover(db: store.Store, name: str, original: str) -> str:
    """Record the user's consent that a new conversation takes over relay name `name`."""
    if not original or not original.strip():
        raise TakeoverRefused("用户原话不能为空：接管要用户明确同意")
    with db.transaction(actor="coordinator") as tx:
        rec = tx.get("session", name)
        if rec is None or rec.get("status") != "active":
            raise TakeoverRefused(f"{name} 不是状态库里在用的会话")
        rec = {k: v for k, v in rec.items() if k != "hostSession"}      # the new conversation binds itself
        tx.put("session", name, rec, action="taken-over", data={"original": original, "at": store.now()})
    return (f"已记下：新会话接管 {name}。请在新会话里用同一个名字调用 agent-relay 的 bridge_register"
            f"（name: \"{name}\"，wake: \"auto\"；若提示该名字已被占用或已退役，按提示传接管／恢复参数），"
            f"再运行 module-crew bind {name}，然后先跑 module-crew status。")
