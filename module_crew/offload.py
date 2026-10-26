"""Quota offload: Codex implements a module's Tasks through delegate, the coordinator checks and commits for it
(see spec/crew-codex-offload.md).

module-crew never runs delegate itself (its scripts are not an interface): `start` writes the task text and the
`/delegate:run` line for the coordinator, `settle` reads what came back. Every new behaviour needs the project switch
`codexOffload`, off unless the user turned it on.
"""

from __future__ import annotations

import json
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
    """Decision 5: hand the module's next Task to Codex; prints what the coordinator runs.
    `again` (the user's yes) re-sends after a timeout, an unknown end or a failed check, on top of what is left."""
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
    state = rec.get("state")
    if state == "running":
        return Outcome(3, [f"{module} 的外包正在跑（running）：跑完先 offload settle {module}"])
    if state == "needs-input":
        return Outcome(3, [f"{module} 的外包在等用户回答 Codex 的问题：答复到了用 offload resume {module}"])
    if state in PENDING and not again:
        return Outcome(3, [f"{module} 的外包停着（{state}）：要用户答复后再 offload start {module} --again，或 offload handback {module}"])
    if state == "handed-back" and not again:
        return Outcome(3, [f"{module} 已交还模块会话：要重新外包须用户同意后用 offload start {module} --again"])
    dirty = bool(_git(worktree, "status", "--porcelain").stdout.strip())
    if dirty and not (again and state in ("timeout", "stopped")):
        return Outcome(3, [f"{module} 的 worktree 不干净（有未提交的改动）：外包要从干净的工作区开始"])
    if approval[1] and _git(worktree, "merge-base", "--is-ancestor", approval[1], "HEAD").returncode != 0:
        return Outcome(3, [f"{module} 的分支还没包含批准提交 {approval[1][:7]}：等模块会话 module-crew sync 后发来【等待其他会话】再派"])
    head = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    if dirty or (again and state == "stopped" and rec.get("base") == head):
        task, base = rec["task"], rec["base"]          # pick up the same Task on top of what was left
    else:
        try:
            todo = (worktree / "tasks" / module / "todo.md").read_text(encoding="utf-8")
        except OSError as exc:
            return Outcome(3, [f"读不出 tasks/{module}/todo.md：{exc}"])
        item = next_item(todo)
        if item is None:
            return Outcome(3, [f"{module} 的 todo 已全部勾完，没有可外包的 Task"])
        if not item[1]:
            return Outcome(3, [f"{module} 的下一项不是 Task（{item[0]}）：不交给 Codex，用 offload handback {module} 交还模块会话"])
        task, base = item[0], head
    text = render_brief(module, task) + (LEFT_OVER if dirty else "")
    with db.transaction(actor="coordinator") as tx:
        n = tx.allocate_number()
        meta = tx.write_body(n, text)
        brief = str(db.path / meta["path"])
        out = _output_path(db, module, n)
        runs = list(rec.get("runs") or [])
        runs.append({"n": n, "task": task, "startedAt": _now(), "brief": brief, "output": out,
                     **({"again": answer} if again and answer else {})})
        tx.put("offload", module, {"module": module, "state": "running", "approval": approval[0], "task": task,
                                   "base": base, "worktree": str(worktree), "runs": runs}, action="started")
    return Outcome(0, [
        f"外包 {module}：{task}（批准事项 C{approval[0]}，基线 {base[:7]}）" + ("，接着上次留下的改动" if dirty else ""),
        f"在模块 worktree {worktree} 里执行（Bash 后台运行，timeout 600000，标准输出存到 {out}，记下退出码）：",
        f'  /delegate:run --write --resumable -- "$(cat {brief})"',
        f"跑完：module-crew offload settle {module} --output {out} --exit <退出码>",
    ])


LEFT_OVER = "工作区里有上次留下的改动（超时或停下时没提交）：先看懂这些改动，再接着把这一项做完。\n"


def _output_path(db: store.Store, module: str, n: int) -> str:
    return str(db.path / "tmp" / f"offload-{module}-{n}.out")


def resume(project: str | os.PathLike, module: str, answer: dict) -> Outcome:
    """Decisions 7, 8: carry the user's answer back to the same Codex run (needs-input; a delegate >= 1.2 timeout)."""
    project = Path(project)
    db = store.open_store(project)
    if not enabled(db):
        return Outcome(3, ["项目开关 codexOffload 没打开"])
    if not (answer.get("original") or "").strip():
        return Outcome(3, ["续跑要用户的答复原话（--original 或 --original-file）"])
    rec = store.get(db, "offload", module) or {}
    last = (rec.get("runs") or [{}])[-1]
    if rec.get("state") == "timeout" and not last.get("runId"):
        return Outcome(3, [f"这次超时没有 runId（delegate 1.1 超时不能续跑）：用户同意后用 offload start {module} --again 重派"])
    if rec.get("state") not in ("needs-input", "timeout") or not last.get("runId"):
        return Outcome(3, [f"{module} 没有可续跑的外包（状态 {rec.get('state') or '无'}）：只有在等答复或 delegate ≥ 1.2 超时时才续跑"])
    if rec["state"] == "timeout" and not delegate_interface(project).resume_timeout:
        return Outcome(3, [f"装的 delegate 不支持超时续跑：用户同意后用 offload start {module} --again 重派"])
    with db.transaction(actor="coordinator") as tx:
        n = tx.allocate_number()
        meta = tx.write_body(n, answer["original"])
        file = str(db.path / meta["path"])
        out = _output_path(db, module, n)
        runs = list(rec["runs"]) + [{"n": n, "task": rec["task"], "startedAt": _now(), "resumeOf": last["runId"],
                                     "answer": answer, "answerFile": file, "output": out}]
        tx.put("offload", module, {**rec, "state": "running", "runs": runs}, action="resumed")
    return Outcome(0, [
        f"续跑 {module}：{rec['task']}（delegate run {last['runId']}，带用户的答复）",
        f"在模块 worktree {rec['worktree']} 里执行（Bash 后台运行，timeout 600000，标准输出存到 {out}，记下退出码）：",
        f'  /delegate:run --resume {last["runId"]} --write -- "$(cat {file})"',
        f"跑完：module-crew offload settle {module} --output {out} --exit <退出码>",
    ])


# ------------------------------------------------------------------ settle (decisions 6 to 9)

def _coordinator_name(db: store.Store) -> str:
    return next((n for n, r in store.records(db, "session").items()
                 if r.get("role") == "coordinator" and r.get("status") == "active"), "模块协调")


def draft(db: store.Store, module: str, decide: str, happened: str, options: list[tuple[str, str, str]]) -> list[str]:
    """A 【等待用户】 (v2.3 卡住选做法) for the coordinator to send on; options are (label, text, effect), first recommended."""
    lines = ["【等待用户】", "结束：无", f"来自：{_coordinator_name(db)}", f"要你决定：{decide}", "要点：",
             f"出了什么事：{happened}", f"模块：{module}", "类型：卡住选做法", "选项与我的建议："]
    for i, (label, text, effect) in enumerate(options):
        lines += [f"{'推荐 ' if i == 0 else ''}{label}：{text}", f"  选了会怎样：{effect}"]
    lines += [f"你该回：{options[0][0]}", "是否完全停住：是"]
    return lines


AGAIN = ("A", "重派：在现有改动上让 Codex 接着做这一项", "用户答复后运行 offload start <模块> --again --original-file <答复>，再执行它给出的 /delegate:run")
BACK = ("B", "交还模块会话自己做", "运行 offload handback <模块>，模块会话按 Plan 接着做，之后不再外包这个模块")
HOLD = ("C", "先停，我自己看", "什么都不动，改动留在模块 worktree")


def _options(module: str, *opts: tuple[str, str, str]) -> list[tuple[str, str, str]]:
    return [(a, b, c.replace("<模块>", module)) for a, b, c in opts]


def _finish(db: store.Store, module: str, state: str, **run: object) -> dict:
    with db.transaction(actor="coordinator") as tx:
        rec = dict(tx.get("offload", module))
        runs = list(rec.get("runs") or [])
        runs[-1] = {**runs[-1], "settledAt": _now(), **run}
        rec.update(state=state, runs=runs)
        tx.put("offload", module, rec, action="settled", data={"state": state})
    return rec


def _stop(db: store.Store, module: str, task: str, reason: str, detail: list[str], **run: object) -> Outcome:
    _finish(db, module, "stopped", reason=reason, **run)
    head = [f"外包停下，没有提交、没有回滚（改动原样留在模块 worktree）：{reason}"] + detail
    return Outcome(5, head + ["", "把下面这份【等待用户】交用户决定（有决策收件箱就照现有规则转给它）：", ""]
                   + draft(db, module, f"{module} 的外包停在 {task}，下一步怎么办", f"{reason}"
                           + ("（" + "；".join(x.strip() for x in detail if x.strip())[:300] + "）" if detail else ""),
                           _options(module, AGAIN, BACK, HOLD)))


def _tick_problem(base_todo: str, now_todo: str, task: str) -> str | None:
    """Decision 6 ①: this Task ticked and no other item's state changed; item texts may change."""
    before, after = items(base_todo), items(now_todo)
    if len(before) != len(after):
        return f"todo 的条目数变了（{len(before)} → {len(after)}），认不出做完了哪一项"
    for (was, text), (now, _) in zip(before, after):
        if text == task:
            if not now:
                return f"todo 里 {task} 没勾，没认出做完（可能漏写了 NEED_USER:）"
        elif was != now:
            return f"todo 里别的条目的勾选变了：{text}"
    return None


def _scope(db: store.Store, project: Path, worktree: Path, module: str, base: str) -> tuple[list[str], list[str]] | str:
    """Decision 6 ②: (changed files, files outside the module's scope), or why scopeCheck could not tell."""
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


def _settle_done(db: store.Store, project: Path, rec: dict, result: Result, exit_code: int) -> Outcome:
    module, task, worktree, base = rec["module"], rec["task"], Path(rec["worktree"]), rec["base"]
    run = {"exit": exit_code, "status": result.status, "runId": result.run_id}
    rel = f"tasks/{module}/todo.md"
    base_todo = _git(worktree, "show", f"{base}:{rel}").stdout
    try:
        now_todo = (worktree / rel).read_text(encoding="utf-8")
    except OSError as exc:
        return _stop(db, module, task, f"读不出 {rel}：{exc}", [], **run)
    why = _tick_problem(base_todo, now_todo, task)
    if why:
        return _stop(db, module, task, why, [], **run)
    scoped = _scope(db, project, worktree, module, base)
    if isinstance(scoped, str):
        return _stop(db, module, task, f"核对不了改动范围（scopeCheck）：{scoped}", [], **run)
    changed, outside = scoped
    if outside:
        return _stop(db, module, task, "有越界文件：" + "、".join(outside), [], **run)
    add = _git(worktree, "add", "-A", "--", *changed)
    if add.returncode != 0:
        return _stop(db, module, task, f"git add 失败：{add.stderr.strip()[:200]}", [], **run)
    tree = _git(worktree, "write-tree").stdout.strip()
    cfg = store.get(db, "config", "main") or {}
    check = checks.check_tree(db, cfg, "quick", tree, worktree, "offload", None)
    if check.code != 0:
        return _stop(db, module, task, "快检查没通过" if check.code == 5 else "快检查没跑成", check.lines, **run)
    from module_crew import commits, merge
    number = task.split("：", 1)[0]
    msg = commits.message(f"Codex 外包 {module} {number}（delegate run {result.run_id}）", commits.prefix_of(db))
    try:
        done = subprocess.run(["git", "-C", str(worktree), "commit", "-q", "-m", msg], capture_output=True, text=True,
                              timeout=merge.commit_timeout(cfg))
    except subprocess.TimeoutExpired as exc:
        return _stop(db, module, task, probe.timed_out("代提交", exc), [], **run)
    if done.returncode != 0:
        return _stop(db, module, task, commits.failure(worktree, done, "代提交失败"), [], **run)
    commit = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    _finish(db, module, "idle", commit=commit, **run)
    nxt = next_item((worktree / rel).read_text(encoding="utf-8"))
    step = ("下一步：module-crew offload start " + module if nxt and nxt[1] else
            f"下一项不是 Task（{nxt[0] if nxt else '已全部勾完'}）：module-crew offload handback {module} 交还模块会话")
    return Outcome(0, [f"已代提交 {commit[:7]}：{msg}", *check.lines, *commits.hook_lines(worktree, done), step])


def settle(project: str | os.PathLike, module: str, output: str | os.PathLike, exit_code: int) -> Outcome:
    """Read what /delegate:run printed and sort it (assumption 6); never runs delegate itself."""
    project = Path(project)
    db = store.open_store(project)
    if not enabled(db):
        return Outcome(3, ["项目开关 codexOffload 没打开"])
    rec = store.get(db, "offload", module)
    if not rec or rec.get("state") != "running":
        return Outcome(3, [f"{module} 没有正在跑的外包（状态 {(rec or {}).get('state') or '无'}）：先 offload start"])
    try:
        text = Path(output).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return _unknown(db, rec, f"delegate 的输出文件读不出：{exc}", "", exit_code)
    result = parse_result(text, exit_code, delegate_interface(project).resume_timeout)
    if result.kind == "done":
        return _settle_done(db, project, rec, result, exit_code)
    if result.kind == "needs-input":
        return _needs_input(db, rec, result, exit_code)
    if result.kind == "timeout":
        return _timeout(db, rec, result, text, exit_code)
    return _unknown(db, rec, f"认不出 delegate 的结束状态：{result.reason or result.kind}", text, exit_code,
                    runId=result.run_id, status=result.status)


TAIL = 20


def _unknown(db: store.Store, rec: dict, reason: str, text: str, exit_code: int, **run: object) -> Outcome:
    tail = [x for x in text.splitlines() if x.strip()][-TAIL:]
    return _stop(db, rec["module"], rec["task"], reason, ["delegate 输出最后几行："] + [f"  {x}" for x in tail] if tail else [],
                 exit=exit_code, **run)


def _needs_input(db: store.Store, rec: dict, result: Result, exit_code: int) -> Outcome:
    """Decision 7: the question goes to the user word for word; the coordinator never answers it."""
    module, task = rec["module"], rec["task"]
    _finish(db, module, "needs-input", exit=exit_code, status=result.status, runId=result.run_id, question=result.question)
    return Outcome(5, [
        f"Codex 做 {task} 时停下来问用户（delegate run {result.run_id}）；没有提交，改动留在模块 worktree。",
        "问题原文：", result.question, "",
        "把下面这份【等待用户】交用户决定（有决策收件箱就照现有规则转给它）；不要替用户回答：", "",
        *draft(db, module, f"回答 Codex 在 {module} {task} 上的问题",
               f"Codex 做 {task} 时停下来问：\n{result.question}",
               _options(module, ("A", "回答这个问题，Codex 带着答复接着做",
                                 "你的答复原话交给 offload resume <模块> --original-file <答复>，再执行它给出的 /delegate:run --resume"),
                        BACK, HOLD)),
    ])


def _progress(worktree: Path, base: str) -> list[str]:
    status = _git(worktree, "status", "--short").stdout.rstrip().splitlines()
    stat = _git(worktree, "diff", "--stat", base).stdout.rstrip().splitlines()
    return (["工作区（git status --short）："] + [f"  {x}" for x in status or ["（没有改动）"]]
            + [f"相对派出时 {base[:7]} 的改动（git diff --stat）："] + [f"  {x}" for x in stat or ["（没有已跟踪文件的改动）"]])


def _timeout(db: store.Store, rec: dict, result: Result, text: str, exit_code: int) -> Outcome:
    """Decision 8: no quick check, no commit; the progress goes to the user, who decides whether to go on."""
    module, task = rec["module"], rec["task"]
    _finish(db, module, "timeout", exit=exit_code, status=result.status or "timeout", runId=result.run_id)
    progress = _progress(Path(rec["worktree"]), rec["base"])
    note = []
    if result.run_id:                              # delegate >= 1.2: its progress note, passed on as written
        raw = text.rstrip()
        body = raw[:raw.rfind("delegate: run_id=")].strip()
        note = ["delegate 的进度说明（原样）："] + [f"  {x}" for x in body.splitlines()]
        go_on = ("A", "续跑：Codex 接着这次超时的进度做", "你的答复原话交给 offload resume <模块> --original-file <答复>，再执行它给出的 /delegate:run --resume")
    else:
        go_on = ("A", "重派：在已有改动上让 Codex 从头接着做这一项（delegate 1.1 超时后不能续跑）",
                 "用户答复后运行 offload start <模块> --again --original-file <答复>，再执行它给出的 /delegate:run")
    return Outcome(5, [
        f"Codex 做 {task} 超时（退出码 {exit_code}）：没有跑快检查、没有提交，改到一半的文件留在模块 worktree。",
        *progress, *note, "",
        "把下面这份【等待用户】交用户决定；续跑要用户点头，不自动续跑：", "",
        *draft(db, module, f"{module} 的外包在 {task} 超时，下一步怎么办",
               f"Codex 做 {task} 超时；" + "；".join(x.strip() for x in progress[1:4] if x.strip())[:200],
               _options(module, go_on, BACK, HOLD)),
    ])


# ------------------------------------------------------------------ start notice, decline, hand back (decisions 4, 10)

def start_todo_offload(module: str) -> str:
    """Decision 4: the start notice's 要你做什么 when Codex takes the Tasks."""
    from module_crew import sync
    return (f"本模块的实现外包给 Codex（项目开关 codexOffload）：先{sync.STEP}"
            f"（spec/{module}.md、tasks/{module}/ 冲突时 sync 自动取集成分支的版本，它带批准标记），然后不构建、不改本 worktree；"
            "发一条【等待其他会话】给模块协调（在等谁：模块协调；等什么：Codex 外包实现）后停下；外包期间收到同步基线通知先不同步。"
            "做到检查点或最终验收时模块协调会发恢复通知交还给你。")


def _dev_name(db: store.Store, module: str) -> str | None:
    return next((n for n, r in store.records(db, "session").items()
                 if r.get("role") == "dev" and r.get("module") == module and r.get("status") == "active"), None)


def _notice(db: store.Store, module: str, kind: str, basis: str, todo: str, state: str, extra: dict) -> Outcome:
    from module_crew import protocol
    to = _dev_name(db, module)
    text = protocol.render_coordination_notice(kind=kind, basis=basis, todo=todo)
    with db.transaction(actor="coordinator") as tx:
        n = tx.allocate_number()
        meta = tx.write_body(n, text)
        rec = dict(tx.get("offload", module) or {"module": module, "runs": []})
        rec.update(state=state, **extra)
        tx.put("offload", module, rec, action=state)
    return Outcome(0, [f"发送 【协调通知】 → {to}，正文文件：{db.path / meta['path']}"])


def decline(project: str | os.PathLike, module: str, original: str) -> Outcome:
    """Decision 4: offloading cannot happen and the user chose the module session building as today."""
    from module_crew import review
    project = Path(project)
    db = store.open_store(project)
    if not enabled(db):
        return Outcome(3, ["项目开关 codexOffload 没打开：开工通知照今天由 review approve 发出"])
    if not original.strip():
        return Outcome(3, ["改由模块会话构建要用户原话（--original 或 --original-file）"])
    approval = _approval(db, module)
    if approval is None:
        return Outcome(3, [f"{module} 的 Spec 与 Plan 还没都批准"])
    if (store.get(db, "offload", module) or {}).get("runs"):
        return Outcome(3, [f"{module} 已经外包过：要交还模块会话用 offload handback {module}"])
    out = _notice(db, module, "start", f"用户批准事项 C{approval[0]}（{module} 的 Spec 与 Plan），集成分支 {approval[1][:7]}；"
                  "额度外包条件不满足，用户选择由模块会话自己构建", review.start_todo_today(module), "handed-back",
                  {"approval": approval[0], "declined": {"original": original, **store.source_field(), "at": _now()}})
    return Outcome(0, [f"{module} 改由模块会话自己构建（照今天的开工通知）", *out.lines])


def handback(project: str | os.PathLike, module: str) -> Outcome:
    """Decision 10: a checkpoint, the final acceptance, or the user's B: the module session takes over again."""
    project = Path(project)
    db = store.open_store(project)
    if not enabled(db):
        return Outcome(3, ["项目开关 codexOffload 没打开"])
    rec = store.get(db, "offload", module)
    if not rec or not rec.get("runs"):
        return Outcome(3, [f"{module} 没有外包过，没有可交还的"])
    if rec["state"] == "running":
        return Outcome(3, [f"{module} 的外包正在跑：跑完先 offload settle {module}"])
    if rec["state"] == "handed-back":
        return Outcome(3, [f"{module} 已经交还过模块会话"])
    worktree = Path(rec["worktree"])
    if rec["state"] == "idle":
        try:
            item = next_item((worktree / "tasks" / module / "todo.md").read_text(encoding="utf-8"))
        except OSError as exc:
            return Outcome(3, [f"读不出 tasks/{module}/todo.md：{exc}"])
        at, state = (item[0] if item else "todo 末尾"), "idle"
    else:
        at, state = f"{rec['task']}（{rec['state']}，用户选交还）", "handed-back"
    made = [r["commit"] for r in rec["runs"] if r.get("commit")]
    span = f"{made[0][:7]}…{made[-1][:7]}（{len(made)} 个）" if made else "无"
    more = ("做完检查点、还有 Task 时再发【等待其他会话】，模块协调接着外包" if state == "idle" else
            "之后本模块不再外包，按 Plan 自己做完剩下的项")
    todo = (f"外包已停在 {at}：先 module-crew sync，对照 Spec 看一遍 Codex 的提交（{span}）"
            + ("，工作区里留着 Codex 没提交的改动，看懂后自己决定怎么处理" if state == "handed-back"
               and _git(worktree, "status", "--porcelain").stdout.strip() else "")
            + f"，再按 Plan 处理这一项（检查点照 gate／report 规则、最终验收照常交审）；{more}。"
            "然后自己发【已恢复】结项你那张等待记录。")
    out = _notice(db, module, "resume", f"用户批准事项 C{rec['approval']}（{module} 的 Spec 与 Plan）；外包提交 {span}",
                  todo, state, {"handedBackAt": _now()})
    return Outcome(0, [f"交还 {module} 的模块会话：停在 {at}", *out.lines])


# ------------------------------------------------------------------ show (decision 12)

STATE_NAMES = {"running": "Codex 在跑", "needs-input": "等用户回答 Codex 的问题", "timeout": "超时，等用户决定",
               "stopped": "停下，等用户决定", "idle": "空闲（上一项已代提交）", "handed-back": "已交还模块会话"}


def show(project: str | os.PathLike, module: str | None = None) -> tuple[int, list[dict], list[str]]:
    """Read only: (exit code, records, lines)."""
    db = store.open_store(Path(project))
    recs = store.records(db, "offload")
    rows = [recs[module]] if module and module in recs else ([] if module else [recs[k] for k in sorted(recs)])
    if not rows:
        return 3, [], [f"{module or '本项目'} 没有外包记录" + ("" if enabled(db) else "（项目开关 codexOffload 没打开）")]
    lines = [] if enabled(db) else ["项目开关 codexOffload 没打开（下面是以前的记录）"]
    for r in rows:
        runs = r.get("runs") or []
        made = [x["commit"][:7] for x in runs if x.get("commit")]
        lines.append(f"{r['module']}：{STATE_NAMES.get(r.get('state'), r.get('state'))}；当前项 {r.get('task') or '无'}；"
                     f"已代提交 {'、'.join(made) or '无'}；共派出 {len(runs)} 次")
        last = runs[-1] if runs else {}
        if r.get("state") == "needs-input":
            lines.append(f"  待答问题（delegate run {last.get('runId')}）：{last.get('question')}")
        elif r.get("state") in ("stopped", "timeout"):
            lines.append(f"  原因：{last.get('reason') or '超时'}")
    return 0, rows, lines
