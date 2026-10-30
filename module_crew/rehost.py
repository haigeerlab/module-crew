"""Move an unfinished batch from Codex to Claude Code in one step (see spec/crew-live-rehost.md).

The user starts it from a new, unregistered Claude conversation in the integration checkout, without the old Codex
coordinator's help. `--check` shows what moves and a confirmation code; `--to claude` needs the user's words with
that code. Open items, requests and waits stay keyed by relay name, so they carry over untouched.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from module_crew import store
from module_crew.handover import Check, ready

FROM, TO = "codex-desktop", "claude-desktop"
OFFLOAD_OPEN = ("running", "needs-input", "stopped", "timeout")
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"     # no 0/O/1/I
DIRTY_SHOWN = 50
GIT_TIMEOUT = 30


def _git(cwd: str | os.PathLike, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=GIT_TIMEOUT)


def movers(db: store.Store) -> list[tuple[str, dict]]:
    """The coordinator and every module or task session in use: all of them move together."""
    return [(n, r) for n, r in sorted(store.records(db, "session").items())
            if r.get("status") == "active" and r.get("role") in ("coordinator", "dev", "task")]


def snapshot(worktree: str | None) -> dict:
    """HEAD and the uncommitted files of a worktree, as git prints them (sorted, so the code does not wobble)."""
    if not worktree or not Path(worktree).is_dir():
        return {"head": None, "dirty": []}
    try:
        head = _git(worktree, "rev-parse", "HEAD")
        status = _git(worktree, "status", "--porcelain=v1", "-uall")
    except (OSError, subprocess.TimeoutExpired):
        return {"head": None, "dirty": []}
    return {"head": (head.stdout.strip() or None) if head.returncode == 0 else None,
            "dirty": sorted(l for l in status.stdout.splitlines() if l.strip()) if status.returncode == 0 else []}


def integration(db: store.Store, project: str | os.PathLike) -> Path | None:
    from module_crew import probe
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch")
    found = probe._checkout_of(Path(project), branch) if branch else None
    return Path(os.path.realpath(found)) if found else None


def caller_host() -> str | None:
    """'claude-desktop', 'codex-desktop', or None for the user at a terminal."""
    if (os.environ.get("CLAUDE_CODE_SESSION_ID") or "").strip():
        return TO
    return FROM if (os.environ.get("CODEX_THREAD_ID") or "").strip() else None


def _inside(path: str, root: Path) -> bool:
    here = os.path.realpath(path)
    return here == str(root) or here.startswith(str(root) + os.sep)


def readiness(db: store.Store, project: str | os.PathLike, cwd: str | os.PathLike,
              session_id: str | None) -> list[Check]:
    """Decision 1: the fixed list `rehost --check` and `rehost --to` share."""
    from module_crew import hooks, mergelock, probe
    moving = movers(db)
    coord = next(((n, r) for n, r in moving if r.get("role") == "coordinator"), None)
    coord_host = None if coord is None else coord[1].get("host", TO)
    on_claude = sorted(n for n, r in moving if r.get("role") != "coordinator" and r.get("host", TO) != FROM)
    lock = mergelock.read(db)
    offloads = sorted(f"{m}（{r.get('state')}）" for m, r in store.records(db, "offload").items()
                      if r.get("state") in OFFLOAD_OPEN)
    found = probe.find_plugin("spec-guard", project)
    host = caller_host()
    bound = hooks.registration_of(db, session_id)
    home = integration(db, project)
    caller_reason = ("Codex 会话不能发起：迁到 Claude 要在 Claude 会话里做" if host == FROM else
                     f"本会话已登记为 {bound[0]}：要在还没登记的 Claude 会话里发起" if bound else
                     "调用者是还没登记的 Claude 会话" if host == TO else "调用者在终端（读不到会话编号）")
    return [
        Check("coordinator-host", coord_host == FROM,
              "模块协调登记在 Codex" if coord_host == FROM else
              "本项目没有在用的模块协调" if coord is None else
              "模块协调登记在 Claude：批次内迁移只做 Codex→Claude（空档换宿主用 coordinator handover）"),
        Check("all-codex", not on_claude,
              "在用的模块会话、轻任务会话都在 Codex" if not on_claude else
              "有登记在 Claude 的会话，混搭不迁：" + "、".join(on_claude)),
        Check("merge", lock is None,
              "没有进行中的合并" if lock is None else f"合并正在进行（批准事项 C{lock.get('approval', '?')}）：等它结束再迁"),
        Check("offload", not offloads,
              "没有未结的外包" if not offloads else "外包没结：" + "、".join(offloads)),
        Check("spec-guard", not isinstance(found, str),
              "本机 Claude 装着 spec-guard" if not isinstance(found, str) else f"找不到 spec-guard（{found}）：迁过去的会话离不开它"),
        Check("caller", host != FROM and bound is None, caller_reason),
        Check("cwd", home is not None and _inside(str(cwd), home),
              f"当前目录在集成 checkout {home}" if home is not None and _inside(str(cwd), home) else
              f"要在集成 checkout {home or '（集成分支没有被检出）'} 里运行"),
    ]


def state_of(db: store.Store) -> dict:
    """What the confirmation code is taken over: who moves, where they are bound, and each worktree's state."""
    from module_crew import mergelock
    rows = []
    for name, rec in movers(db):
        row = {"name": name, "role": rec.get("role"), "host": rec.get("host", TO),
               "session": (rec.get("hostSession") or {}).get("sessionId")}
        if rec.get("role") != "coordinator":
            row.update(worktree=rec.get("worktree"), **snapshot(rec.get("worktree")))
        rows.append(row)
    return {"sessions": rows, "merge": mergelock.read(db) is not None,
            "offload": {m: r.get("state") for m, r in sorted(store.records(db, "offload").items())}}


def confirm_code(state: dict) -> str:
    """Decision 3: six characters from the state's hash; nothing is stored."""
    digest = hashlib.sha256(json.dumps(state, sort_keys=True, ensure_ascii=False).encode("utf-8")).digest()
    return "".join(CODE_ALPHABET[b % len(CODE_ALPHABET)] for b in digest[:6])


def _who(row: dict, rec: dict) -> str:
    return ("模块协调" if row["role"] == "coordinator" else
            f"模块 {rec.get('module')}" if row["role"] == "dev" else f"轻任务 T{rec.get('task')}")


def session_lines(db: store.Store, state: dict) -> list[str]:
    sessions = store.records(db, "session")
    lines = ["要迁的会话（邮箱名不变）："]
    for row in state["sessions"]:
        rec = sessions.get(row["name"]) or {}
        lines.append(f"  {row['name']}（{_who(row, rec)}）")
        if row["role"] == "coordinator":
            continue
        head = (row.get("head") or "读不到")[:7]
        dirty = row.get("dirty") or []
        lines.append(f"    worktree：{row.get('worktree')}，HEAD {head}，未提交改动 {len(dirty)} 个（原样带过去，盘点时由用户定留还是丢）")
        lines += [f"      {l}" for l in dirty[:DIRTY_SHOWN]]
        if len(dirty) > DIRTY_SHOWN:
            lines.append(f"      另有 {len(dirty) - DIRTY_SHOWN} 个")
    return lines


def check(project: str | os.PathLike, cwd: str | os.PathLike, session_id: str | None) -> tuple[int, dict, list[str]]:
    """`coordinator rehost --check`: read only. 0 ready (with a code), 3 not ready (no code)."""
    db = store.open_store(Path(project))
    checks = readiness(db, project, cwd, session_id)
    state = state_of(db)
    ok = ready(checks)
    code = confirm_code(state) if ok else None
    doc = {"ready": ok, "code": code, "from": FROM, "to": TO,
           "checks": [{"id": c.id, "ok": c.ok, "reason": c.reason} for c in checks],
           "sessions": [{"name": r["name"], "role": r["role"],
                         "module": (store.get(db, "session", r["name"]) or {}).get("module"),
                         "task": (store.get(db, "session", r["name"]) or {}).get("task"),
                         "worktree": r.get("worktree"), "head": r.get("head"), "dirty": r.get("dirty")}
                        for r in state["sessions"]]}
    lines = ["批次内迁移：Codex → Claude Code"] + [f"  {'✅' if c.ok else '❌'} {c.id}：{c.reason}" for c in checks]
    lines += session_lines(db, state)
    lines.append("未结的事项、公共变更请求、等待记录、轻任务都按邮箱名原样带过去，不用处理；"
                 "决策收件箱侧的待决事项 module-crew 看不全，请用 decision-inbox 的 waits 再看一眼")
    if ok:
        lines += [f"确认码：{code}",
                  "把上面整段给用户看。用户同意时，原话里要有这个确认码，并写明 Codex 里的旧会话（上面每一个）已亲手停下并归档；"
                  f"再运行 module-crew coordinator rehost --to claude --code {code} --original-file <原话文件>。状态一变确认码就变，要重新 --check"]
    else:
        lines.append("还不能迁：先处理上面打 ❌ 的项")
    return (0 if ok else 3), doc, lines
