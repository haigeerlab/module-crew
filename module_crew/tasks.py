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
from module_crew.hooks import ENTRY_LINE, active_coordinator


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


@dataclass
class Dispatched:
    number: int
    worktree: str
    branch: str
    relay: str
    kickoff: int
    kickoff_path: str
    lines: list[str] = field(default_factory=list)


def render_kickoff(n: int, t: dict, worktree: Path, branch: str, cfg: dict, relay: str, coord: str,
                   codex: list[str] | None = None) -> str:
    """The first message of a light task's session: the task card, its rules and the v2.5 message shapes."""
    check = cfg.get("checkCommand") or "项目 Spec 的 Commands 一节里的完整检查命令"
    caused = [f"由 {t['causedBy']} 带进来：修之前先看那次改动。"] if t.get("causedBy") else []
    bug = (["这是 bug：先写一个能复现问题的测试，确认它失败，再修到它通过；交回的「要点」里写一行「复现测试：<测试名>」。"]
           if t["type"] == "bug" else [])
    return "\n".join([
        f"你是 module-crew 的轻任务会话，负责轻任务 T{n}（{'bug' if t['type'] == 'bug' else '需求'}）：{t['title']}。",
        "先加载 crew-dev skill，照它的「轻任务」一节做；规则不要抄进这个 worktree 的 CLAUDE.md。",
        "",
        "任务单：",
        f"- 做什么：{t['what']}",
        f"- 预计改的文件：{'、'.join(t['expectedFiles'])}",
        f"- 做到什么程度算完：{t['done']}",
        *caused,
        "",
        f"工作目录：{worktree}（分支 {branch}，从集成分支 {cfg['integrationBranch']} 切出）",
        f"邮箱名：{relay}，用 agent-relay bridge_register 注册，wake: \"auto\"",
        f"注册后先运行 module-crew bind {relay}：登记本会话的身份，module-crew 的钩子只认登记过的会话",
        f"模块协调：{coord}（你只和它说话）",
        *([] if codex else [ENTRY_LINE]),   # Codex has no hooks: the Codex lines give the fixed entry (crew-host-handover)
        "",
        *bug,
        f"做完、提交、跑完整检查（{check}）全部通过后才交回。交回发最终验收【交审】，样子是：",
        "【交审】", "结束：无", "模块：无", "节点：最终验收", "文件：", "- <改动的文件> sha256:<前 16 位>",
        "要点：", "- 做了什么", "- 实测：<命令>，<结果>", "- 没验证：<哪些>", f"任务：T{n}",
        "改动统计：", "  <git diff --stat 的最后一行，相对集成分支>",
        "越界检查：与任务单一致（预计 …）／多改了 <文件>，原因 …",
        "",
        "做到一半发现比任务单大、或要改别人正在改的文件：停下，代码留在本分支，发【等待用户】：",
        "要你决定写「轻任务 T<号> 超出任务单，升格、缩小还是取消」，要点写「出了什么事：做了什么、还剩什么、为什么超出」，",
        f"然后一行「任务：T{n}」、一行「类型：卡住选做法」，选项 A 升格为模块／B 缩小／C 取消，「是否完全停住：是」。",
        "只多改了没人在碰的文件，不用停，交回时在「越界检查」里写一句。",
        "",
        "全局约束：不改公共文件（要改发【公共变更请求】）；被挡住发【等待其他会话】；发出前 module-crew protocol check。",
    ] + (codex or [])) + "\n"


def dispatch(db: store.Store, project: str | os.PathLike, number: int, host: str | None = None) -> Dispatched:
    """ready → dispatched: its own worktree and branch from the integration branch, a `task` registration, the kickoff."""
    import subprocess
    project = Path(project)
    t = store.get(db, "task", str(number))
    if t is None:
        raise TaskRefused(f"{label(number)} 不是任务")
    if t["state"] != "ready":
        raise TaskRefused(f"{label(number)} 现在是「{STATE_NAMES[t['state']]}」，只有「可开」的任务能派出")
    cfg = store.get(db, "config", "main") or {}
    if not all(cfg.get(k) for k in ("crewDir", "integrationBranch", "projectShort")):
        raise TaskRefused("运行配置还没定（先 module-crew coordinator up）")
    coord = active_coordinator(db)
    if coord is None:
        raise TaskRefused("本项目没有在用的模块协调")
    from module_crew import handover, start
    refused, host = handover.pick_host(db, host)      # crew-host-handover: follow the coordinator's host
    if refused:
        raise TaskRefused(refused)
    host_id = start.HOSTS[host]
    branch, relay = f"task/t{number}", f"{cfg['projectShort']}-t{number}"
    worktree = Path(cfg["crewDir"]) / f"task-t{number}"
    if worktree.exists():
        raise TaskRefused(f"worktree 目录已存在：{worktree}")
    added = subprocess.run(["git", "-C", str(project), "worktree", "add", "-q", "-b", branch, str(worktree),
                            cfg["integrationBranch"]], capture_output=True, text=True, timeout=60)
    if added.returncode != 0:
        raise TaskRefused(f"建 worktree 失败：{added.stderr.strip()[:200]}")
    text = render_kickoff(number, t, worktree, branch, cfg, relay, coord[0],
                          start.codex_lines(relay, db.path) if host_id == "codex-desktop" else None)
    try:
        with db.transaction(actor=coord[0]) as tx:
            tx.put("session", relay, {"role": "task", "host": host_id, "status": "active", "task": number,
                                      "worktree": str(worktree)}, action="registered")
            body = tx.allocate_number()
            tx.write_body(body, text)
    except store.StoreError:            # nothing recorded: take the fresh worktree and branch back
        subprocess.run(["git", "-C", str(project), "worktree", "remove", "--force", str(worktree)],
                       capture_output=True, timeout=60)
        subprocess.run(["git", "-C", str(project), "branch", "-D", branch], capture_output=True, timeout=60)
        raise
    advance(db, number, "dispatched", assignee=relay, worktree=str(worktree), branch=branch)
    result = Dispatched(number, str(worktree), branch, relay, body, str(db.path / "bodies" / f"{body}.txt"))
    from module_crew import permissions
    line = permissions.follow(project, relay)
    if line:
        result.lines.append(line)
    return result


@dataclass
class Scoped:
    number: int
    body: int
    path: str


def scope(db: store.Store, number: int, expect: list[str], done: str, original: str) -> Scoped:
    """After an escalation answered 「缩小」: rewrite the task card and send it back to work."""
    t = store.get(db, "task", str(number))
    if t is None or t.get("state") != "escalated":
        raise TaskRefused(f"{label(number)} 不在等升格决定，不能缩小")
    original, done = _clean(original, "用户原话"), _clean(done, "完成标准")
    files = [f.strip() for f in expect or [] if f.strip()]
    if not files or not all(store.task_path_ok(f) for f in files):
        raise TaskRefused("预计文件要写仓库内的相对路径（不含 ..），不能为空")
    text = "\n".join([f"轻任务 {label(number)} 已按用户的决定缩小，新的任务单：",
                      f"- 做什么：{t['what']}", f"- 预计改的文件：{'、'.join(files)}", f"- 做到什么程度算完：{done}",
                      "超出这份任务单的改动不要再做，做完按原来的写法交回最终验收【交审】。"]) + "\n"
    with db.transaction(actor="coordinator") as tx:
        tx.put("task", str(number), {**t, "expectedFiles": files, "done": done, "state": "working"},
               action="scoped", data={"original": original})
        body = tx.allocate_number()
        meta = tx.write_body(body, text)
    return Scoped(number, body, str(db.path / meta["path"]))


def bound(db: store.Store, name: str) -> None:
    """A task session bound its identity: the task is being worked on."""
    rec = store.get(db, "session", name) or {}
    t = store.get(db, "task", str(rec.get("task"))) if rec.get("role") == "task" else None
    if t is not None and t.get("state") == "dispatched":
        advance(db, rec["task"], "working")
