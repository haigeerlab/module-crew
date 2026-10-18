"""Role-aware context for SessionStart / UserPromptSubmit hooks, and takeover (see spec/crew-recovery-hooks.md).

Read-only and fast: only the store and git metadata files are read; no probe, no /map.
Anything unexpected means "not a module-crew session" and the hook stays silent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from module_crew import role as marker
from module_crew import store


@dataclass(frozen=True)
class Role:
    kind: str                     # dev / coordinator
    name: str                     # relay name
    module: str | None
    db: store.Store


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


COMPACT_NOTE = "刚压缩过：先跑 `module-crew status`、读未完成的事项，以状态库为准，不按压缩前的记忆重做已经做过的事。"
STAGE_WRITE = "写 Spec 与 Plan、发【交审】，收到开工通知之前不要构建"
STAGE_BUILD = "Spec 与 Plan 已批准，可以构建；做完发最终验收【交审】"
STAGE_WAIT_MERGE = "最终验收已批准，等协调会话合并"
STAGE_MERGED = "已合入集成分支，停止开发，等协调会话收回 worktree"


def _stage(items: dict, module: str) -> str:
    approved = set()
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
        "等待单": sum(1 for v in store.records(db, "ticket").values() if v.get("state") != "closed"),
        "待合并": sum(1 for v in items.values() if v.get("kind") == "merge-approval" and v.get("state") == "open"),
    }


def _count_text(c: dict[str, int]) -> str:
    return "未关 " + "／".join(f"{k} {n}" for k, n in c.items())


def _coordinator_name(db: store.Store) -> str:
    return next((n for n, s in sorted(store.records(db, "session").items())
                 if s.get("role") == "coordinator" and s.get("status") == "active"), "（没有在用的协调会话）")


def session_start(cwd: str | os.PathLike, source: str = "startup") -> str | None:
    role = detect(cwd)
    if role is None:
        return None
    if role.kind == "dev":
        tickets = sorted(int(k) for k, v in store.records(role.db, "ticket").items()
                         if v.get("from") == role.name and v.get("state") == "open")
        lines = [f"module-crew：你是模块 {role.module} 的模块会话（邮箱名 {role.name}），协调会话是 {_coordinator_name(role.db)}，你只和它说话。",
                 "按 crew-dev skill 的规则做；被挡住必须发【等待其他会话】；发出前 module-crew protocol check。",
                 f"当前：{_stage(store.records(role.db, 'item'), role.module)}",
                 "未关的等待单：" + ("、".join(f"#{n}" for n in tickets) or "无")]
    else:
        lines = [f"module-crew：本会话是协调会话（{role.name}）。{_count_text(_counts(role.db))}。",
                 "先跑 `module-crew status` 再动手；看 agent-relay 在线状态里谁处于「等待审批」，提醒用户去那个会话点权限弹窗。",
                 "按 crew-coordinator skill 的规则做：只统筹不开发，只转达用户在本会话亲手输入的话。"]
    if source == "compact":
        lines.append(COMPACT_NOTE)
    return "\n".join(lines)


def prompt_line(cwd: str | os.PathLike) -> str | None:
    role = detect(cwd)
    if role is None:
        return None
    if role.kind == "dev":
        stage = _stage(store.records(role.db, "item"), role.module).split("，")[0].split("（")[0]
        return f"module-crew：你是 {role.module} 的模块会话（{role.name}），当前：{stage}"
    return f"module-crew：协调会话；{_count_text(_counts(role.db))}"


EVENT_NAMES = {"session-start": "SessionStart", "prompt": "UserPromptSubmit"}


def run_hook(event: str, stdin_text: str) -> str:
    """Hook entry: the JSON to print, or "" to stay silent. Never raises."""
    try:
        import json
        try:
            payload = json.loads(stdin_text) if stdin_text.strip() else {}
        except ValueError:
            payload = {}
        cwd = payload.get("cwd") or os.getcwd()
        if event == "session-start":
            text = session_start(cwd, payload.get("source") or "startup")
        elif event == "prompt":
            text = prompt_line(cwd)
        else:
            return ""
        if not text:
            return ""
        return json.dumps({"hookSpecificOutput": {"hookEventName": EVENT_NAMES[event], "additionalContext": text}},
                          ensure_ascii=False)
    except BaseException:  # a hook must never get in the way of the conversation
        return ""


class TakeoverRefused(Exception):
    """The takeover cannot be recorded; nothing was written."""


def takeover(db: store.Store, name: str, original: str) -> str:
    """Record the user's consent that a new conversation takes over relay name `name`."""
    if not original or not original.strip():
        raise TakeoverRefused("用户原话不能为空：接管要用户明确同意")
    with db.transaction(actor="coordinator") as tx:
        rec = tx.get("session", name)
        if rec is None or rec.get("status") != "active":
            raise TakeoverRefused(f"{name} 不是状态库里在用的会话")
        tx.put("session", name, rec, action="taken-over", data={"original": original, "at": store.now()})
    return (f"已记下：新会话接管 {name}。请在新会话里用同一个名字调用 agent-relay 的 bridge_register"
            f"（name: \"{name}\"，wake: \"auto\"；若提示该名字已被占用或已退役，按提示传接管／恢复参数），然后先跑 module-crew status。")
