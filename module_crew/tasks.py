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


ACTIVE = ("dispatched", "working", "returned", "escalated")    # 在做
HOLDING = ("ready",) + ACTIVE                                    # take part in the overlap check
FINAL = ("merged", "promoted", "cancelled")
GIT_TIMEOUT = 20


def clash(a: str, b: str) -> bool:
    """Same path, or one is a directory (trailing /) holding the other."""
    if a == b:
        return True
    return (a.endswith("/") and b.startswith(a)) or (b.endswith("/") and a.startswith(b))


def _module_files(db: store.Store, project: Path) -> tuple[dict[str, list[str]], list[str]]:
    """Files each in-use module branch already changed relative to the integration branch; notes for branches not read."""
    import subprocess
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch")
    out, notes = {}, []
    for name, s in sorted(store.records(db, "session").items()):
        if s.get("role") != "dev" or s.get("status") != "active" or not s.get("module"):
            continue
        mod = s["module"]
        try:
            run = subprocess.run(["git", "-C", str(project), "diff", "--name-only", f"{branch}...{mod}"],
                                 capture_output=True, text=True, timeout=GIT_TIMEOUT)
        except (subprocess.TimeoutExpired, OSError):
            notes.append(f"模块 {mod} 的分支读不出改动（超时或 git 不可用），没有比较")
            continue
        if run.returncode != 0:
            notes.append(f"模块 {mod} 的分支读不出改动（{run.stderr.strip()[:80]}），没有比较")
            continue
        out[mod] = [line for line in run.stdout.splitlines() if line.strip()]
    return out, notes


def overlaps(db: store.Store, project: str | os.PathLike, files: list[str],
             exclude: int | None = None) -> tuple[list[str], list[str]]:
    """(clashes, notes) of `files` against tasks holding files and in-use module branches. Read-only."""
    clashes = []
    for k, t in sorted(store.records(db, "task").items(), key=lambda kv: int(kv[0])):
        if t.get("state") not in HOLDING or (exclude is not None and int(k) == exclude):
            continue
        theirs = list(t.get("expectedFiles") or []) + list(((t.get("result") or {}).get("files")) or [])
        hit = sorted({f for f in files for o in theirs if clash(f, o)})
        clashes += [f"{label(k)}：{f}" for f in hit]
    changed, notes = _module_files(db, Path(project))
    for mod, theirs in changed.items():
        hit = sorted({f for f in files for o in theirs if clash(f, o)})
        clashes += [f"模块 {mod}：{f}" for f in hit]
        if not hit:
            notes.append(f"模块 {mod} 还在开发，以后可能碰到同样的文件（只比了它已经改过的）")
    return clashes, notes


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
    clashes, notes = overlaps(db, project, files)
    state = "queued" if clashes else "ready"
    with db.transaction(actor="coordinator") as tx:
        n = tx.allocate_number()
        rec = {"type": kind, "title": title, "what": what, "expectedFiles": files, "done": done, "state": state,
               "causedBy": caused, "assignee": None, "worktree": None, "branch": None, "result": None,
               "original": original, "createdAt": store.now()}
        tx.put("task", str(n), rec, action="added", data={"original": original})
    return AddResult(n, state, clashes, notes)


def label(n: int | str) -> str:
    return refs.task(int(n))


RECENT_SHOWN = 5


def summary(db: store.Store, project: str | os.PathLike) -> dict:
    """For status: tasks in progress (and ready), queued ones with what they clash with, the latest finished. Read-only."""
    rows = sorted((int(k), t) for k, t in store.records(db, "task").items())
    pick = lambda n, t, **extra: {"number": n, "label": label(n), "type": t["type"], "title": t["title"],
                                  "state": t["state"], "assignee": t.get("assignee"), **extra}
    active = [pick(n, t) for n, t in rows if t["state"] in HOLDING]
    queued = [pick(n, t, clashes=overlaps(db, project, t["expectedFiles"], exclude=n)[0])
              for n, t in rows if t["state"] == "queued"]
    recent = [pick(n, t) for n, t in reversed(rows) if t["state"] in FINAL][:RECENT_SHOWN]
    return {"active": active, "queued": queued, "recent": recent}


TRANSITIONS = {
    "queued": {"ready", "cancelled"},
    "ready": {"queued", "dispatched", "cancelled"},
    "dispatched": {"working", "escalated", "cancelled"},
    "working": {"returned", "escalated", "cancelled"},
    "returned": {"merged", "working", "escalated", "cancelled"},
    "escalated": {"working", "promoted", "cancelled"},
}
FIELDS = ("assignee", "worktree", "branch", "result")


def advance(db: store.Store, number: int, new_state: str, original: str | None = None, **fields) -> dict:
    """Move a task along TRANSITIONS (crew-light-task calls this); anything else is refused."""
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise TaskRefused("不认识的任务字段：" + "、".join(sorted(unknown)))
    with db.transaction(actor="coordinator") as tx:
        rec = tx.get("task", str(number))
        if rec is None:
            raise TaskRefused(f"{label(number)} 不是任务")
        if new_state not in TRANSITIONS.get(rec["state"], set()):
            raise TaskRefused(f"{label(number)} 现在是「{STATE_NAMES[rec['state']]}」，不能改成「{STATE_NAMES.get(new_state, new_state)}」")
        rec = {**rec, **fields, "state": new_state}
        tx.put("task", str(number), rec, action=new_state, data={"original": original} if original else None)
    return rec


def cancel(db: store.Store, number: int, original: str) -> dict:
    """Cancel a task that has not been merged; the user's words are kept."""
    return advance(db, number, "cancelled", original=_clean(original, "用户原话"))


def next_ready(db: store.Store, project: str | os.PathLike) -> list[int]:
    """Promote queued tasks that no longer clash, bugs first then by number; each promoted one holds its files."""
    queued = sorted(((int(k), t) for k, t in store.records(db, "task").items() if t.get("state") == "queued"),
                    key=lambda kv: (kv[1].get("type") != "bug", kv[0]))
    promoted = []
    for n, t in queued:
        clashes, _ = overlaps(db, project, list(t.get("expectedFiles") or []), exclude=n)
        if not clashes:
            advance(db, n, "ready")
            promoted.append(n)
    return promoted


STATE_NAMES = {"queued": "排队", "ready": "可开", "dispatched": "已派出", "working": "在做", "returned": "交回",
               "escalated": "升格待定", "merged": "已合入", "promoted": "已升格", "cancelled": "已取消"}
