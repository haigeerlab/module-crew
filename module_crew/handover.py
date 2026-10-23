"""Switch the whole crew between Claude Code and Codex in the gap between batches (see spec/crew-host-handover.md).

Only when a batch is closed: no module or task session in use, no merge queued or running, nothing waiting on the
user. Whether to switch, and to which side, is the user's call; module-crew never looks at quotas.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from module_crew import store

HOST_IDS = {"claude": "claude-desktop", "codex": "codex-desktop"}
HOST_NAMES = {"claude-desktop": "Claude Code", "codex-desktop": "Codex"}
BUSY_TASK_STATES = ("dispatched", "working", "returned", "escalated")
PLUGIN_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Check:
    id: str
    ok: bool
    reason: str


def codex_coordinator_skill() -> Path:
    """Where the Codex coordinator skill (module B, not this module) lives once it ships."""
    return PLUGIN_ROOT / "codex-skills" / "crew-coordinator" / "SKILL.md"


def _open(kind: str, db: store.Store) -> dict:
    return {k: v for k, v in store.records(db, kind).items() if v.get("state") != "closed"}


def readiness(db: store.Store, to: str | None = None) -> list[Check]:
    """Decision 1: the fixed list `handover --check` and `handover --to` share; `to` adds the module-B check."""
    sessions = store.records(db, "session")
    busy = sorted(f"{n}（{'模块 ' + str(r.get('module')) if r.get('role') == 'dev' else '轻任务 T' + str(r.get('task'))}）"
                  for n, r in sessions.items() if r.get("status") == "active" and r.get("role") in ("dev", "task"))
    tasks = sorted(f"T{r.get('number', k)}（{r.get('state')}）" for k, r in store.records(db, "task").items()
                   if r.get("state") in BUSY_TASK_STATES)
    items = _open("item", db)
    approvals = sorted(f"C{k}" for k, v in items.items() if v.get("kind") == "merge-approval")
    from module_crew import mergelock
    lock = mergelock.read(db)
    others = sorted(f"C{k}" for k, v in items.items() if v.get("kind") != "merge-approval")
    requests = sorted(_open("request", db))
    tickets = sorted(f"W{k}" for k in _open("ticket", db))
    coord = next((n for n, r in sessions.items() if r.get("role") == "coordinator" and r.get("status") == "active"), None)
    clears = sorted(n for n, h in store.records(db, "handover").items()
                    if h.get("state") == "open" and n != coord and (sessions.get(n) or {}).get("status") == "active")
    merge_reason = "；".join(x for x in (
        f"合并正在进行（批准事项 C{lock.get('approval')}）" if lock else "",
        "已批准未合并：" + "、".join(approvals) if approvals else "") if x)
    pending = "；".join(x for x in (
        "未结的事项：" + "、".join(others) if others else "",
        "未结的公共变更请求：" + "、".join(requests) if requests else "",
        "未结的等待记录：" + "、".join(tickets) if tickets else "") if x)
    checks = [
        Check("sessions", not busy, "还有在用的会话：" + "、".join(busy) if busy else "没有在用的模块会话与轻任务会话"),
        Check("tasks", not tasks, "还有没做完的任务：" + "、".join(tasks) if tasks else "没有派出或交回中的轻任务"),
        Check("merge", not merge_reason, merge_reason or "没有排队或进行中的合并"),
        Check("pending", not pending, pending or "module-crew 侧没有待用户批的事项"),
        Check("clear-handover", not clears,
              "还有没取走的清空交接：" + "、".join(clears) if clears else "没有未取走的清空交接"),
    ]
    if to == "codex":
        ok = codex_coordinator_skill().is_file()
        checks.append(Check("codex-coordinator-skill", ok, "插件里有 Codex 版模块协调规矩" if ok else
                            "Codex 版模块协调规矩还没发版（待定模块 B）：换到 Codex 后没人管合并与派活，先不换"))
    return checks


def ready(checks: list[Check]) -> bool:
    return all(c.ok for c in checks)


def check_lines(checks: list[Check], frm: str | None, to: str | None) -> list[str]:
    head = (f"换宿主：{HOST_NAMES.get(frm, '?')} → {HOST_NAMES.get(HOST_IDS.get(to, ''), '?')}" if to
            else f"换宿主：当前模块协调在 {HOST_NAMES.get(frm, '?')}")
    lines = [head] + [f"  {'✅' if c.ok else '❌'} {c.id}：{c.reason}" for c in checks]
    lines.append("  决策收件箱侧的待决事项 module-crew 看不全：请模块协调用 decision-inbox 的 waits 再看一眼")
    lines.append("具备换宿主的条件" if ready(checks) else "还不具备换宿主的条件：先处理上面打 ❌ 的项")
    return lines


def coordinator_host(db: store.Store) -> str | None:
    rec = next((r for r in store.records(db, "session").values()
                if r.get("role") == "coordinator" and r.get("status") == "active"), None)
    return None if rec is None else rec.get("host", "claude-desktop")


def check(project: str | os.PathLike, to: str | None = None) -> tuple[int, dict, list[str]]:
    """`coordinator handover --check`: read only. 0 ready, 3 not ready."""
    db = store.open_store(Path(project))
    checks = readiness(db, to)
    frm = coordinator_host(db)
    doc = {"ready": ready(checks), "from": frm, "to": HOST_IDS.get(to) if to else None,
           "checks": [{"id": c.id, "ok": c.ok, "reason": c.reason} for c in checks]}
    return (0 if doc["ready"] else 3), doc, check_lines(checks, frm, to)
