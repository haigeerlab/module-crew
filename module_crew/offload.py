"""Quota offload: Codex implements a module's Tasks through delegate, the coordinator checks and commits for it
(see spec/crew-codex-offload.md).

module-crew never runs delegate itself (its scripts are not an interface): `start` writes the task text and the
`/delegate:run` line for the coordinator, `settle` reads what came back. Every new behaviour needs the project switch
`codexOffload`, off unless the user turned it on.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from module_crew import checks, handover, permissions, probe, store

SWITCH = "codexOffload"
DELEGATE_MAJOR = 1


def enabled(db: store.Store | None) -> bool:
    return db is not None and (store.get(db, "config", "main") or {}).get(SWITCH) == "on"


@dataclass
class Delegate:
    reason: str | None = None          # why it cannot be used; None when it can
    version: str | None = None
    resume_timeout: bool = False       # delegate >= 1.2 also resumes a run that timed out (assumption 7)


def _minor(version: str) -> tuple[int, int]:
    try:
        major, minor = (version.split(".") + ["0"])[:2]
        return int(major), int(minor)
    except ValueError:
        return 0, 0


def delegate_interface(project: str | os.PathLike) -> Delegate:
    """Decision 2 ③: only interface.json is read, never delegate's own files."""
    found = probe.find_plugin("delegate", project)
    if isinstance(found, str):
        return Delegate(f"找不到 delegate（{found}）")
    doc = probe.read_interface(found.root, DELEGATE_MAJOR)
    if isinstance(doc, str):
        return Delegate(f"delegate {doc}")
    version = str(doc.get("interface"))
    if _minor(version) < (1, 1):
        return Delegate(f"装的 delegate 接口 {version} 低于 1.1（没有续跑）", version)
    resume = (doc.get("run") or {}).get("resume")
    if not isinstance(resume, dict) or resume.get("option") != "--resume" or "codex" not in (resume.get("backends") or []):
        return Delegate(f"delegate 接口 {version} 没有可用的 run.resume（codex 续跑）", version)
    statuses = resume.get("statuses") or []
    return Delegate(None, version, _minor(version) >= (1, 2) and "timeout" in statuses)


def _spec_guard(project: str | os.PathLike):
    """(plugin, interface doc) of spec-guard with scopeCheck, or why not."""
    found = probe.find_plugin("spec-guard", project)
    if isinstance(found, str):
        return f"找不到 spec-guard（{found}）"
    doc = probe.read_interface(found.root, probe.SPEC_GUARD_MAJOR)
    if isinstance(doc, str):
        return f"spec-guard {doc}"
    if "scopeCheck" not in doc:
        return f"装的 spec-guard 接口 {doc.get('interface')} 没有 scopeCheck，核对不了改动范围"
    return found, doc


def problems(db: store.Store, project: str | os.PathLike) -> list[str]:
    """Decision 2: every reason offloading cannot happen, in order; empty when every condition holds."""
    project = Path(project)
    cfg = store.get(db, "config", "main") or {}
    out = []
    if cfg.get(SWITCH) != "on":
        out.append("项目开关 codexOffload 没打开")
    if not checks.enabled(cfg):
        out.append("检查记账（checkLedger）没打开，代提交前跑不了快检查")
    d = delegate_interface(project)
    if d.reason:
        out.append(d.reason)
    got = _spec_guard(project)
    if isinstance(got, str):
        out.append(got)
    else:
        found, doc = got
        result = probe.run_map(found.root, doc, project)
        if isinstance(result, str):
            out.append(f"读不到 spec-guard 的 /map（{result}），核对不了 moduleConcurrency")
        elif result.get("moduleConcurrency") != "on":
            out.append("spec-guard 的 moduleConcurrency 没打开，scopeCheck 核对不了改动范围")
    host = handover.coordinator_host(db)
    if host is None:
        out.append("没有在用的模块协调")
    elif host != "claude-desktop":
        out.append("模块协调在 Codex：delegate 是 Claude Code 插件，Codex 模块协调不外包")
    if permissions.codex_trust(project, project) == "untrusted":
        out.append("Codex 把这个项目标为不信任（untrusted）：外包前请用户决定是否在 Codex 里信任它")
    return out


def ready(db: store.Store, project: str | os.PathLike) -> str | None:
    """The first reason offloading cannot happen, or None."""
    found = problems(db, project)
    return found[0] if found else None


def set_switch(db: store.Store, project: str | os.PathLike, value: str, original: str) -> list[str]:
    """Decision 1: `config set --codex-offload on|off`; raises checks.ConfigRefused and writes nothing when refused."""
    with db.transaction(actor="coordinator") as tx:
        cfg = dict(tx.get("config", "main") or {})
        if value == "on" and not checks.enabled(cfg):
            raise checks.ConfigRefused("打开额度外包前要先打开检查记账 checkLedger（config set --check-ledger on）：代提交前要跑快检查")
        tx.put("config", "main", {**cfg, SWITCH: value}, action="set", data={SWITCH: value, "original": original})
    if value == "off":
        return ["已关闭额度外包：模块会话照今天自己构建"]
    lines = ["已打开额度外包：Spec、Plan 批准后由模块协调经 delegate 把 Task 交给 Codex，核对范围、跑快检查后代提交"]
    lines += [f"⚠️ {why}；打开后这项不满足时不外包，照今天由模块会话构建前先问用户" for why in problems(db, project)]
    return lines


# ------------------------------------------------------------------ results, todo items, the task text

@dataclass
class Outcome:
    code: int
    lines: list[str]


@dataclass
class Result:
    kind: str                       # done / needs-input / timeout / unknown
    run_id: str | None = None
    status: str | None = None
    question: str | None = None
    reason: str | None = None


_RESULT_RE = re.compile(r"^delegate: run_id=(\S+) status=(\S+) resumable=(true|false)$")
NEED_USER = "NEED_USER:"
TIMEOUT_EXIT = 124


def parse_result(text: str, exit_code: int, resume_timeout: bool = False) -> Result:
    """Assumption 6: only delegate's last line and exit code count; everything else is unknown (decision 9)."""
    lines = [x for x in text.splitlines() if x.strip()]
    m = _RESULT_RE.match(lines[-1].strip()) if lines else None
    if m is None:
        if exit_code == TIMEOUT_EXIT:
            return Result("timeout")
        return Result("unknown", reason=f"退出码 {exit_code}，输出最后没有 delegate 的结果行")
    run_id, status = m.group(1), m.group(2)
    if status == "timeout" and resume_timeout:
        return Result("timeout", run_id, status)
    if exit_code != 0:
        return Result("unknown", run_id, status, reason=f"退出码 {exit_code} 却有结果行 status={status}")
    if status == "done":
        return Result("done", run_id, status)
    if status == "needs-input":
        raw = text.rstrip()
        body = raw[:raw.rfind(lines[-1])]
        at = body.find(NEED_USER)
        if at < 0:
            return Result("unknown", run_id, status, reason="status=needs-input 却没有 NEED_USER: 标记")
        return Result("needs-input", run_id, status, question=body[at + len(NEED_USER):].strip())
    return Result("unknown", run_id, status, reason=f"不认识的结束状态 status={status}")


_ITEM_RE = re.compile(r"^- \[( |x|X)\] (.+?)\s*$")


def items(todo_text: str) -> list[tuple[bool, str]]:
    """(checked, text) of every todo item, in order."""
    return [(m.group(1) != " ", m.group(2)) for m in map(_ITEM_RE.match, todo_text.splitlines()) if m]


def next_item(todo_text: str) -> tuple[str, bool] | None:
    """The first unchecked item and whether it is a Task (assumption 3: only Tasks go to Codex)."""
    for checked, text in items(todo_text):
        if not checked:
            return text, text.startswith("Task")
    return None


PENDING = ("running", "needs-input", "timeout", "stopped")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "--no-optional-locks", "-C", str(cwd), *args], capture_output=True, text=True,
                          timeout=probe.GIT_TIMEOUT)


def _session(db: store.Store, module: str) -> dict | None:
    return next((r for r in store.records(db, "session").values()
                 if r.get("role") == "dev" and r.get("module") == module and r.get("status") == "active"), None)


def _approval(db: store.Store, module: str) -> tuple[int, str] | None:
    """(C number, integration commit) of the approval that completed module's Spec and Plan, this round only."""
    from module_crew import review
    if not {"spec", "plan"} <= {("spec" if n == "interface" else n) for n in review._approved_nodes(db).get(module, set())}:
        return None
    items_ = store.records(db, "item")
    since = store.round_since(store.records(db, "session"), module)
    found = None
    for key, rec in items_.items():
        if rec.get("kind") != "review-approval":
            continue
        if any((items_.get(str(n)) or {}).get("module") == module and (items_.get(str(n)) or {}).get("node") == "plan"
               and n > since for n in rec.get("reviews", [])):
            if found is None or int(key) > found[0]:
                found = (int(key), rec.get("baselineCommit"))
    return found


def render_brief(module: str, task: str) -> str:
    """Decision 5: short, Chinese, one Task."""
    return "\n".join([
        f"你在 module-crew 模块 {module} 的 worktree 里实现一个任务。只做这一项：{task}",
        f"先读 spec/{module}.md 与 tasks/{module}/plan.md，按它们实现；测试先写、先看到失败再实现到通过。",
        f"只改 Spec「并行边界」里的独占路径、spec/{module}.md、tasks/{module}/ 下的文件，以及 Plan「预先声明」名单内的公共文件；别的文件不要改。",
        "不要提交、不要推送、不要删除文件：改完留在工作区，由模块协调核对后代为提交。",
        f"这一项做完、相关测试通过后，把 tasks/{module}/todo.md 里这一项勾上（- [ ] 改成 - [x]），别的项不要动。",
        "先做不受待定决策影响的部分。遇到这三种情况就停下：Spec 没覆盖的决策、测试改不红、高风险不可逆改动；"
        f"停下时在答复里另起一行以 {NEED_USER} 开头，后面写要问用户的问题（写清选项与各自的影响）。",
    ]) + "\n"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def start(project: str | os.PathLike, module: str, again: bool = False, answer: dict | None = None) -> Outcome:
    """Decision 5: hand the module's next Task to Codex; prints what the coordinator runs."""
    project = Path(project)
    db = store.open_store(project)
    if not enabled(db):
        return Outcome(3, ["项目开关 codexOffload 没打开：模块会话照今天自己构建"])
    why = ready(db, project)
    if why:
        return Outcome(3, [f"外包条件不满足：{why}"])
    sess = _session(db, module)
    if sess is None:
        return Outcome(3, [f"{module} 没有在用的模块会话"])
    worktree = Path(sess["worktree"])
    approval = _approval(db, module)
    if approval is None:
        return Outcome(3, [f"{module} 的 Spec 与 Plan 还没都批准，不能外包"])
    rec = store.get(db, "offload", module) or {}
    if rec.get("state") in PENDING and not again:
        return Outcome(3, [f"{module} 已有待处理的外包（{rec['state']}）：先按 offload show {module} 处理"])
    if rec.get("state") == "handed-back" and not again:
        return Outcome(3, [f"{module} 已交还模块会话：要重新外包须用户同意后用 offload start {module} --again"])
    if not again and _git(worktree, "status", "--porcelain").stdout.strip():
        return Outcome(3, [f"{module} 的 worktree 不干净（有未提交的改动）：外包要从干净的工作区开始"])
    if approval[1] and _git(worktree, "merge-base", "--is-ancestor", approval[1], "HEAD").returncode != 0:
        return Outcome(3, [f"{module} 的分支还没包含批准提交 {approval[1][:7]}：等模块会话 module-crew sync 后发来【等待其他会话】再派"])
    try:
        todo = (worktree / "tasks" / module / "todo.md").read_text(encoding="utf-8")
    except OSError as exc:
        return Outcome(3, [f"读不出 tasks/{module}/todo.md：{exc}"])
    item = next_item(todo)
    if item is None:
        return Outcome(3, [f"{module} 的 todo 已全部勾完，没有可外包的 Task"])
    if not item[1]:
        return Outcome(3, [f"{module} 的下一项不是 Task（{item[0]}）：不交给 Codex，用 offload handback {module} 交还模块会话"])
    head = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    with db.transaction(actor="coordinator") as tx:
        n = tx.allocate_number()
        meta = tx.write_body(n, render_brief(module, item[0]))
        brief = str(db.path / meta["path"])
        out = str(db.path / "tmp" / f"offload-{module}-{n}.out")
        runs = list(rec.get("runs") or [])
        runs.append({"n": n, "task": item[0], "startedAt": _now(), "brief": brief, "output": out,
                     **({"again": answer} if again and answer else {})})
        tx.put("offload", module, {"module": module, "state": "running", "approval": approval[0], "task": item[0],
                                   "base": rec.get("base") if again and rec.get("base") else head,
                                   "worktree": str(worktree), "runs": runs}, action="started")
    return Outcome(0, [
        f"外包 {module}：{item[0]}（批准事项 C{approval[0]}，基线 {head[:7]}）",
        f"在模块 worktree {worktree} 里执行（Bash 后台运行，timeout 600000，标准输出存到 {out}，记下退出码）：",
        f'  /delegate:run --write --resumable -- "$(cat {brief})"',
        f"跑完：module-crew offload settle {module} --output {out} --exit <退出码>",
    ])
