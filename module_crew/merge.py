"""Local merge queue and remote hand-off (see spec/crew-merge.md).

Approved final acceptances are merged into the local integration branch one at a time with
--no-ff and checked; failures are reset away (or aborted) and the module is sent back. Pushing
goes to a new remote branch and a PR the user merges.
"""

from __future__ import annotations

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
        if old.get("kind") == "merge-approval" and old.get("state") == "open" and old.get("module") == rec["module"]:
            tx.put("item", key, dict(old, state="closed", closedReason="superseded", supersededBy=approval),
                   action="superseded", data={"by": approval})
            replaced.append(int(key))
    tx.put("item", str(approval), {
        "state": "open", "kind": "merge-approval", "module": rec["module"], "review": review_no,
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
    return Revoked(rec["from"], None, body, db.path / meta["path"], max(newer) if newer else None)


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
    return sorted(rows, key=lambda kv: (pos.get(kv[1]["module"], len(pos)), kv[0]))


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
        shlex.split(check_command)
    except ValueError as exc:
        return cfg, [f"检查命令拆不开：{exc}"], False
    new = dict(cfg, checkCommand=check_command)
    new.setdefault("checkTimeout", DEFAULT_CHECK_TIMEOUT)
    return new, [], check_command != current


def _write_config(db: store.Store, cfg: dict) -> None:
    with db.transaction(actor="coordinator") as tx:
        previous = (tx.get("config", "main") or {}).get("checkCommand")
        tx.put("config", "main", cfg, action="set", data={"previousCheckCommand": previous})


def _run_check(cfg: dict, checkout: Path) -> str | None:
    """None when the full check passes, else the reason."""
    timeout = cfg.get("checkTimeout") or DEFAULT_CHECK_TIMEOUT
    try:
        done = subprocess.run(shlex.split(cfg["checkCommand"]), cwd=checkout, capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"完整检查超时（{timeout} 秒）"
    except OSError as exc:
        return f"完整检查运行不了：{exc}"
    if done.returncode != 0:
        tail = "\n".join((done.stdout + done.stderr).strip().splitlines()[-40:])
        return f"完整检查失败（退出码 {done.returncode}）：{tail}"
    return None


_FAILED = re.compile(r"^(FAIL|ERROR|FAILED)\b")
ENV_TODO = "失败与你的代码无关，不用改代码；等模块协调告诉你检查环境恢复后，用原提交重新发最终验收【交审】"
MODULE_TODO = "同步集成分支、修好后重新发最终验收【交审】"


def _return_kind(reason: str) -> str:
    """R20⑤: `env` when the full check could not run or ran out of time, `module` when it ran and failed or conflicted."""
    if reason.startswith(("完整检查超时", "完整检查运行不了")) or re.match(r"^完整检查失败（退出码 12[67]）", reason):
        return "env"
    return "module"


def _failed_lines(reason: str) -> str:
    """The test runner's FAIL/ERROR lines (at most 5), so the module sees which check failed."""
    hits = [line.strip() for line in reason.splitlines()[1:] if _FAILED.match(line.strip())][:5]
    return f"（{'；'.join(hits)}）" if hits else ""


def _notice(tx, db: store.Store, result: RunResult, to: str, kind: str, basis: str, todo: str) -> None:
    text = protocol.render_coordination_notice(kind=kind, basis=basis, todo=todo)
    body = tx.allocate_number()
    meta = tx.write_body(body, text)
    result.sends.append({"to": to, "kind": kind, "body": body, "path": db.path / meta["path"]})


def run(project: str | os.PathLike, check_command: str | None = None, replace: bool = False) -> RunResult:
    """Merge the head of the queue, run the full check, and reset or abort on failure."""
    project = Path(project)
    db = store.open_store(project)
    cfg, reasons, pending_write = _check_config(db, check_command, replace)
    if reasons:
        return RunResult(2, reasons)
    rows = queue(project)
    if not rows:
        return RunResult(3, ["合并队列是空的"])
    n, rec = rows[0]
    m = rec["module"]
    session = store.get(db, "session", rec["from"]) or {}
    worktree = Path(session.get("worktree", "/nonexistent"))
    checkout = probe._checkout_of(project, cfg.get("integrationBranch", ""))
    problems = []
    head = _git(project, "rev-parse", f"refs/heads/{m}").stdout.strip()
    if head != rec["commit"]:
        problems.append(f"模块分支 {m} 在最终验收交审之后又有提交（交审时 {rec['commit'][:7]}，现在 {head[:7]}），须重新交审")
    if not worktree.is_dir() or not _clean(worktree):
        problems.append(f"模块 {m} 的 worktree 不干净或不存在：{worktree}")
    if checkout is None or not _clean(checkout):
        problems.append("集成分支所在的 checkout 不干净或集成分支没有被检出")
    if problems:
        return RunResult(3, [f"C{n}（{m}）没有合并："] + problems, approval=n)
    if pending_write:
        _write_config(db, cfg)

    result = RunResult(0, approval=n)
    merged = _git(checkout, "merge", "--no-ff", "--no-edit", "-m", commits.message(f"合并批准事项 C{n}：合入 {m}"), m)
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

    tick_line, tick_hooks = (None, []) if reason else _tick(checkout, m, n)[1:]
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
                    todo=ENV_TODO if kind == "env" else MODULE_TODO)
            result.lines.append(f"C{n}（{m}）已退回（{'检查环境出了问题，模块不用改代码' if kind == 'env' else '模块需要修改'}）：{first}")
        else:
            tx.put("item", str(n), dict(current, state="closed", closedReason="merged", mergeCommit=result.merge_commit),
                   action="merged")
            short = result.merge_commit[:7]
            _notice(tx, db, result, rec["from"], "wrap-up",
                    basis=f"最终验收的合并批准事项 C{n}；已合入集成分支 {short}",
                    todo="停止在本 worktree 开发，等模块协调收回 worktree")
            busy = {v.get("module") for v in tx.records("item").values() if v.get("kind") == "merge-approval"
                    and (v.get("state") == "open" or v.get("closedReason") == "merged")} | awaiting_final(tx)
            for name, s in sorted(tx.records("session").items()):
                if (s.get("role") == "dev" and s.get("status") == "active" and name != rec["from"]
                        and s.get("module") not in busy and not s.get("suspended")):  # resume sends it later
                    _notice(tx, db, result, name, "sync-baseline",
                            basis=f"模块 {m} 已合入集成分支 {short}（合并批准记录 C{n}）",
                            todo=f"{sync.STEP}，跑完整检查后继续")
            result.lines.append(f"C{n}（{m}）已合入集成分支 {short}")
            if tick_line:
                result.lines.append(tick_line)
            result.lines += tick_hooks
    return result


_UNCHECKED = re.compile(r"^(\s*[-*] )\[ \]( .*)$")


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


def _tick(checkout: Path, module: str, approval: int) -> tuple[str | None, str | None, list[str]]:
    """Tick the module's only unchecked todo item on the integration branch; (commit, report line)."""
    path = checkout / "tasks" / module / "todo.md"
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        return None, None, []
    open_at = [i for i, line in enumerate(lines) if _UNCHECKED.match(line.rstrip("\n"))]
    if not open_at:
        return None, None, []
    if len(open_at) > 1:
        return None, f"tasks/{module}/todo.md 还有 {len(open_at)} 个未勾项，没有替它勾最终验收", []
    i = open_at[0]
    end = lines[i][len(lines[i].rstrip("\n")):]
    lines[i] = _UNCHECKED.sub(r"\1[x]\2", lines[i].rstrip("\n")) + end
    path.write_text("".join(lines), encoding="utf-8")
    rel = f"tasks/{module}/todo.md"
    _git(checkout, "add", "--", rel)
    done = _git(checkout, "commit", "-q", "-m", commits.message(f"合并批准事项 C{approval}：勾选 {module} 的最终验收"))
    if done.returncode != 0:
        _git(checkout, "reset", "-q", "--", rel)
        _git(checkout, "checkout", "--", rel)
        return None, commits.failure(checkout, done, f"勾选 {rel} 失败"), commits.hook_lines(checkout, done)
    commit = _git(checkout, "rev-parse", "HEAD").stdout.strip()
    return commit, f"已在集成分支勾选 {module} 的最终验收 {commit[:7]}", commits.hook_lines(checkout, done)


def tick(project: str | os.PathLike, module: str, original: str) -> str:
    """Tick the final acceptance of a module merged before merge run did it (pilot repair)."""
    if not original or not original.strip():
        raise AnswerRefused("用户原话不能为空：只记用户在本会话亲手输入的话")
    project = Path(project)
    db = store.open_store(project)
    merged = sorted(int(k) for k, v in store.records(db, "item").items()
                    if v.get("kind") == "merge-approval" and v.get("module") == module and v.get("closedReason") == "merged")
    if not merged:
        raise AnswerRefused(f"模块 {module} 没有已合并的合并批准")
    cfg = store.get(db, "config", "main") or {}
    checkout = probe._checkout_of(project, cfg.get("integrationBranch", ""))
    if checkout is None or not _clean(checkout):
        raise AnswerRefused("集成分支所在的 checkout 不干净或集成分支没有被检出")
    n = merged[-1]
    commit, line, _ = _tick(checkout, module, n)
    if commit is None:
        raise AnswerRefused(line or f"tasks/{module}/todo.md 没有未勾项，不需要补勾")
    with db.transaction(actor="coordinator") as tx:
        tx.put("item", str(n), dict(tx.get("item", str(n)), tickCommit=commit), action="ticked",
               data={"original": original, "commit": commit})
    return line


@dataclass
class Simple:
    code: int
    lines: list[str] = field(default_factory=list)


def cleanup(project: str | os.PathLike, module: str, original: str) -> Simple:
    """With the user's words: remove a merged module's worktree (no --force) and retire its session."""
    project = Path(project)
    db = store.open_store(project)
    if not original or not original.strip():
        return Simple(3, ["用户原话不能为空：收回 worktree 要用户明确同意"])
    merged = [v for v in store.records(db, "item").values()
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


def push_plan(project: str | os.PathLike) -> PushPlan:
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
    base = cfg.get("prBase") or integration
    tracking = f"refs/remotes/{remote}/{base}"
    if _git(project, "rev-parse", "--verify", "--quiet", tracking).returncode == 0:
        span, note = [integration, f"^{tracking}"], None
    else:
        span, note = [integration], f"本地没有 {remote}/{base} 的跟踪分支，列出的是集成分支的全部提交"
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


def push(project: str | os.PathLike, original: str) -> PushResult:
    """With the user's explicit words: push the integration branch to a new remote branch and open one PR."""
    project = Path(project)
    if not original or not original.strip():
        return PushResult(3, ["用户原话不能为空：推送要用户明确授权"])
    plan = push_plan(project)
    if plan.code != 0:
        return PushResult(plan.code, plan.lines)
    db = store.open_store(project)
    cfg = store.get(db, "config", "main")
    from module_crew import prepush
    # crew-host-permissions: a one-time pass for the pre-push guard, spent whatever happens
    prepush.write_token(db.path, f"refs/heads/{plan.branch}")
    try:
        pushed = _git(project, "push", plan.remote, f"{cfg['integrationBranch']}:refs/heads/{plan.branch}")
    finally:
        prepush.spend_token(db.path)
    if pushed.returncode != 0:
        return PushResult(4, [f"推送失败：{pushed.stderr.strip()[:300]}"])
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
