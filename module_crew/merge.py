"""Local merge queue and remote hand-off (see spec/crew-merge.md).

Approved final acceptances are merged into the local integration branch one at a time with
--no-ff and checked; failures are reset away (or aborted) and the module is sent back. Pushing
goes to a new remote branch and a PR the user merges.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from module_crew import commits, probe, protocol, store, sync
from module_crew.inbox import AnswerRefused, Reply
from module_crew.review import _reply_text, closing, closing_all

DEFAULT_CHECK_TIMEOUT = 1800
_SHELL_OPS = ("&&", "||", ";", "|", ">", "<", "`", "$(")   # S30: the check runs without a shell
CANNOT_RUN = "完整检查跑不起来"


@dataclass
class Approved:
    approval: int
    reply: Reply
    superseded: list[int] = field(default_factory=list)   # the module's older open approvals this one replaced (MC-11)


def approve(db: store.Store, review_no: int, original: str) -> Approved:
    """Record the user's approval of a final acceptance and queue the module for a local merge."""
    return approve_many(db, [review_no], original)[0]


def approve_many(db: store.Store, numbers: list[int], original: str) -> list[Approved]:
    """approve() for several final acceptances at once; any refusal writes nothing."""
    with db.transaction(actor="coordinator") as tx:
        return [_approve_one(tx, db, n, original) for n in numbers]


def _approve_one(tx, db: store.Store, review_no: int, original: str) -> Approved:
    rec = tx.get("item", str(review_no))
    if rec is None or rec.get("kind") != "review":
        raise AnswerRefused(f"没有交审事项 C{review_no}")
    if rec.get("node") != "final":
        raise AnswerRefused(f"交审事项 C{review_no} 不是最终验收（Spec／Plan 用 review approve）")
    if rec.get("state") != "open":
        raise AnswerRefused(f"交审事项 C{review_no} 已关闭（{rec.get('closedReason')}）")
    answered_at = store.now()
    text = _reply_text(review_no, rec, original, answered_at)
    approval = tx.allocate_number()
    replaced = []
    for key, old in sorted(tx.records("item").items(), key=lambda kv: int(kv[0])):
        if (old.get("kind") == "merge-approval" and old.get("state") == "open" and old.get("module") == rec["module"]
                and old.get("task") == rec.get("task")):
            tx.put("item", key, dict(old, state="closed", closedReason="superseded", supersededBy=approval),
                   action="superseded", data={"by": approval})
            replaced.append(int(key))
    tx.put("item", str(approval), {
        "state": "open", "kind": "merge-approval", "module": rec["module"], "task": rec.get("task"), "review": review_no,
        "specRevisionApproved": bool(rec.get("specRevised")),   # decision 10: one approval covers the revised Spec
        "commit": rec["commit"], "from": rec["from"], "relayId": rec["relayId"],
        "answer": {"original": original, "answeredAt": answered_at, **store.source_field()},
        "closedReason": None, "mergeCommit": None, "revertCommit": None, "resetTo": None, "reason": None,
    }, action="merge-approved")
    body = tx.allocate_number()
    meta = tx.write_body(body, text)
    tx.put("item", str(review_no), dict(rec, state="closed", closedReason="answered",
                                        answer={"original": original, "answeredAt": answered_at, **store.source_field(), "body": body,
                                                "approval": approval}),
           action="answered", data={"body": body})
    return Approved(approval, Reply(rec["from"], rec["relayId"], body, db.path / meta["path"]), replaced)


def awaiting_final(tx) -> set[str]:
    """Modules with an open final-acceptance submission: syncing now would void the approval they wait for (MC-10)."""
    return {v.get("module") for v in tx.records("item").values()
            if v.get("kind") == "review" and v.get("node") == "final" and v.get("state") == "open"}


def no_sync(tx) -> set[str]:
    """Modules that get no sync-baseline notice now, the one rule for `merge run` and `change land` (0.9.3):
    an open or merged merge approval (syncing voids it or is pointless), an open final review (MC-10), or suspended
    (resume says what happened meanwhile)."""
    sessions = tx.records("session")
    approved = {v.get("module") for k, v in tx.records("item").items() if v.get("kind") == "merge-approval"
                and (v.get("state") == "open" or v.get("closedReason") == "merged")
                and int(k) > store.round_since(sessions, v.get("module"))}   # crew-reopen-module: this round only
    suspended = {s.get("module") for s in tx.records("session").values() if s.get("role") == "dev" and s.get("suspended")}
    return approved | awaiting_final(tx) | suspended


def sync_targets(tx, exclude: str | None = None) -> list[tuple[str, int | None]]:
    """Who gets a sync-baseline notice now: in-use module sessions outside `no_sync`, and light tasks being worked on
    (with their task number). One list for `merge run` and `unqueued --notify` (crew-unqueued-commits)."""
    skip = no_sync(tx)
    out = []
    for name, s in sorted(tx.records("session").items()):
        if s.get("status") != "active" or name == exclude:
            continue
        if s.get("role") == "dev" and s.get("module") not in skip:     # a suspended module is told on resume
            out.append((name, None))
        elif s.get("role") == "task" and (tx.get("task", str(s.get("task"))) or {}).get("state") == "working":
            out.append((name, s.get("task")))
    return out


@dataclass(frozen=True)
class Revoked(Reply):
    superseded_by: int | None = None          # the newer submission that keeps the old one closed (MC-6)


REVOKE_TODO = "最终验收批准已撤回，不会合并：停在当前停点，不要再提交，等新的答复"


def revoke(db: store.Store, approval: int, original: str) -> Revoked:
    """Take back a merge approval before `merge run` (R5): close it, reopen the final review unless a newer
    submission of the same module and node replaced it (MC-6), notify the module."""
    if not original or not original.strip():
        raise AnswerRefused("用户原话不能为空：撤回批准要用户明确说")
    with db.transaction(actor="coordinator") as tx:
        rec = tx.get("item", str(approval))
        if rec is None or rec.get("kind") != "merge-approval":
            raise AnswerRefused(f"没有合并批准事项 C{approval}")
        if rec.get("closedReason") == "merged":
            raise AnswerRefused(f"C{approval} 已合并进集成分支，撤不回；要回退请另走回退流程")
        if rec.get("state") != "open":
            raise AnswerRefused(f"C{approval} 已关闭（{rec.get('closedReason')}），不能撤回")
        record = tx.allocate_number()
        tx.put("item", str(record), {"state": "closed", "kind": "revoke", "closedReason": "answered", "approval": approval,
                                     "module": rec["module"],
                                     "answer": {"original": original, "answeredAt": store.now(), **store.source_field()}},
               action="revoke-approved")
        tx.put("item", str(approval), dict(rec, state="closed", closedReason="revoked", revokedBy=record), action="revoked")
        review = tx.get("item", str(rec["review"]))
        newer = [int(k) for k, v in tx.records("item").items()
                 if v.get("kind") == "review" and v.get("module") == review["module"] and v.get("node") == review["node"]
                 and int(k) > int(rec["review"])]
        if not newer:
            tx.put("item", str(rec["review"]), dict(review, state="open", closedReason=None, answer=None), action="reopened",
                   data={"revokedApproval": approval})
        body = tx.allocate_number()
        meta = tx.write_body(body, protocol.render_coordination_notice(
            "approval-revoked", f"C{approval}（用户撤回批准 C{record}；交审 C{rec['review']}）", REVOKE_TODO))
    return Revoked(rec["from"], None, body, db.path / meta["path"], superseded_by=max(newer) if newer else None)


def _build_order(project: Path) -> list[str] | None:
    report = probe.run(project)
    if not report.map:
        return None
    return [m.get("id") for m in report.map.get("modules") or [] if isinstance(m, dict)]


def queue(project: str | os.PathLike) -> list[tuple[int, dict]]:
    """Open merge approvals in Build order (approval number when /map is unavailable)."""
    project = Path(project)
    db = store.open_store(project)
    rows = [(int(k), v) for k, v in store.records(db, "item").items()
            if v.get("kind") == "merge-approval" and v.get("state") == "open"]
    order = _build_order(project) or []
    pos = {m: i for i, m in enumerate(order)}
    kinds = {k: v.get("type") for k, v in store.records(db, "task").items()}

    def key(kv):        # crew-light-task: bug tasks, then modules in Build order, then feature tasks
        n, v = kv
        if v.get("task"):
            return (0 if kinds.get(str(v["task"])) == "bug" else 2, 0, n)
        return (1, pos.get(v["module"], len(pos)), n)
    return sorted(rows, key=key)


@dataclass
class RunResult:
    code: int                 # 0 merged / 2 no check command / 3 checklist failed or empty queue / 4 reset refused or failed / 5 returned
    lines: list[str] = field(default_factory=list)
    approval: int | None = None
    merge_commit: str | None = None
    sends: list[dict] = field(default_factory=list)    # {"to", "kind", "body", "path"}


def _git(cwd: Path, *args: str):
    return probe._git(cwd, *args)


def _clean(path: Path) -> bool:
    return _git(path, "--no-optional-locks", "status", "--porcelain").stdout.strip() == ""


def _check_config(db: store.Store, check_command: str | None, replace: bool) -> tuple[dict, list[str], bool]:
    """(config to use, refusal reasons, whether the new command still has to be written)."""
    cfg = store.get(db, "config", "main") or {}
    current = cfg.get("checkCommand")
    if check_command is None:
        return cfg, ([] if current else ["还没有完整检查命令：第一次运行请加 --check-command \"<命令>\"（取自项目 Spec 的 Commands 一节）"]), False
    if current and check_command != current and not replace:
        return cfg, [f"完整检查命令已定为「{current}」，要改成「{check_command}」须用户明确同意后加 --replace-check"], False
    try:
        argv = shlex.split(check_command)
    except ValueError as exc:
        return cfg, [f"检查命令拆不开：{exc}"], False
    if check_command != current:        # S30: checked when written only; a stored command is not refused afterwards
        bad = next((t for t in argv if t.startswith(_SHELL_OPS) or t.endswith(_SHELL_OPS)), None)
        if bad is not None:
            return cfg, [f"检查命令里有 shell 运算符（「{bad}」）：module-crew 不经 shell 执行检查命令，运算符会被当成普通参数。"
                         f"改用两种写法之一：把这些步骤写进项目脚本，检查命令写这个脚本；或写成 /bin/sh -c '<原命令>'"], False
    new = dict(cfg, checkCommand=check_command)
    new.setdefault("checkTimeout", DEFAULT_CHECK_TIMEOUT)
    return new, [], check_command != current


def _write_config(db: store.Store, cfg: dict) -> None:
    with db.transaction(actor="coordinator") as tx:
        previous = (tx.get("config", "main") or {}).get("checkCommand")
        tx.put("config", "main", cfg, action="set", data={"previousCheckCommand": previous})


def _run_check(cfg: dict, checkout: Path) -> str | None:
    """None when the full check passes, else the reason; a reason starting with CANNOT_RUN means it never ran."""
    timeout = cfg.get("checkTimeout") or DEFAULT_CHECK_TIMEOUT
    argv = shlex.split(cfg["checkCommand"])
    shown = json.dumps(argv, ensure_ascii=False)
    try:
        done = subprocess.run(argv, cwd=checkout, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"完整检查超时（{timeout} 秒）"
    except OSError as exc:
        return f"{CANNOT_RUN}（实际执行的参数：{shown}）：{exc}"
    tail = "\n".join((done.stdout + done.stderr).strip().splitlines()[-40:])
    if done.returncode in (126, 127):       # the shell could not find or execute the program
        return f"{CANNOT_RUN}（退出码 {done.returncode}；实际执行的参数：{shown}）：{tail}"
    if done.returncode != 0:
        return f"完整检查失败（退出码 {done.returncode}；实际执行的参数：{shown}）：{tail}"
    return None


_FAILED = re.compile(r"^(FAIL|ERROR|FAILED)\b")
ENV_TODO = "失败与你的代码无关，不用改代码；等模块协调告诉你检查环境恢复后，用原提交重新发最终验收【交审】"
MODULE_TODO = "同步集成分支、修好后重新发最终验收【交审】"


def _return_kind(reason: str) -> str:
    """R20⑤: `env` when the full check ran out of time, `module` when it ran and failed or conflicted
    (a check that could not run at all is not returned, S30)."""
    if reason.startswith("完整检查超时"):
        return "env"
    return "module"


def _failed_lines(reason: str) -> str:
    """The test runner's FAIL/ERROR lines (at most 5), so the module sees which check failed."""
    hits = [line.strip() for line in reason.splitlines()[1:] if _FAILED.match(line.strip())][:5]
    return f"（{'；'.join(hits)}）" if hits else ""


def _notice(tx, db: store.Store, result: RunResult, to: str, kind: str, basis: str, todo: str,
            task: int | None = None) -> None:
    text = protocol.render_coordination_notice(kind=kind, basis=basis, todo=todo, task=f"T{task}" if task else None)
    body = tx.allocate_number()
    meta = tx.write_body(body, text)
    result.sends.append({"to": to, "kind": kind, "body": body, "path": db.path / meta["path"]})


def run(project: str | os.PathLike, check_command: str | None = None, replace: bool = False,
        detach: bool = False, adopted=None) -> RunResult:
    """Merge the head of the queue, run the full check, and reset or abort on failure.

    crew-background-checks: one merge at a time — the merge lock is taken before anything is touched and always let go.
    crew-codex-coordinator: `detach` hands the merge, lock and all, to a child process once the lock is taken and
    returns at once; that child runs this again with the lock it was given (`adopted`)."""
    from module_crew import mergelock
    project = Path(project)
    db = store.open_store(project)
    rows = queue(project)
    note = None
    if not rows:
        if adopted is not None:
            mergelock.release(db, adopted)
        return RunResult(3, ["合并队列是空的"])
    if adopted is None and (mergelock.read(db) is not None or mergelock.locked(db)):
        reason, note = mergelock.guard(db, project)
        if reason:
            return RunResult(6, [reason])
    holder: dict = {"lock": adopted, "detach": detach, "args": (check_command, replace)}
    try:
        result = _run(project, check_command, replace, holder)
    finally:
        if holder.get("lock"):
            mergelock.release(db, holder["lock"])
    if note:
        result.lines.insert(0, note)
    return result


LOCK_FD_ENV = "MODULE_CREW_MERGE_LOCK_FD"
LOG_ENV = "MODULE_CREW_MERGE_LOG"


def log_path(db: store.Store, approval: int) -> Path:
    return db.path / "merge-output" / f"C{approval}.log"


def _hand_off(project: Path, db: store.Store, n: int, unit: str, lock, check_command: str | None,
              replace: bool) -> RunResult:
    """crew-codex-coordinator decision 6: Codex cannot wake the coordinator when a background command ends, so the
    merge goes on in a child of its own session (the lock passes with it) and its output lands in the store."""
    from module_crew import mergelock
    log = log_path(db, n)
    log.parent.mkdir(exist_ok=True)
    argv = [str(probe.RUNNING_ROOT / "bin" / "module-crew"), "merge", "run", "--detached-child"]
    if check_command:
        argv += ["--check-command", check_command]
    if replace:
        argv.append("--replace-check")
    mergelock.mark_detached(db)
    env = {**os.environ, LOCK_FD_ENV: str(lock.fd), LOG_ENV: str(log)}
    with open(log, "wb") as out:
        subprocess.Popen(argv, cwd=project, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                         pass_fds=(lock.fd,), start_new_session=True)
    mergelock.hand_off(lock)
    with db.transaction(actor="merge") as tx:
        rec = tx.get("item", str(n)) or {}
        tx.put("item", str(n), {**rec, "detached": {"log": str(log), "at": store.now()}}, action="merge-detached")
    return RunResult(0, [f"合并 C{n}（{unit}）已交给后台运行，输出写在 {log}",
                         f"跑完后运行 module-crew merge result C{n} 取结果与通知（还在跑时退出码 6，可加 --wait <分钟> 分段等）"],
                     approval=n)


RESULT_WAIT_MAX = 8      # minutes one `merge result --wait` may block: one tool call in Codex stays short
RESULT_POLL = 5          # seconds between looks while waiting
RESULT_LATE = 60         # seconds a finished child may take to write its result before it counts as lost


@dataclass
class Result:
    code: int                 # the detached merge's own exit code / 6 still running / 3 nothing to read
    lines: list[str] = field(default_factory=list)
    info: dict | None = None
    output: str | None = None


def _result_state(db: store.Store, approval: int | None) -> tuple[str, dict | None]:
    """("none" | "running" | "lost" | "done", record) for the last detached merge (or `approval`)."""
    from module_crew import mergelock
    info = mergelock.last(db)
    if not info or not info.get("detached") or (approval is not None and info.get("approval") != approval):
        return "none", info
    if "exitCode" in info:
        return "done", info
    if mergelock.locked(db):
        return "running", info
    if info.get("running"):
        return "lost", info                      # the child is gone with the lock: a stale lock (crew-background-checks)
    late = mergelock.minutes({"startedAt": info.get("endedAt")})
    return ("lost" if late is not None and late * 60 >= RESULT_LATE else "running"), info


def result(db: store.Store, approval: int | None = None, wait: float = 0) -> Result:
    """crew-codex-coordinator decision 6: what a detached merge printed and how it ended, read in short calls.

    The only write is marking the result read (and its event); the log and the record are never deleted."""
    import time
    from module_crew import mergelock
    end = time.monotonic() + min(max(wait, 0), RESULT_WAIT_MAX) * 60
    state, info = _result_state(db, approval)
    while state == "running" and time.monotonic() < end:
        time.sleep(min(RESULT_POLL, max(end - time.monotonic(), 0)))
        state, info = _result_state(db, approval)
    which = f"C{approval}" if approval is not None else "后台合并"
    if state == "none":
        old = log_path(db, approval) if approval is not None else None
        return Result(3, [f"没有 {which} 可取的结果（只有 merge run --detach 跑的合并才有）"
                          + (f"；它的输出还在 {old}" if old is not None and old.exists() else "")], info)
    if state == "running":
        took = mergelock.minutes(info)
        return Result(6, [f"合并 C{info.get('approval')}（{info.get('unit')}）还在后台跑"
                          + (f"（已跑 {took} 分钟）" if took is not None else "") + "：过一会儿再运行 merge result"], info)
    if state == "lost":
        return Result(3, [f"合并 C{info.get('approval')} 的后台进程不在了，没有写下结果；输出在 {info.get('log') or log_path(db, info.get('approval'))}",
                          "运行 module-crew status 看锁的状态，按它说的处理"], info)
    try:
        output = Path(info["log"]).read_text(encoding="utf-8")
    except (OSError, KeyError) as exc:
        return Result(3, [f"合并 C{info.get('approval')} 已结束（退出码 {info['exitCode']}），但输出读不出：{exc}"], info)
    if not info.get("resultRead"):
        mergelock.mark_read(db, info)
        with db.transaction(actor="merge") as tx:
            rec = tx.get("item", str(info["approval"])) or {}
            tx.put("item", str(info["approval"]), rec, action="merge-result-read")
    return Result(info["exitCode"], [], info, output)


def _run(project: Path, check_command: str | None, replace: bool, holder: dict) -> RunResult:
    db = store.open_store(project)
    cfg, reasons, pending_write = _check_config(db, check_command, replace)
    if reasons:
        return RunResult(2, reasons)
    rows = queue(project)
    if not rows:
        return RunResult(3, ["合并队列是空的"])
    n, rec = rows[0]
    task = rec.get("task")
    m = f"task/t{task}" if task else rec["module"]          # the branch to merge
    unit = f"T{task}" if task else m
    session = store.get(db, "session", rec["from"]) or {}
    worktree = Path(session.get("worktree", "/nonexistent"))
    checkout = probe._checkout_of(project, cfg.get("integrationBranch", ""))
    problems = []
    head = _git(project, "rev-parse", f"refs/heads/{m}").stdout.strip()
    if head != rec["commit"]:
        problems.append(f"{'任务' if task else '模块'}分支 {m} 在最终验收交审之后又有提交（交审时 {rec['commit'][:7]}，现在 {head[:7]}），须重新交审")
    if not worktree.is_dir() or not _clean(worktree):
        problems.append(f"{unit} 的 worktree 不干净或不存在：{worktree}")
    if checkout is None or not _clean(checkout):
        problems.append("集成分支所在的 checkout 不干净或集成分支没有被检出")
    if problems:
        return RunResult(3, [f"C{n}（{unit}）没有合并："] + problems, approval=n)
    from module_crew import mergelock      # taken only once the checklist passed: a refusal writes nothing
    lock = holder.get("lock") or mergelock.acquire(db, n, unit)
    if isinstance(lock, mergelock.Held):
        return RunResult(6, [mergelock.describe(lock.info) + "，等它结束再做"], approval=n)
    holder["lock"] = lock
    if holder.get("detach"):
        return _hand_off(project, db, n, unit, lock, *holder["args"])
    if pending_write:
        _write_config(db, cfg)

    result = RunResult(0, approval=n)
    from module_crew import unqueued        # crew-unqueued-commits: tell, ask for sync, then merge as usual
    found = unqueued.find(db, project)
    if found.commits:
        result.lines.append(unqueued.describe(found) + "：告诉用户一次，已给在开发的模块发同步通知")
        result.sends += unqueued.notify(db, project)
    elif found.missing_seen:
        unqueued.mark_integration(db, project, "merge-run")
    try:
        merged = probe._git(checkout, "merge", "--no-ff", "--no-edit", "-m",
                            commits.message(f"合并批准事项 C{n}：合入 {unit}", commits.prefix_of(db)), m,
                            timeout=commit_timeout(cfg))
    except subprocess.TimeoutExpired as exc:
        # killed in pre-merge-commit, git has staged the merge but written no MERGE_HEAD yet: --abort has nothing to
        # abort, so reset --merge drops the staged result (the checkout was clean before, see the checklist above)
        if _git(checkout, "merge", "--abort").returncode != 0:
            _git(checkout, "reset", "-q", "--merge")
        return RunResult(4, [probe.timed_out(f"C{n}（{m}）的合并提交", exc),
                             "已中止合并，集成分支未变；合并批准仍开着，交用户决定"], approval=n)
    reset_to = None
    if merged.returncode != 0:
        conflicted = _git(checkout, "diff", "--name-only", "--diff-filter=U").stdout.split()
        _git(checkout, "merge", "--abort")
        if not conflicted:
            # No conflicted file: the merge commit itself was refused (usually a commit hook). Not the module's
            # fault, so nothing is sent back and the approval stays open for the user to decide.
            return RunResult(4, [commits.failure(checkout, merged, f"C{n}（{m}）的合并提交没有做成")]
                             + commits.hook_lines(checkout, merged)
                             + ["已中止合并，集成分支未变；合并批准仍开着，交用户决定"], approval=n)
        reason = f"与集成分支冲突：{'、'.join(conflicted)}"
    else:
        result.merge_commit = _git(checkout, "rev-parse", "HEAD").stdout.strip()
        result.lines += commits.hook_lines(checkout, merged)
        reason = _run_check(cfg, checkout)
        if reason:
            # The merge commit was made just now, locally, and nobody has synced it: drop it rather than revert it,
            # so the module branch can be merged again later with all of its changes (pilot round 2, problem K).
            first = reason.splitlines()[0]
            if _git(checkout, "rev-parse", "HEAD").stdout.strip() != result.merge_commit:
                return RunResult(4, [f"C{n}（{m}）{first}；集成分支顶端已不是本次合并提交 {result.merge_commit[:7]}，没有撤销",
                                     "交用户决定"], approval=n, merge_commit=result.merge_commit)
            reset_to = _git(checkout, "rev-parse", f"{result.merge_commit}^1").stdout.strip()
            undo = _git(checkout, "reset", "-q", "--hard", reset_to)
            if undo.returncode != 0:
                return RunResult(4, [f"C{n}（{m}）{first}；撤销合并失败：{undo.stderr.strip()[:200]}",
                                     "集成 checkout 状态未知，交用户决定"], approval=n, merge_commit=result.merge_commit)
            if reason.startswith(CANNOT_RUN):
                # S30: not the module's fault and not a failed check: nothing is sent back, the approval stays open
                return RunResult(4, [f"C{n}（{m}）{first}；已撤销合并，集成分支回到合并前的 {reset_to[:7]}",
                                     "检查命令要改（项目脚本或 /bin/sh -c '…'，须用户同意后加 --replace-check）；"
                                     "合并批准仍开着，交用户决定"], approval=n, merge_commit=result.merge_commit)

    # decision 10: record the revised Spec's approval before the tick; a light task has no Spec and no todo
    try:
        mark_line = _mark_spec(project, checkout, m, n, result.merge_commit, commits.prefix_of(db), commit_timeout(cfg)) \
            if not reason and not task and rec.get("specRevisionApproved") else None
        tick_line, tick_hooks = (None, []) if reason or task else \
            _tick(project, checkout, m, n, commits.prefix_of(db), commit_timeout(cfg))[2:]
    except subprocess.TimeoutExpired as exc:
        # S28: the merge stands and the check passed, but nothing is recorded yet; a rerun would merge nothing new
        return RunResult(4, [probe.timed_out("合并收尾的提交", exc),
                             f"合并提交 {result.merge_commit[:7]} 已在集成分支、检查已通过、状态库未记合并，"
                             "不要重跑 merge run，交模块协调",
                             f"补记合并：请用户同意后运行 module-crew merge record C{n} --original-file <原话文件>"
                             + ("" if task else f"，再用 merge tick {m} 勾选最终验收")],
                         approval=n, merge_commit=result.merge_commit)
    with db.transaction(actor="coordinator") as tx:
        current = tx.get("item", str(n))
        if reason:
            result.code = 5
            first = reason.splitlines()[0] + _failed_lines(reason)
            kind = _return_kind(reason)
            tx.put("item", str(n), dict(current, state="closed", closedReason="returned", reason=reason,
                                        mergeCommit=result.merge_commit, resetTo=reset_to, returnKind=kind),
                   action="returned")
            _notice(tx, db, result, rec["from"], "returned", basis=_return_basis(n, first, reset_to),
                    todo=ENV_TODO if kind == "env" else MODULE_TODO, task=task)
            result.lines.append(f"C{n}（{unit}）已退回（{'检查环境出了问题，模块不用改代码' if kind == 'env' else '模块需要修改'}）：{first}")
        else:
            _close_merged(tx, db, result, n, current, unit)
            result.lines.append(f"C{n}（{unit}）已合入集成分支 {result.merge_commit[:7]}")
            if mark_line:
                result.lines.append(mark_line)
            if tick_line:
                result.lines.append(tick_line)
            result.lines += tick_hooks
    if task:
        from module_crew import tasks
        tasks.advance(db, task, "working" if reason else "merged")
    if not reason:                  # crew-unqueued-commits: the merge (and tick) commits are module-crew's own
        from module_crew import unqueued
        unqueued.mark(db, checkout, "merge-run")
    return result


def _close_merged(tx, db: store.Store, result: RunResult, n: int, rec: dict, unit: str, data: dict | None = None) -> None:
    """Close merge approval C{n} as merged into result.merge_commit: wrap-up to its session, sync to the others."""
    task = rec.get("task")
    tx.put("item", str(n), dict(rec, state="closed", closedReason="merged", mergeCommit=result.merge_commit),
           action="merged", data=data)
    short = result.merge_commit[:7]
    _notice(tx, db, result, rec["from"], "wrap-up",
            basis=f"最终验收的合并批准事项 C{n}；已合入集成分支 {short}",
            todo="停止在本 worktree 开发，等模块协调收回 worktree", task=task)
    what = f"轻任务 {unit}" if task else f"模块 {unit}"
    for name, target_task in sync_targets(tx, exclude=rec["from"]):
        _notice(tx, db, result, name, "sync-baseline",
                basis=f"{what} 已合入集成分支 {short}（合并批准记录 C{n}）",
                todo=f"{sync.STEP}，跑完整检查后继续", task=target_task)


def record(project: str | os.PathLike, approval: int, original: str) -> RunResult:
    """T136: with the user's words, record a merge whose wrap-up timed out after the merge commit was made (S28).
    The merge commit must be on the integration branch: a first-parent merge whose second parent is the submitted
    commit."""
    if not original or not original.strip():
        return RunResult(3, ["用户原话不能为空：补记合并要用户明确同意"], approval=approval)
    project = Path(project)
    db = store.open_store(project)
    rec = store.get(db, "item", str(approval))
    if rec is None or rec.get("kind") != "merge-approval":
        return RunResult(3, [f"C{approval} 不是合并批准"], approval=approval)
    if rec.get("state") != "open":
        return RunResult(3, [f"合并批准 C{approval} 已关闭（{rec.get('closedReason')}），没有可补记的"], approval=approval)
    task = rec.get("task")
    m = f"task/t{task}" if task else rec["module"]
    unit = f"T{task}" if task else m
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch", "")
    merges = _git(project, "rev-list", "--first-parent", "--merges", "--parents", f"refs/heads/{branch}").stdout
    found = next((line.split()[0] for line in merges.splitlines()
                  if len(line.split()) == 3 and line.split()[2] == rec["commit"]), None)
    if found is None:
        return RunResult(3, [f"C{approval}（{unit}）没有补记：集成分支 {branch} 上没有合入交审提交 {rec['commit'][:7]} 的合并提交"],
                         approval=approval)
    result = RunResult(0, approval=approval, merge_commit=found)
    with db.transaction(actor="coordinator") as tx:
        _close_merged(tx, db, result, approval, tx.get("item", str(approval)), unit,
                      data={"original": original, "recorded": True})
    if task:
        from module_crew import tasks
        tasks.advance(db, task, "merged")
    checkout = probe._checkout_of(project, branch)
    if checkout is not None and _git(checkout, "rev-parse", "HEAD").stdout.strip() == found:
        from module_crew import unqueued        # crew-unqueued-commits: the merge commit is module-crew's own
        unqueued.mark(db, checkout, "merge-record")
    result.lines.append(f"C{approval}（{unit}）已补记合并：合并提交 {found[:7]} 在集成分支上")
    if not task:
        result.lines.append(f"最终验收的勾选若没做成，用户同意后运行 module-crew merge tick {m}（已勾上的会说已勾选）")
    return result


def _return_basis(n: int, first: str, reset_to: str | None) -> str:
    where = (f"已撤销合并：集成分支回到合并前的 {reset_to[:7]}，你的分支原样保留" if reset_to else "集成分支未改动")
    return f"最终验收的合并批准事项 C{n}；{first}；{where}"


def renotice(db: store.Store, approval: int, kind: str) -> Reply:
    """R20⑤: re-send a returned module's notice with the other reason, as judged by the coordinator; the branch is untouched."""
    if kind not in ("env", "module"):
        raise AnswerRefused("原因只能是 env（检查环境）或 module（模块要改）")
    with db.transaction(actor="coordinator") as tx:
        rec = tx.get("item", str(approval))
        if rec is None or rec.get("kind") != "merge-approval" or rec.get("closedReason") != "returned":
            raise AnswerRefused(f"C{approval} 不是已退回的合并批准，没有退回通知可以重发")
        first = (rec.get("reason") or "").splitlines()[0] + _failed_lines(rec.get("reason") or "")
        body = tx.allocate_number()
        meta = tx.write_body(body, protocol.render_coordination_notice(
            "returned", _return_basis(approval, first, rec.get("resetTo")) + "；模块协调改判退回原因",
            ENV_TODO if kind == "env" else MODULE_TODO))
        tx.put("item", str(approval), dict(rec, returnKind=kind), action="renoticed", data={"body": body, "returnKind": kind})
    return Reply(rec["from"], None, body, db.path / meta["path"])


def _mark_spec(project: Path, checkout: Path, module: str, approval: int, merge_commit: str,
               prefix: str = commits.PREFIX, timeout: float = DEFAULT_CHECK_TIMEOUT) -> str | None:
    """crew-merge decision 10: have spec-guard mark the merged, revised Spec approved, in a commit of its own.
    Failure is only reported: the merge stands and the marker line is put back as it was."""
    rel = f"spec/{module}.md"
    if _git(checkout, "diff", "--quiet", f"{merge_commit}^1", merge_commit, "--", rel).returncode == 0:
        return None                     # the merge did not touch the Spec
    missed = f"没有记上 {module} 修订后 Spec 的批准"
    later = f"；用 /spec-guard:review-mark 在集成 checkout {checkout} 补记"
    from module_crew import review
    got = review._mark_command(project)
    if isinstance(got, str):
        return f"{missed}：{got}{later}"
    root, doc = got
    cmd = probe.safe_command(root, doc, "reviewMark", review._mark_fill(checkout, module, "spec")) + ["--confirm"]
    try:
        ran = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=probe.MAP_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        ran = None
        why = str(exc)
    if ran is None or ran.returncode != 0:
        _git(checkout, "checkout", "--", rel)
        if ran is not None:
            out = [x.strip() for x in (ran.stdout.strip() or ran.stderr.strip()).splitlines() if x.strip()]
            why = out[0] if out else f"reviewMark 退出码 {ran.returncode}"
        return f"{missed}：{why}{later}"
    if _git(checkout, "diff", "--quiet", "--", rel).returncode == 0:
        return f"{rel} 早已是批准状态，没有改动"
    _git(checkout, "add", "--", rel)
    try:
        done = probe._git(checkout, "commit", "-q", "-m",
                          commits.message(f"合并批准事项 C{approval}：记下 {module} 修订后 Spec 的批准", prefix), timeout=timeout)
    except subprocess.TimeoutExpired:
        _git(checkout, "reset", "-q", "--", rel)
        _git(checkout, "checkout", "--", rel)
        raise
    if done.returncode != 0:
        _git(checkout, "reset", "-q", "--", rel)
        _git(checkout, "checkout", "--", rel)
        return "\n".join([f"{missed}：" + commits.failure(checkout, done, "提交失败") + later] + commits.hook_lines(checkout, done))
    return f"已在集成分支记下 {module} 修订后 Spec 的批准 {_git(checkout, 'rev-parse', '--short=7', 'HEAD').stdout.strip()}"


GATE_TICK_MINOR = 7      # spec-guard interface 1.7 brings gateTick (0.9.6)


def _gate_command(project: Path, checkout: Path, module: str) -> tuple[Path, list[str]] | str:
    """spec-guard's gateTick command for this module, ready to run with --confirm; a str says why there is none."""
    found = probe.find_plugin("spec-guard", project)
    if isinstance(found, str):
        return found
    doc = probe.read_interface(found.root, probe.SPEC_GUARD_MAJOR)
    if isinstance(doc, str):
        return doc
    if probe._version_tuple(doc) < (probe.SPEC_GUARD_MAJOR, GATE_TICK_MINOR) or "gateTick" not in doc:
        return f"spec-guard 接口 {doc.get('interface')} 低于 1.7（没有 gateTick）"
    cmd = probe.safe_command(found.root, doc, "gateTick", {"<project-root>": str(checkout), "<module-id>": module})
    if isinstance(cmd, str):
        return cmd
    left = [x for x in cmd if x.startswith("<") and x.endswith(">")]
    if left:
        return f"gateTick.command 有不认识的占位符 {'、'.join(left)}，没有运行"
    return found.root, cmd + ["--confirm"]


def _tick(project: Path, checkout: Path, module: str, approval: int,
          prefix: str = commits.PREFIX, timeout: float = DEFAULT_CHECK_TIMEOUT) -> tuple[str, str | None, str, list[str]]:
    """Have spec-guard tick the module's final gate on the integration branch, then commit it (0.9.6: gateTick).

    (status, commit, report line, hook lines); status is ticked / already / refused / unavailable / commit-failed.
    module-crew never ticks a todo item itself: which line is the final gate is spec-guard's rule."""
    rel = f"tasks/{module}/todo.md"
    got = _gate_command(project, checkout, module)
    if isinstance(got, str):
        return "unavailable", None, f"没有替 {module} 勾最终验收：{got}；升级 spec-guard 后用 module-crew merge tick {module} 补勾", []
    root, cmd = got
    try:
        ran = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=probe.MAP_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "unavailable", None, f"没有替 {module} 勾最终验收：gateTick 没跑成（{exc}）", []
    out = [x.strip() for x in (ran.stdout.strip() or ran.stderr.strip()).splitlines() if x.strip()]
    first = out[0] if out else f"退出码 {ran.returncode}"
    if ran.returncode != 0:          # starts with a short code such as not-at-final-gate
        return "refused", None, f"spec-guard 没有勾 {module} 的最终验收：{' '.join(out[:2]) or first}", []
    if any("the final gate is already ticked" in x for x in out):
        return "already", None, f"{module} 的最终验收早已勾过，没有改动", []
    done_line = next((x for x in reversed(out) if x.startswith("ticked;")), None)
    if done_line is None:
        return "refused", None, f"gateTick 的输出看不懂，没有提交：{first}", []
    _git(checkout, "add", "--", rel)
    try:
        done = probe._git(checkout, "commit", "-q", "-m",
                          commits.message(f"合并批准事项 C{approval}：勾选 {module} 的最终验收", prefix), timeout=timeout)
    except subprocess.TimeoutExpired:
        _git(checkout, "reset", "-q", "--", rel)
        _git(checkout, "checkout", "--", rel)
        raise
    if done.returncode != 0:
        _git(checkout, "reset", "-q", "--", rel)
        _git(checkout, "checkout", "--", rel)
        return "commit-failed", None, commits.failure(checkout, done, f"勾选 {rel} 失败"), commits.hook_lines(checkout, done)
    commit = _git(checkout, "rev-parse", "HEAD").stdout.strip()
    from module_crew import unqueued
    unqueued.mark(store.open_store(project), checkout, "merge-tick")
    left = done_line.split(";", 1)[1].strip()
    return "ticked", commit, f"已在集成分支勾选 {module} 的最终验收 {commit[:7]}" + (f"（spec-guard：{left}）" if left else ""), \
        commits.hook_lines(checkout, done)


def tick(project: str | os.PathLike, module: str, original: str) -> str:
    """Tick the final acceptance of a module merged before merge run did it (pilot repair)."""
    if not original or not original.strip():
        raise AnswerRefused("用户原话不能为空：只记用户在本会话亲手输入的话")
    project = Path(project)
    db = store.open_store(project)
    merged = sorted(int(k) for k, v in store.round_items(store.records(db, "item"), store.records(db, "session"), module).items()
                    if v.get("kind") == "merge-approval" and v.get("module") == module and v.get("closedReason") == "merged")
    if not merged:
        raise AnswerRefused(f"模块 {module} 没有已合并的合并批准")
    cfg = store.get(db, "config", "main") or {}
    checkout = probe._checkout_of(project, cfg.get("integrationBranch", ""))
    if checkout is None or not _clean(checkout):
        raise AnswerRefused("集成分支所在的 checkout 不干净或集成分支没有被检出")
    n = merged[-1]
    try:
        status, commit, line, _ = _tick(project, checkout, module, n, commits.prefix_of(db), commit_timeout(cfg))
    except subprocess.TimeoutExpired as exc:
        raise AnswerRefused(probe.timed_out(f"勾选 {module} 的最终验收", exc) + "；没有勾上，可以重试") from None
    if status == "already":
        return line
    if commit is None:
        raise AnswerRefused(line)
    with db.transaction(actor="coordinator") as tx:
        tx.put("item", str(n), dict(tx.get("item", str(n)), tickCommit=commit), action="ticked",
               data={"original": original, "commit": commit})
    return line


@dataclass
class Simple:
    code: int
    lines: list[str] = field(default_factory=list)


def cleanup(project: str | os.PathLike, module: str, original: str) -> Simple:
    """With the user's words: remove a merged module's worktree (no --force) and retire its session; then say whether
    the batch is closed and the crew may switch hosts (crew-host-handover)."""
    res = _cleanup(project, module, original)
    if res.code == 0:
        from module_crew import handover
        line = handover.ready_line(store.open_store(Path(project)))
        if line:
            res.lines.append(line)
    return res


def _cleanup(project: str | os.PathLike, module: str, original: str) -> Simple:
    project = Path(project)
    db = store.open_store(project)
    if not original or not original.strip():
        return Simple(3, ["用户原话不能为空：收回 worktree 要用户明确同意"])
    import re
    if re.match(r"^[Tt][1-9]\d*$", module):
        return _cleanup_task(project, db, int(module[1:]), original)
    merged = [v for v in store.round_items(store.records(db, "item"), store.records(db, "session"), module).values()
              if v.get("kind") == "merge-approval" and v.get("module") == module and v.get("closedReason") == "merged"]
    if not merged:
        return Simple(3, [f"模块 {module} 还没有合入集成分支，不能收回"])
    name, session = next(((k, v) for k, v in store.records(db, "session").items()
                          if v.get("role") == "dev" and v.get("module") == module and v.get("status") == "active"),
                         (None, None))
    if session is None:
        return Simple(3, [f"模块 {module} 没有在用的会话登记"])
    worktree = Path(session["worktree"])
    if not worktree.is_dir() or not _clean(worktree):
        return Simple(3, [f"{worktree} 不存在或不干净，没有收回"])
    removed = _git(project, "worktree", "remove", str(worktree))
    if removed.returncode != 0:
        return Simple(3, [f"git worktree remove 失败：{removed.stderr.strip()[:200]}"])
    with db.transaction(actor="coordinator") as tx:
        tx.put("session", name, dict(session, status="retired"), action="retired",
               data={"original": original, "reason": "merged"})
        tickets = sorted(int(k) for k, v in tx.records("ticket").items() if v.get("from") == name and v.get("state") == "open")
    lines = [f"已收回 {worktree}（分支 {module} 保留），会话 {name} 改为退役",
             f"待退役的邮箱名：{name}（列给用户确认；用户同意后由用户在 Claude Code 里用 /agent-relay:collaboration 退役，"
             "一次一个名字，有未确认的消息时会被拒绝）"]
    if tickets:
        lines.append("这个模块还开着的等待记录：" + "、".join(f"W{n}" for n in tickets)
                     + "（它已不能再发已结项（契约标签【已恢复】）：所等的事已办好就 ticket close --reason happened，用户说关就 --reason user）")
    return Simple(0, lines)


def _cleanup_task(project: Path, db: store.Store, n: int, original: str) -> Simple:
    """crew-light-task: remove a finished light task's worktree (branch kept) and retire its session."""
    t = store.get(db, "task", str(n))
    if t is None or t.get("state") not in ("merged", "cancelled", "promoted"):
        return Simple(3, [f"T{n} 还没有合入、取消或升格，不能收回"])
    name, session = next(((k, v) for k, v in store.records(db, "session").items()
                          if v.get("role") == "task" and v.get("task") == n and v.get("status") == "active"), (None, None))
    if session is None:
        return Simple(3, [f"T{n} 没有在用的会话登记"])
    worktree = Path(session["worktree"])
    if not worktree.is_dir() or not _clean(worktree):
        return Simple(3, [f"{worktree} 不存在或不干净，没有收回"])
    removed = _git(project, "worktree", "remove", str(worktree))
    if removed.returncode != 0:
        return Simple(3, [f"git worktree remove 失败：{removed.stderr.strip()[:200]}"])
    with db.transaction(actor="coordinator") as tx:
        tx.put("session", name, dict(session, status="retired"), action="retired",
               data={"original": original, "reason": t["state"]})
    return Simple(0, [f"已收回 {worktree}（分支 {t.get('branch')} 保留），会话 {name} 改为退役",
                      f"待退役的邮箱名：{name}（列给用户确认；用户同意后由用户在 Claude Code 里用 /agent-relay:collaboration 退役）"])


@dataclass
class PushPlan:
    code: int
    lines: list[str] = field(default_factory=list)
    remote: str | None = None
    branch: str | None = None
    base: str | None = None
    commits: list[str] = field(default_factory=list)
    title: str = ""
    body: str = ""
    modules: list[dict] = field(default_factory=list)


def _next_number(db: store.Store) -> int:
    return max((int(e["key"]) for e in store.events(db)
                if e["type"].split(".")[0] in store.NUMBERED and e["key"].isdigit()), default=0) + 1


def push_timeout(cfg: dict) -> int:
    """Decision 11 (0.11.3): a project's pre-push hook may run the full check, so the push gets the check's timeout."""
    return int(cfg.get("checkTimeout") or DEFAULT_CHECK_TIMEOUT)


def commit_timeout(cfg: dict) -> int:
    """S28 (0.14.1): a commit runs the project's commit hooks, which may be as heavy as the full check."""
    return push_timeout(cfg)


def _pr_base(project: Path, cfg: dict, remote: str, integration: str, given: str | None) -> tuple[str | None, str]:
    """Decision 1 (0.11.3): (PR base, where it came from); None when nothing names one."""
    if given:
        return given, "命令参数 --pr-base"
    if cfg.get("prBase"):
        return cfg["prBase"], "配置 prBase"
    if _git(project, "rev-parse", "--verify", "--quiet", f"refs/remotes/{remote}/{integration}").returncode == 0:
        return integration, "集成分支（远端有它的跟踪分支）"
    head = _git(project, "symbolic-ref", "--quiet", "--short", f"refs/remotes/{remote}/HEAD").stdout.strip()
    if head.startswith(f"{remote}/"):
        return head.split("/", 1)[1], "远端默认分支"
    return None, ""


def push_plan(project: str | os.PathLike, pr_base: str | None = None) -> PushPlan:
    """Read-only preview of the push: remote, new branch, PR base, commits and PR text."""
    project = Path(project)
    db = store.open_store(project)
    cfg = store.get(db, "config", "main") or {}
    remote = cfg.get("remote") or "origin"
    integration = cfg.get("integrationBranch")
    if not integration:
        return PushPlan(3, ["还没有运行配置（先 start prepare）"])
    if _git(project, "remote", "get-url", remote).returncode != 0:
        return PushPlan(3, [f"没有远端 {remote}：推送与开 PR 交用户自己处理"])
    base, why = _pr_base(project, cfg, remote, integration, pr_base)
    if base is None:
        return PushPlan(3, [f"集成分支 {integration} 在远端 {remote} 没有跟踪分支，也读不出远端的默认分支：PR 开向哪里请用户指定，"
                            f"再带 --pr-base <分支> 重跑（先 git fetch {remote} 也可能取得到）"], remote=remote)
    tracking = f"refs/remotes/{remote}/{base}"
    if _git(project, "rev-parse", "--verify", "--quiet", tracking).returncode != 0:
        return PushPlan(3, [f"远端 {remote} 没有 {base} 的跟踪分支（PR 目标取自{why}）：先 git fetch {remote}，或带 --pr-base 指定"],
                        remote=remote, base=base)
    span, note = [integration, f"^{tracking}"], f"PR 目标取自{why}"
    commits = _git(project, "log", "--format=%h %s", *span).stdout.strip().splitlines()
    if not commits:
        return PushPlan(3, ["没有要推送的提交"], remote=remote, base=base)
    pushed = {c for v in store.records(db, "item").values() if v.get("kind") == "push" for c in v.get("mergeCommits", [])}
    modules = [{"module": v["module"], "approval": int(k), "mergeCommit": v["mergeCommit"]}
               for k, v in sorted(store.records(db, "item").items(), key=lambda kv: int(kv[0]))
               if v.get("kind") == "merge-approval" and v.get("closedReason") == "merged" and v["mergeCommit"] not in pushed]
    number = _next_number(db)
    branch = f"crew/batch-{number}"
    names = "、".join(m["module"] for m in modules) or "集成分支改动"
    title = f"module-crew：合入 {names}"
    module_lines = [f"- {m['module']}：合并批准事项 C{m['approval']}，合并提交 {m['mergeCommit'][:7]}"
                    for m in modules] or ["- （无）"]
    body = "\n".join(["本批由 module-crew 的模块协调在本地集成分支合入，远端合并请由你决定。", "",
                      "## 合入的模块", *module_lines, "", "## 提交", *[f"- {c}" for c in commits]]) + "\n"
    lines = [f"远端 {remote}，新分支 {branch} → PR 开向 {base}", f"{len(commits)} 个提交"] + ([note] if note else [])
    return PushPlan(0, lines, remote, branch, base, commits, title, body, modules)


@dataclass
class PushResult:
    code: int
    lines: list[str] = field(default_factory=list)
    branch: str | None = None
    record: int | None = None
    pr: str | None = None


def _gh() -> str | None:
    override = os.environ.get("MODULE_CREW_GH")
    if override is not None:
        return override or None
    return shutil.which("gh")


def push(project: str | os.PathLike, original: str, pr_base: str | None = None) -> PushResult:
    """With the user's explicit words: push the integration branch to a new remote branch and open one PR."""
    project = Path(project)
    if not original or not original.strip():
        return PushResult(3, ["用户原话不能为空：推送要用户明确授权"])
    plan = push_plan(project, pr_base)
    if plan.code != 0:
        return PushResult(plan.code, plan.lines)
    db = store.open_store(project)
    cfg = store.get(db, "config", "main")
    from module_crew import prepush
    # crew-host-permissions: a one-time pass for the pre-push guard, spent whatever happens
    prepush.write_token(db.path, f"refs/heads/{plan.branch}")
    limit = push_timeout(cfg)
    try:
        pushed = subprocess.run(["git", "-C", str(project), "push", plan.remote,
                                 f"{cfg['integrationBranch']}:refs/heads/{plan.branch}"],
                                capture_output=True, text=True, timeout=limit)
    except subprocess.TimeoutExpired:
        return PushResult(4, [f"推送超时（{limit} 秒）：多半是项目的 pre-push 钩子在跑检查，git 已被停下；远端可能没有 {plan.branch}，"
                              f"看钩子的输出后再决定重推，或把 checkTimeout 调大"])
    except OSError as exc:
        return PushResult(4, [f"推送没有跑起来：{exc}"])
    finally:
        prepush.spend_token(db.path)
    if pushed.returncode != 0:
        why = (pushed.stderr.strip() or pushed.stdout.strip() or f"git 退出码 {pushed.returncode}")[:300]
        return PushResult(4, [f"推送失败：{why}"])
    result = PushResult(0, [f"已推送到 {plan.remote}/{plan.branch}"], branch=plan.branch)
    # the body has to be on disk before gh reads it, so the push record is committed first
    with db.transaction(actor="coordinator") as tx:
        number = tx.allocate_number()
        body_no = tx.allocate_number()
        meta = tx.write_body(body_no, plan.body)
        rec = {"state": "closed", "kind": "push", "closedReason": "pushed", "remoteBranch": plan.branch, "base": plan.base,
               "commits": plan.commits, "mergeCommits": [m["mergeCommit"] for m in plan.modules], "pr": None,
               "body": body_no, "answer": {"original": original, "answeredAt": store.now(), **store.source_field()}}
        tx.put("item", str(number), rec, action="pushed")
    body_path = db.path / meta["path"]
    gh = _gh()
    url = _git(project, "remote", "get-url", plan.remote).stdout.strip()
    pr = None
    if gh and "github.com" in url:
        made = subprocess.run([gh, "pr", "create", "--base", plan.base, "--head", plan.branch, "--title", plan.title,
                               "--body-file", str(body_path)], cwd=project, capture_output=True, text=True, timeout=120)
        if made.returncode == 0:
            pr = made.stdout.strip().splitlines()[-1] if made.stdout.strip() else None
            result.lines.append(f"已开 PR：{pr}（请你在远端合并；没有开自动合并）")
            with db.transaction(actor="coordinator") as tx:
                tx.put("item", str(number), dict(rec, pr=pr), action="pr-opened")
        else:
            result.code = 4
            result.lines.append(f"推送成功，但开 PR 失败：{made.stderr.strip()[:300]}；PR 正文在 {body_path}")
    else:
        why = "远端不是 GitHub" if gh else "没有 gh"
        result.lines.append(f"{why}：请你在远端从 {plan.branch} 向 {plan.base} 开 PR。PR 标题：{plan.title}；PR 正文：")
        result.lines.append(plan.body)
    result.record, result.pr = number, pr
    if f"batch-{number}" not in plan.branch:
        result.lines.append(f"注意：分支名用的是 {plan.branch}，推送记录编号是 C{number}（期间有其他写入）")
    return result
