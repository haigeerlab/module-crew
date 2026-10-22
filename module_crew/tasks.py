"""The coordinator's ledger of light tasks: one requirement or one bug each (see spec/crew-task-ledger.md).

Only bookkeeping and queueing live here; opening worktrees and sessions, hand-back, merging and escalation are
crew-light-task's, which moves the records through `advance`. Numbers share the store counter and show as T<N>.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from module_crew import refs, store
from module_crew.hooks import active_coordinator


class TaskRefused(Exception):
    """The task cannot be recorded or changed; nothing was written."""


@dataclass
class AddResult:
    number: int
    state: str
    clashes: list[str] = field(default_factory=list)     # 「T3：src/a.py」
    notes: list[str] = field(default_factory=list)


def _clean(text: str | None, what: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise TaskRefused(f"{what}不能为空")
    return text.strip()


def _caused(value: str | None) -> str | None:
    if value is None:
        return None
    m = re.match(r"^\s*([TtCc])\s*([1-9]\d*)\s*$", str(value))
    if not m:
        raise TaskRefused(f"「由哪个任务带进来」写 T<号> 或 C<号>：{value!r}")
    return f"{m.group(1).upper()}{m.group(2)}"


def add(db: store.Store, project: str | os.PathLike, kind: str, title: str, what: str, expect: list[str], done: str,
        original: str, caused_by: str | None = None) -> AddResult:
    """Record a task the user asked for; `ready` when nothing in progress touches its files, otherwise `queued`."""
    if active_coordinator(db) is None:
        raise TaskRefused("本项目没有在用的模块协调：先在要统筹的会话里 module-crew coordinator up")
    if kind not in store.TASK_TYPES:
        raise TaskRefused(f"类型只能是 {'／'.join(store.TASK_TYPES)}")
    title, what, done = _clean(title, "标题"), _clean(what, "做什么"), _clean(done, "完成标准")
    original = _clean(original, "用户原话")
    files = [f.strip() for f in expect or [] if f.strip()]
    if not files:
        raise TaskRefused("预计改哪些文件不能为空")
    bad = [f for f in files if not store.task_path_ok(f)]
    if bad:
        raise TaskRefused("预计文件要写仓库内的相对路径（不含 ..）：" + "、".join(bad))
    caused = _caused(caused_by)
    with db.transaction(actor="coordinator") as tx:
        n = tx.allocate_number()
        rec = {"type": kind, "title": title, "what": what, "expectedFiles": files, "done": done, "state": "ready",
               "causedBy": caused, "assignee": None, "worktree": None, "branch": None, "result": None,
               "original": original, "createdAt": store.now()}
        tx.put("task", str(n), rec, action="added", data={"original": original})
    return AddResult(n, "ready")


def label(n: int | str) -> str:
    return refs.task(int(n))
