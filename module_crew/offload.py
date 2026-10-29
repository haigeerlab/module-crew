"""Quota offload, round 2: the module session hands its Tasks to one Codex session through delegate >= 1.3, checks
what comes back and commits it itself (see spec/crew-codex-offload.md).

module-crew never runs delegate itself (its scripts are not an interface): `start` writes the task text and the
`/delegate:run` line for the module session, `settle` reads what came back. Every new behaviour needs the project
switch `codexOffload`, off unless the user turned it on, and a module marked for Codex when its start notice went out.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from module_crew import checks, hooks, permissions, probe, store

SWITCH = "codexOffload"
SWITCH_WORDS = "codexOffloadOriginal"    # the user's words when the switch went on, copied into each module's grant
DELEGATE_MAJOR = 1
VERSION = 2                              # round 2 records; round 1 records have no version (assumption 10)
TIMEOUT = 1800                           # assumption 6
TAIL = 20


def enabled(db: store.Store | None) -> bool:
    return db is not None and (store.get(db, "config", "main") or {}).get(SWITCH) == "on"


@dataclass
class Delegate:
    reason: str | None = None          # why it cannot be used; None when it can
    version: str | None = None


def _minor(version: str) -> tuple[int, int]:
    try:
        major, minor = (version.split(".") + ["0"])[:2]
        return int(major), int(minor)
    except ValueError:
        return 0, 0


def delegate_interface(project: str | os.PathLike) -> Delegate:
    """Decision 2 ③: only interface.json is read, never delegate's own files; every 1.3 flag this module uses."""
    found = probe.find_plugin("delegate", project)
    if isinstance(found, str):
        return Delegate(f"找不到 delegate（{found}）")
    doc = probe.read_interface(found.root, DELEGATE_MAJOR)
    if isinstance(doc, str):
        return Delegate(f"delegate {doc}")
    version = str(doc.get("interface"))
    if _minor(version) < (1, 3):
        return Delegate(f"装的 delegate 接口 {version} 低于 1.3（没有接续、长期限、结果文件与写入授权）", version)
    run = doc.get("run") or {}
    sub = lambda key: run.get(key) if isinstance(run.get(key), dict) else {}
    resume, cont, long_run, result, grant = (sub(k) for k in ("resume", "continue", "longRun", "result", "writeAuthorization"))
    missing = []
    if resume.get("option") != "--resume" or "codex" not in (resume.get("backends") or []) \
            or not {"needs-input", "timeout"} <= set(resume.get("statuses") or []):
        missing.append("run.resume（codex 的 needs-input 与 timeout 续跑）")
    if cont.get("option") != "--continue" or "done" not in (cont.get("accepts") or []) or cont.get("chain") != "--resumable":
        missing.append("run.continue（done 之后接着同一条 --resumable 链）")
    try:
        long_ok = long_run.get("option") == "--timeout" and int(long_run.get("maxSeconds") or 0) >= TIMEOUT
    except (TypeError, ValueError):
        long_ok = False
    if not long_ok:
        missing.append(f"run.longRun（--timeout 能放到 {TIMEOUT} 秒）")
    if result.get("schemaVersion") != 1 or not result.get("strict"):
        missing.append("run.result（结果文件 schemaVersion 1 与 --strict）")
    if grant.get("option") != "--authorized-by":
        missing.append("run.writeAuthorization（--authorized-by）")
    if missing:
        return Delegate(f"delegate 接口 {version} 缺：" + "、".join(missing), version)
    return Delegate(None, version)


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


def _dev(db: store.Store, module: str) -> tuple[str, dict] | None:
    return next(((n, r) for n, r in sorted(store.records(db, "session").items())
                 if r.get("role") == "dev" and r.get("module") == module and r.get("status") == "active"), None)


def module_host(db: store.Store, module: str) -> str | None:
    dev = _dev(db, module)
    return None if dev is None else dev[1].get("host", "claude-desktop")


def problems(db: store.Store, project: str | os.PathLike, module: str | None = None) -> list[str]:
    """Decision 2: every reason offloading cannot happen, in order; empty when every condition holds.
    Condition ⑤ (the module session runs in Claude Code) is checked only when a module is named."""
    project = Path(project)
    cfg = store.get(db, "config", "main") or {}
    out = []
    if cfg.get(SWITCH) != "on":
        out.append("项目开关 codexOffload 没打开")
    elif not (cfg.get(SWITCH_WORDS) or {}).get("original"):
        out.append("开关打开时的用户原话没记下（旧版打开的）：请用户原话重新 config set --codex-offload on")
    if not checks.enabled(cfg):
        out.append("检查记账（checkLedger）没打开，提交前跑不了快检查")
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
    if module is not None:
        host = module_host(db, module)
        if host is None:
            out.append(f"{module} 没有在用的模块会话")
        elif host != "claude-desktop":
            out.append(f"{module} 的模块会话在 Codex：delegate 是 Claude Code 插件")
    if permissions.codex_trust(project, project) == "untrusted":
        out.append("Codex 把这个项目标为不信任（untrusted）：外包前请用户决定是否在 Codex 里信任它")
    return out


def ready(db: store.Store, project: str | os.PathLike, module: str | None = None) -> str | None:
    """The first reason offloading cannot happen, or None."""
    found = problems(db, project, module)
    return found[0] if found else None


def set_switch(db: store.Store, project: str | os.PathLike, value: str, original: str) -> list[str]:
    """Decision 1: `config set --codex-offload on|off`; raises checks.ConfigRefused and writes nothing when refused."""
    with db.transaction(actor="coordinator") as tx:
        cfg = dict(tx.get("config", "main") or {})
        if value == "on" and not checks.enabled(cfg):
            raise checks.ConfigRefused("打开额度外包前要先打开检查记账 checkLedger（config set --check-ledger on）：提交前要跑快检查")
        cfg[SWITCH] = value
        if value == "on":
            cfg[SWITCH_WORDS] = {"original": original, "at": _now(), **store.source_field()}
        tx.put("config", "main", cfg, action="set", data={SWITCH: value, "original": original})
    if value == "off":
        return ["已关闭额度外包：之后开工的模块照今天由模块会话构建；已经交给 Codex 的模块照旧做完"]
    lines = ["已打开额度外包：之后开工的模块（Spec、Plan 批准后）由模块会话经 delegate 把 Task 交给同一个 Codex 会话，自己核对、快检查、提交"]
    lines += [f"⚠️ {why}；打开后这项不满足时不外包，开工前先问用户" for why in problems(db, project)]
    return lines


# ------------------------------------------------------------------ the hand-over at the start notice (decision 3)

def grant_text(cfg: dict, module: str, approval: int, worktree: str) -> str:
    words = cfg.get(SWITCH_WORDS) or {}
    return (f"用户打开额度外包开关的原话：{words.get('original', '')}（{words.get('at', '')}）\n"
            f"模块 {module}；Spec、Plan 批准事项 C{approval}；模块 worktree {worktree}\n")


def assign(tx, db: store.Store, module: str, approval: int) -> str:
    """Decision 3: mark `module` for Codex inside the approval's transaction; returns the grant file's path."""
    cfg = tx.get("config", "main") or {}
    dev = _dev(db, module)
    worktree = dev[1].get("worktree", "") if dev else ""
    n = tx.allocate_number()
    meta = tx.write_body(n, grant_text(cfg, module, approval, worktree))
    path = str(db.path / meta["path"])
    tx.put("offload", module, {"module": module, "version": VERSION, "state": "assigned", "approval": approval,
                               "authorization": {"path": path, "sha256": meta["sha256"],
                                                 "original": (cfg.get(SWITCH_WORDS) or {}).get("original")},
                               "worktree": worktree, "task": None, "base": None, "head": None,
                               "failures": {}, "claudeTasks": [], "runs": []}, action="assigned")
    return path


def start_todo_offload(module: str) -> str:
    """Decision 4: the start notice's 要你做什么 when Codex takes the Tasks."""
    from module_crew import sync
    return (f"本模块的实现交给 Codex（项目开关 codexOffload）：先{sync.STEP}"
            f"（spec/{module}.md、tasks/{module}/ 冲突时 sync 自动取集成分支的版本，它带批准标记）；"
            f"然后照 crew-dev「额度外包」一节，每个 Task 用 module-crew offload start {module} 派给 Codex、"
            f"跑完用 offload settle 核对并提交；检查点、最终验收照常由你处理")


# ------------------------------------------------------------------ what delegate printed (assumptions 4, 5; decision 7)

@dataclass
class Outcome:
    code: int
    lines: list[str]


_RESULT_RE = re.compile(r"^delegate: run_id=(\S+) status=(\S+) resumable=(true|false)$")
_RESULT_FILE = "delegate: result="
NEED_USER, TIME_UP = "NEED_USER:", "TIME_UP:"


@dataclass
class Outputs:
    run_id: str | None = None          # from the result line
    status: str | None = None
    result_path: str | None = None
    result: dict | None = None         # the result file, top-level fields only
    result_error: str | None = None
    answer: str = ""                   # stdout without the result line and the result= line before it
    stdout: str = ""
    stderr: str = ""


def read_outputs(stdout: str, stderr: str) -> Outputs:
    out = Outputs(stdout=stdout, stderr=stderr)
    lines = stdout.rstrip("\n").split("\n") if stdout.strip() else []
    m = _RESULT_RE.match(lines[-1].strip()) if lines else None
    if m:
        out.run_id, out.status = m.group(1), m.group(2)
        lines = lines[:-1]
        if lines and lines[-1].startswith(_RESULT_FILE):      # assumption 5: not always there
            out.result_path = lines[-1][len(_RESULT_FILE):].strip()
            lines = lines[:-1]
    out.answer = "\n".join(lines)
    if out.result_path is None:
        found = [x for x in stderr.splitlines() if x.startswith(_RESULT_FILE)]
        if found:
            out.result_path = found[-1][len(_RESULT_FILE):].strip()
    if out.result_path:
        try:
            doc = json.loads(Path(out.result_path).read_text(encoding="utf-8"))
            out.result = doc if isinstance(doc, dict) else None
            if out.result is None:
                out.result_error = "结果文件不是 JSON 对象"
        except (OSError, ValueError) as exc:
            out.result_error = f"结果文件读不出：{exc}"
    return out


def _after(text: str, marker: str) -> str | None:
    at = text.find(marker)
    return None if at < 0 else text[at + len(marker):].strip()


RETRY = ("unmarked", "failed", "empty")
SIGNALS = (143, 130, 129)


@dataclass
class Sorted:
    cls: str                           # done / needs-input / timeout / retry / interrupted / unreaped / refused / unknown
    status: str | None = None
    run_id: str | None = None
    reason: str = ""
    question: str | None = None


def classify(exit_code: int, out: Outputs, grant_sha: str | None) -> Sorted:
    """Decision 7: the table; anything outside it is unknown, never done."""
    doc = out.result or {}
    status = out.status or doc.get("status")
    run_id = out.run_id or doc.get("runId")
    s = lambda cls, reason="", **kw: Sorted(cls, status, run_id, reason, **kw)
    if exit_code == 64 and out.status is None and out.result is None:
        return s("refused", "delegate 拒绝了这次调用（退出码 64，没有启动 Codex）")
    if exit_code == 125:
        return s("unreaped", "delegate 回收不了 Codex 起的进程（退出码 125），它们可能还在改工作区")
    if out.result_path and out.result is None:
        return s("unknown", out.result_error or "结果文件读不出")
    if out.result is None:
        return s("unknown", f"退出码 {exit_code}，没有结果文件" + ("" if out.status else "、也没有结果行"))
    if out.status is not None and (doc.get("status") != out.status or doc.get("runId") != out.run_id):
        return s("unknown", f"结果行（{out.status}，{out.run_id}）与结果文件（{doc.get('status')}，{doc.get('runId')}）对不上")
    grant = doc.get("authorization")
    if not isinstance(grant, dict) or grant.get("sha256") != grant_sha:
        return s("unknown", "结果文件里的写入授权缺失或与授权文件的 sha256 不同")
    if exit_code in SIGNALS and status == "interrupted":
        return s("interrupted", f"运行被停下（退出码 {exit_code}）")
    if exit_code == 0 and status == "done" and out.status == "done":
        return s("done")
    if exit_code == 0 and status == "needs-input" and out.status == "needs-input":
        question = _after(out.answer, NEED_USER)
        if not question:
            return s("unknown", "status=needs-input 却没有 NEED_USER: 之后的问题")
        return s("needs-input", question=question)
    if exit_code == 124 and status == "timeout":
        return s("timeout")
    if exit_code != 0 and status in RETRY:
        return s("retry", f"Codex 没做成（status={status}，退出码 {exit_code}）")
    return s("unknown", f"认不出 delegate 的结束状态：退出码 {exit_code}，status={status}")


# ------------------------------------------------------------------ todo items and the task text

_ITEM_RE = re.compile(r"^- \[( |x|X)\] (.+?)\s*$")


def items(todo_text: str) -> list[tuple[bool, str]]:
    """(checked, text) of every todo item, in order."""
    return [(m.group(1) != " ", m.group(2)) for m in map(_ITEM_RE.match, todo_text.splitlines()) if m]


def next_item(todo_text: str) -> tuple[str, bool] | None:
    """The first unchecked item and whether it is a Task (only Tasks go to Codex)."""
    for checked, text in items(todo_text):
        if not checked:
            return text, text.startswith("Task")
    return None


def render_brief(module: str, task: str) -> str:
    """Decision 6: short, Chinese, one Task, machine-made around the Plan's own words."""
    return "\n".join([
        f"你在 module-crew 模块 {module} 的 worktree 里实现一个任务。只做这一项：{task}",
        f"先读 spec/{module}.md 与 tasks/{module}/plan.md，按它们实现；测试先写、先看到失败再实现到通过。",
        f"只改 Spec「并行边界」里的独占路径、spec/{module}.md、tasks/{module}/ 下的文件，以及 Plan「预先声明」名单内的公共文件；别的文件不要改。",
        "不要提交、不要推送、不要删除文件：改完留在工作区，由模块会话核对后提交。",
        f"这一项做完、相关测试通过后，把 tasks/{module}/todo.md 里这一项勾上（- [ ] 改成 - [x]），别的项不要动；答复首行以 DONE: 开头。",
        "先做不受待定决策影响的部分。遇到这三种情况就停下：Spec 没覆盖的决策、测试改不红、高风险不可逆改动；"
        f"停下时答复首行以 {NEED_USER} 开头，后面写要问用户的问题（写清选项与各自的影响）。",
    ]) + "\n"


LEFT_OVER = "工作区里有上次留下的改动（没提交）：先看懂这些改动，再接着把这一项做完。\n"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "--no-optional-locks", "-C", str(cwd), *args], capture_output=True, text=True,
                          timeout=probe.GIT_TIMEOUT)


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


def _approved_in(db: store.Store, approval: int, module: str) -> set[str]:
    """The nodes of module that approval C<approval> approved (S53: the start notice names them as they are)."""
    items_ = store.records(db, "item")
    return {(items_.get(str(n)) or {}).get("node") for n in (items_.get(str(approval)) or {}).get("reviews", [])
            if (items_.get(str(n)) or {}).get("module") == module}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _root(db: store.Store) -> Path:
    """The main checkout: plugins, spec-guard's /map and Codex trust are keyed on it (assumption 8 of round 1)."""
    return db.path.parent.parent


# ------------------------------------------------------------------ who may run it, which record (decision 14)

@dataclass
class Here:
    db: store.Store
    rec: dict
    name: str
    worktree: Path


def _here(cwd: str | os.PathLike, module: str) -> Here | Outcome:
    db = store.open_store(cwd)
    if not enabled(db):
        return Outcome(3, ["项目开关 codexOffload 没打开：模块会话照今天自己构建"])
    role = hooks.detect(cwd)
    if role is None or role.kind != "dev" or role.module != module:
        return Outcome(3, [f"offload 的派出与收结果只在 {module} 的模块会话 worktree 里跑（这里不是）"])
    rec = store.get(db, "offload", module)
    if rec is None or rec.get("state") == "declined":
        return Outcome(3, [f"{module} 开工时没交给 Codex：由 Claude 模块会话做完，不中途切换"])
    if rec.get("version") != VERSION:
        return Outcome(3, [f"{module} 的外包记录是旧版（第 1 轮）格式：不接着用；要外包须重新开工"])
    dev = _dev(db, module)
    return Here(db, rec, role.name, Path(dev[1]["worktree"]) if dev else Path(cwd))


def _grant_ok(rec: dict) -> str | None:
    grant = rec.get("authorization") or {}
    try:
        data = Path(grant.get("path", "")).read_bytes()
    except OSError as exc:
        return f"授权文件读不出（{exc}）"
    if hashlib.sha256(data).hexdigest() != grant.get("sha256"):
        return "授权文件的内容变了（sha256 与开工时记下的不同）"
    return None


# ------------------------------------------------------------------ dispatch (decision 5)

def _paths(db: store.Store, module: str, n: int) -> tuple[str, str]:
    base = db.path / "tmp" / f"offload-{module}-{n}"
    return f"{base}.out", f"{base}.err"


def _command(mode: str, parent: str | None, grant: str, text_file: str) -> str:
    tail = f'--write --strict --timeout {TIMEOUT} --authorized-by {grant} -- "$(cat {text_file})"'
    if mode == "resumable":
        return f"/delegate:run --write --resumable --strict --timeout {TIMEOUT} --authorized-by {grant} -- \"$(cat {text_file})\""
    return f"/delegate:run --{mode} {parent} {tail}"


def _dispatch(db: store.Store, rec: dict, task: str, base: str, mode: str, parent: str | None, text: str,
              action: str, **extra) -> list[str]:
    """Write the text, mark the record running and say what the module session runs (shared by start, resume, retries)."""
    module = rec["module"]
    with db.transaction(actor="dev") as tx:
        n = tx.allocate_number()
        meta = tx.write_body(n, text)
        text_file = str(db.path / meta["path"])
        out, err = _paths(db, module, n)
        cur = dict(tx.get("offload", module))
        runs = list(cur.get("runs") or []) + [{"n": n, "task": task, "mode": mode, "parent": parent, "startedAt": _now(),
                                               "text": text_file, "stdout": out, "stderr": err, **extra}]
        cur.update(state="running", task=task, base=base, runs=runs, head=None if mode == "continue" else cur.get("head"))
        tx.put("offload", module, cur, action=action)
    rec.clear()
    rec.update(cur)
    grant = cur["authorization"]["path"]
    return [
        f"在模块 worktree {cur['worktree']} 里执行（照 /delegate:run 的说明用 Bash 后台运行，等完成通知、不轮询；"
        f"一次最多约 {TIMEOUT + 30} 秒；标准输出存到 {out}，标准错误存到 {err}，记下退出码）：",
        f"  {_command(mode, parent, grant, text_file)}",
        f"跑完：module-crew offload settle {module} --output {out} --stderr {err} --exit <退出码>",
    ]


def _continue_note(rec: dict, worktree: Path) -> str:
    last = next((r for r in reversed(rec.get("runs") or []) if r.get("commit")), None)
    by_claude = bool(rec.get("claudeTasks")) and (last is None or rec["claudeTasks"][-1] != last.get("task"))
    head = _git(worktree, "rev-parse", "--short", "HEAD").stdout.strip()
    return f"上一项已核对并提交（{head}，由{'模块会话' if by_claude else ' Codex '}完成），先看一眼再做这一项。\n"


def start(cwd: str | os.PathLike, module: str, again: bool = False, answer: dict | None = None) -> Outcome:
    """Decision 5: hand the module's next Task to the Codex session; `again` (the user's A) starts a new chain
    for the Task that stopped, on top of what is left."""
    here = _here(cwd, module)
    if isinstance(here, Outcome):
        return here
    db, rec, worktree = here.db, here.rec, here.worktree
    why = ready(db, _root(db), module)
    if why:
        return Outcome(3, [f"外包条件不满足：{why}"])
    state = rec.get("state")
    if state == "running":
        return Outcome(3, [f"{module} 的外包正在跑：跑完先 offload settle {module}"])
    if state == "needs-input":
        return Outcome(3, [f"{module} 在等用户回答 Codex 的问题：答复到了用 offload resume {module}"])
    if state in ("stopped", "timeout") and not again:
        return Outcome(3, [f"{module} 的外包停着（{state}）：用户的答复到了再 offload start {module} --again、offload resume 或 offload takeover"])
    if again and state not in ("stopped", "timeout"):
        return Outcome(3, [f"{module} 没有停下的外包（状态 {state}）：--again 只在停下问用户之后用"])
    if again and not ((answer or {}).get("original") or "").strip():
        return Outcome(3, ["重派要用户的答复原话（--original 或 --original-file）"])
    bad = _grant_ok(rec)
    if bad:
        return Outcome(3, [f"{bad}：停下问用户，不派出"])
    approval = _approval(db, module)
    if approval is None:
        return Outcome(3, [f"{module} 的 Spec 与 Plan 还没都批准，不能外包"])
    dirty = bool(_git(worktree, "status", "--porcelain").stdout.strip())
    if dirty and not again:
        return Outcome(3, [f"{module} 的 worktree 不干净（有未提交的改动）：派下一个 Task 要从干净的工作区开始"])
    if approval[1] and _git(worktree, "merge-base", "--is-ancestor", approval[1], "HEAD").returncode != 0:
        return Outcome(3, [f"{module} 的分支还没包含批准提交 {approval[1][:7]}：先 module-crew sync"])
    if again:
        task, base = rec["task"], rec["base"]
        text = render_brief(module, task) + (LEFT_OVER if dirty else "")
        lines = _dispatch(db, rec, task, base, "resumable", None, text, "again", again=answer)
        return Outcome(0, [f"重派 {module}：{task}（另起一条 --resumable 链）", *lines])
    try:
        todo = (worktree / "tasks" / module / "todo.md").read_text(encoding="utf-8")
    except OSError as exc:
        return Outcome(3, [f"读不出 tasks/{module}/todo.md：{exc}"])
    item = next_item(todo)
    if item is None:
        return Outcome(3, [f"{module} 的 todo 已全部勾完，没有可外包的 Task"])
    if not item[1]:
        return Outcome(3, [f"{module} 的下一项不是 Task（{item[0]}）：这一项由你按 Plan 处理，勾上后再 offload start {module}"])
    if item[0] in (rec.get("claudeTasks") or []):
        return Outcome(3, [f"{item[0]} 已退回 Claude：由你自己写完、提交、勾上，再 offload start {module}"])
    head = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    mode = "continue" if rec.get("head") else "resumable"
    text = render_brief(module, item[0]) + (_continue_note(rec, worktree) if rec.get("runs") else "")
    lines = _dispatch(db, rec, item[0], head, mode, rec.get("head"), text, "started")
    how = f"接着同一个 Codex 会话（--continue {rec['runs'][-1]['parent']}）" if mode == "continue" else "起一条 --resumable 链"
    return Outcome(0, [f"外包 {module}：{item[0]}（批准事项 C{approval[0]}，基线 {head[:7]}，{how}）", *lines])


def resume(cwd: str | os.PathLike, module: str, answer: dict) -> Outcome:
    """Decision 9: carry the user's answer back to the same Codex run (needs-input, timeout)."""
    here = _here(cwd, module)
    if isinstance(here, Outcome):
        return here
    db, rec = here.db, here.rec
    if not (answer.get("original") or "").strip():
        return Outcome(3, ["续跑要用户的答复原话（--original 或 --original-file）"])
    last = (rec.get("runs") or [{}])[-1]
    if rec.get("state") not in ("needs-input", "timeout") or not last.get("runId"):
        return Outcome(3, [f"{module} 没有可续跑的外包（状态 {rec.get('state')}）：只有在等答复或超时后才续跑"])
    bad = _grant_ok(rec)
    if bad:
        return Outcome(3, [f"{bad}：停下问用户，不续跑"])
    lines = _dispatch(db, rec, rec["task"], rec["base"], "resume", last["runId"], answer["original"], "resumed", answer=answer)
    return Outcome(0, [f"续跑 {module}：{rec['task']}（delegate run {last['runId']}，带用户的答复）", *lines])


def takeover(cwd: str | os.PathLike, module: str, answer: dict) -> Outcome:
    """Decision 11: the user chose「这一项改由 Claude 写」."""
    here = _here(cwd, module)
    if isinstance(here, Outcome):
        return here
    db, rec = here.db, here.rec
    if not (answer.get("original") or "").strip():
        return Outcome(3, ["改由 Claude 写要用户的答复原话（--original 或 --original-file）"])
    if rec.get("state") not in ("stopped", "timeout", "needs-input"):
        return Outcome(3, [f"{module} 没有停下的外包（状态 {rec.get('state')}）"])
    last = (rec.get("runs") or [{}])[-1]
    with db.transaction(actor="dev") as tx:
        cur = dict(tx.get("offload", module))
        cur.update(state="idle", claudeTasks=list(cur.get("claudeTasks") or []) + [cur["task"]],
                   head=last.get("runId") if last.get("status") == "done" else None, takenOver={"task": cur["task"], **answer})
        tx.put("offload", module, cur, action="taken-over")
    return Outcome(0, [f"{rec['task']} 改由 Claude 写（用户的答复）：改动原样留在工作区，照常写完、提交、勾上，再 offload start {module} 派下一个 Task"])


# ------------------------------------------------------------------ settle (decisions 7 to 11)

def draft(name: str, module: str, decide: str, happened: str, options: list[tuple[str, str, str]]) -> list[str]:
    """A 【等待用户】 (v2.3 卡住选做法) the module session sends to the coordinator; options are (label, text, effect)."""
    lines = ["【等待用户】", "结束：无", f"来自：{name}", f"要你决定：{decide}", "要点：",
             f"出了什么事：{happened}", f"模块：{module}", "类型：卡住选做法", "选项与我的建议："]
    for i, (label, text, effect) in enumerate(options):
        lines += [f"{'推荐 ' if i == 0 else ''}{label}：{text}", f"  选了会怎样：{effect}"]
    lines += [f"你该回：{options[0][0]}", "是否完全停住：是"]
    return lines


def _options(module: str, *opts: tuple[str, str, str]) -> list[tuple[str, str, str]]:
    return [(a, b, c.replace("<模块>", module)) for a, b, c in opts]


AGAIN = ("A", "重派：另起一个 Codex 会话，在现有改动上接着做这一项",
         "用户的答复到了运行 offload start <模块> --again --original-file <答复>，再执行它给出的 /delegate:run")
GO_ON = ("A", "续跑：Codex 接着这次的进度做", "用户的答复到了运行 offload resume <模块> --original-file <答复>，再执行它给出的 /delegate:run --resume")
CLAUDE = ("B", "这一项改由 Claude 写", "运行 offload takeover <模块> --original-file <答复>，模块会话自己写完这一项，下一个 Task 照旧交给 Codex")
HOLD = ("C", "先停，我自己看", "什么都不动，改动留在模块 worktree")


def _finish(db: store.Store, module: str, state: str, rec_update: dict | None = None, **run: object) -> dict:
    with db.transaction(actor="dev") as tx:
        rec = dict(tx.get("offload", module))
        runs = list(rec.get("runs") or [])
        runs[-1] = {**runs[-1], "settledAt": _now(), **run}
        rec.update(state=state, runs=runs, **(rec_update or {}))
        tx.put("offload", module, rec, action="settled", data={"state": state})
    return rec


def _tail(text: str) -> list[str]:
    return [f"  {x}" for x in [x for x in text.splitlines() if x.strip()][-TAIL:]]


def _failed(here: Here, s: Sorted, reason: str, detail: list[str], run: dict, continuable: bool) -> Outcome:
    """Decision 10: count the miss, then retry, hand to Claude, or stop and ask the user."""
    db, rec, module = here.db, here.rec, here.rec["module"]
    task = rec["task"]
    failures = {k: list(v) for k, v in (rec.get("failures") or {}).items()}
    failures[task] = failures.get(task, []) + [reason]
    head = s.run_id if continuable else None
    if len(failures[task]) >= 2 and s.cls != "unreaped":
        claude = list(rec.get("claudeTasks") or []) + [task]
        _finish(db, module, "idle", {"failures": failures, "claudeTasks": claude, "head": head}, reason=reason, **run)
        return Outcome(4, [f"{task} 改由 Claude 写（Codex 连续 2 次没通过：{'；'.join(failures[task])}）",
                           *detail, "这句照原样告诉用户（本会话回复、任务列表、最终验收「做了什么」里都写）；不用问用户。",
                           f"改动原样留在工作区：看懂后照常写完这一项、提交、勾上，再 offload start {module} 派下一个 Task"])
    if s.cls in ("check", "retry"):
        _finish(db, module, "stopped", {"failures": failures, "head": head}, reason=reason, **run)
        here.rec = store.get(db, "offload", module)
        base_text = render_brief(module, task)
        if continuable:
            text = base_text + "上一轮核对没通过，没有提交：\n" + "\n".join([reason, *detail]) + "\n先改好这些，再按上面的要求结束。\n"
            lines = _dispatch(db, here.rec, task, rec["base"], "continue", s.run_id, text, "retried")
            how = f"--continue {s.run_id}"
        else:
            lines = _dispatch(db, here.rec, task, rec["base"], "resumable", None, base_text + LEFT_OVER, "retried")
            how = "另起一条 --resumable 链"
        return Outcome(4, [f"{task} 第 1 次没通过：{reason}", *detail, f"自动重来一次（{how}），不用问用户：", *lines])
    state = "timeout" if s.cls == "timeout" else "stopped"
    _finish(db, module, state, {"failures": failures, "head": head}, reason=reason, **run)
    first = GO_ON if s.cls == "timeout" else AGAIN
    opts = _options(module, CLAUDE, HOLD) if s.cls == "unreaped" else _options(module, first, CLAUDE, HOLD)
    return Outcome(5, [f"外包停下，没有提交、没有回滚（改动原样留在模块 worktree）：{reason}", *detail, "",
                       "把下面这份【等待用户】发给模块协调（它照现有规则转给用户）；不要替用户回答：", "",
                       *draft(here.name, module, f"{module} 的外包停在 {task}，下一步怎么办",
                              reason + ("（" + "；".join(x.strip() for x in detail if x.strip())[:300] + "）" if detail else ""),
                              opts)])


def _tick_problem(base_todo: str, now_todo: str, task: str) -> str | None:
    """Decision 8 ①: this Task ticked and no other item's state changed; item texts may change."""
    before, after = items(base_todo), items(now_todo)
    if len(before) != len(after):
        return f"todo 的条目数变了（{len(before)} → {len(after)}），认不出做完了哪一项"
    for (was, text), (now, _) in zip(before, after):
        if text == task:
            if not now:
                return f"todo 里 {task} 没勾，没认出做完"
        elif was != now:
            return f"todo 里别的条目的勾选变了：{text}"
    return None


def _scope(db: store.Store, project: Path, worktree: Path, module: str, base: str) -> tuple[list[str], list[str]] | str:
    """Decision 8 ②: (changed files, files outside the module's scope), or why scopeCheck could not tell."""
    got = _spec_guard(project)
    if isinstance(got, str):
        return got
    found, doc = got
    cmd = probe.safe_command(found.root, doc, "scopeCheck", {"<project-root>": str(worktree), "<module-id>": module,
                                                             "<base-ref>": base})
    if isinstance(cmd, str):
        return cmd
    try:
        ran = subprocess.run(cmd, cwd=found.root, capture_output=True, text=True, timeout=probe.MAP_TIMEOUT * 3)
        result = json.loads(ran.stdout) if ran.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return f"scopeCheck 没跑成（{exc}）"
    if not isinstance(result, dict) or not isinstance(result.get("files"), list):
        return f"scopeCheck 退出码 {ran.returncode}：{(ran.stderr or ran.stdout).strip()[:200]}"
    decl = None
    from module_crew import declared
    if declared.enabled(db):
        decl = declared.read(project, module)
    changed, outside = [], []
    for f in result["files"]:
        path, status, scope = f.get("path"), f.get("status"), f.get("scope")
        changed.append(path)
        if status == "D":
            outside.append(f"{path}（删除）")
        elif scope not in ("exclusive", "own") and not (decl is not None and decl.inside(path)):
            outside.append(path)
    return changed, outside


def _settle_done(here: Here, s: Sorted, run: dict) -> Outcome:
    db, rec = here.db, here.rec
    module, task, worktree, base = rec["module"], rec["task"], here.worktree, rec["base"]
    fail = lambda reason, detail=(): _failed(here, Sorted("check", s.status, s.run_id), reason, list(detail), run, True)
    rel = f"tasks/{module}/todo.md"
    base_todo = _git(worktree, "show", f"{base}:{rel}").stdout
    try:
        now_todo = (worktree / rel).read_text(encoding="utf-8")
    except OSError as exc:
        return fail(f"读不出 {rel}：{exc}")
    why = _tick_problem(base_todo, now_todo, task)
    if why:
        return fail(why)
    scoped = _scope(db, _root(db), worktree, module, base)
    if isinstance(scoped, str):
        return fail(f"核对不了改动范围（scopeCheck）：{scoped}")
    changed, outside = scoped
    if outside:
        return fail("有越界文件：" + "、".join(outside))
    add = _git(worktree, "add", "-A", "--", *changed)
    if add.returncode != 0:
        return fail(f"git add 失败：{add.stderr.strip()[:200]}")
    tree = _git(worktree, "write-tree").stdout.strip()
    cfg = store.get(db, "config", "main") or {}
    check = checks.check_tree(db, cfg, "quick", tree, worktree, "offload", None)
    if check.code != 0:
        return fail("快检查没通过" if check.code == 5 else "快检查没跑成", check.lines[-TAIL:])
    from module_crew import commits, merge
    number = task.split("：", 1)[0]
    msg = commits.message(f"{module} {number}（Codex 实现，delegate run {s.run_id}）", commits.prefix_of(db))
    try:
        done = subprocess.run(["git", "-C", str(worktree), "commit", "-q", "-m", msg], capture_output=True, text=True,
                              timeout=merge.commit_timeout(cfg))
    except subprocess.TimeoutExpired as exc:
        return fail(probe.timed_out("提交", exc))
    if done.returncode != 0:
        return fail(commits.failure(worktree, done, "提交失败"))
    commit = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    failures = {k: v for k, v in (rec.get("failures") or {}).items() if k != task}
    _finish(db, module, "idle", {"head": s.run_id, "failures": failures}, commit=commit, **run)
    nxt = next_item((worktree / rel).read_text(encoding="utf-8"))
    step = (f"下一步：module-crew offload start {module}" if nxt and nxt[1] else
            f"下一项不是 Task（{nxt[0] if nxt else '已全部勾完'}）：按 Plan 自己处理")
    return Outcome(0, [f"已提交 {commit[:7]}：{msg}", *check.lines, *commits.hook_lines(worktree, done), step])


def _progress(worktree: Path, base: str) -> list[str]:
    status = _git(worktree, "status", "--short").stdout.rstrip().splitlines()
    stat = _git(worktree, "diff", "--stat", base).stdout.rstrip().splitlines()
    return (["工作区（git status --short）："] + [f"  {x}" for x in status or ["（没有改动）"]]
            + [f"相对派出时 {base[:7]} 的改动（git diff --stat）："] + [f"  {x}" for x in stat or ["（没有已跟踪文件的改动）"]])


def settle(cwd: str | os.PathLike, module: str, output: str | os.PathLike, stderr: str | os.PathLike,
           exit_code: int) -> Outcome:
    """Read what /delegate:run printed and sort it (decision 7); never runs delegate itself."""
    here = _here(cwd, module)
    if isinstance(here, Outcome):
        return here
    rec = here.rec
    if rec.get("state") != "running":
        return Outcome(3, [f"{module} 没有正在跑的外包（状态 {rec.get('state')}）：先 offload start"])
    try:
        out = read_outputs(Path(output).read_text(encoding="utf-8"), Path(stderr).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        s = Sorted("unknown")
        return _failed(here, s, f"delegate 的输出文件读不出：{exc}", [], {"exit": exit_code, "class": "unknown"}, False)
    s = classify(exit_code, out, (rec.get("authorization") or {}).get("sha256"))
    run = {"exit": exit_code, "status": s.status, "runId": s.run_id, "class": s.cls}
    if s.cls == "done":
        return _settle_done(here, s, run)
    if s.cls == "needs-input":
        _finish(here.db, module, "needs-input", question=s.question, **run)
        task = rec["task"]
        return Outcome(5, [
            f"Codex 做 {task} 时停下来问用户（delegate run {s.run_id}）；没有提交，改动留在模块 worktree。",
            "问题原文：", s.question, "",
            "把下面这份【等待用户】发给模块协调（它照现有规则转给用户）；不要替用户回答：", "",
            *draft(here.name, module, f"回答 Codex 在 {module} {task} 上的问题", f"Codex 做 {task} 时停下来问：\n{s.question}",
                   _options(module, ("A", "回答这个问题，Codex 带着答复接着做",
                                     "你的答复原话交给 offload resume <模块> --original-file <答复>，再执行它给出的 /delegate:run --resume"),
                            CLAUDE, HOLD)),
        ])
    if s.cls == "timeout":
        progress = _progress(here.worktree, rec["base"])
        time_up = _after(out.answer, TIME_UP)
        note = ["TIME_UP: 之后的原文："] + [f"  {x}" for x in time_up.splitlines()] if time_up else []
        return _failed(here, s, f"Codex 做 {rec['task']} 超时（退出码 {exit_code}）：没有跑快检查、没有提交",
                       progress + note, run, False)
    detail = [] if s.cls == "retry" else ["delegate 输出最后几行（stdout）：", *_tail(out.stdout),
                                          "（stderr）：", *_tail(out.stderr)]
    return _failed(here, s, s.reason, detail, run, False)


# ------------------------------------------------------------------ decline (decision 3), show

def decline(project: str | os.PathLike, module: str, original: str) -> Outcome:
    """Decision 3: offloading cannot happen and the user chose the module session building as today."""
    from module_crew import protocol, review
    project = Path(project)
    db = store.open_store(project)
    if not enabled(db):
        return Outcome(3, ["项目开关 codexOffload 没打开：开工通知照今天由 review approve 发出"])
    if not original.strip():
        return Outcome(3, ["改由模块会话构建要用户原话（--original 或 --original-file）"])
    approval = _approval(db, module)
    if approval is None:
        return Outcome(3, [f"{module} 的 Spec 与 Plan 还没都批准"])
    if (store.get(db, "offload", module) or {}).get("state") not in (None, "declined"):
        return Outcome(3, [f"{module} 已经交给 Codex：不中途切换"])
    dev = _dev(db, module)
    text = protocol.render_coordination_notice(
        kind="start", basis=review.start_basis(db, module, approval[0], _approved_in(db, approval[0], module))
                            + f"，集成分支 {approval[1][:7]}；"
                            "额度外包条件不满足，用户选择由模块会话自己构建", todo=review.start_todo_today(module))
    with db.transaction(actor="coordinator") as tx:
        n = tx.allocate_number()
        meta = tx.write_body(n, text)
        tx.put("offload", module, {"module": module, "version": VERSION, "state": "declined", "approval": approval[0],
                                   "declined": {"original": original, **store.source_field(), "at": _now()}}, action="declined")
    return Outcome(0, [f"{module} 改由模块会话自己构建（照今天的开工通知）",
                       f"发送 【协调通知】 → {dev[0] if dev else '模块会话'}，正文文件：{db.path / meta['path']}"])


STATE_NAMES = {"assigned": "已交给 Codex，还没派出", "running": "Codex 在跑", "needs-input": "等用户回答 Codex 的问题",
               "timeout": "超时，等用户决定", "stopped": "停下，等用户决定", "idle": "空闲（上一项已提交）",
               "declined": "开工时改由模块会话构建"}


def show(project: str | os.PathLike, module: str | None = None) -> tuple[int, list[dict], list[str]]:
    """Read only: (exit code, records, lines)."""
    db = store.open_store(Path(project))
    recs = store.records(db, "offload")
    rows = [recs[module]] if module and module in recs else ([] if module else [recs[k] for k in sorted(recs)])
    if not rows:
        return 3, [], [f"{module or '本项目'} 没有外包记录" + ("" if enabled(db) else "（项目开关 codexOffload 没打开）")]
    lines = [] if enabled(db) else ["项目开关 codexOffload 没打开（下面是以前的记录）"]
    for r in rows:
        if r.get("version") != VERSION:
            lines.append(f"{r['module']}：旧版记录（第 1 轮），不再使用；状态 {r.get('state')}")
            continue
        runs = r.get("runs") or []
        made = [x["commit"][:7] for x in runs if x.get("commit")]
        chain = [x["runId"] for x in runs if x.get("runId")]
        lines.append(f"{r['module']}：{STATE_NAMES.get(r.get('state'), r.get('state'))}；当前项 {r.get('task') or '无'}；"
                     f"已提交 {'、'.join(made) or '无'}；共派出 {len(runs)} 次；链上 run {'→'.join(chain) or '无'}"
                     + (f"；可接 {r['head']}" if r.get("head") else ""))
        for t in r.get("claudeTasks") or []:
            why = "；".join((r.get("failures") or {}).get(t, [])) or "用户选改由 Claude 写"
            lines.append(f"  退回 Claude：{t}（{why}）")
        last = runs[-1] if runs else {}
        if r.get("state") == "needs-input":
            lines.append(f"  待答问题（delegate run {last.get('runId')}）：{last.get('question')}")
        elif r.get("state") in ("stopped", "timeout"):
            lines.append(f"  原因：{last.get('reason') or '超时'}")
    return 0, rows, lines
