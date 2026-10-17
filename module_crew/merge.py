"""Local merge queue and remote hand-off (see spec/crew-merge.md).

Approved final acceptances are merged into the local integration branch one at a time with
--no-ff and checked; failures are reverted (or aborted) and the module is sent back. Pushing
goes to a new remote branch and a PR the user merges.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from module_crew import probe, protocol, store
from module_crew.inbox import AnswerRefused, Reply
from module_crew.review import _reply_text

DEFAULT_CHECK_TIMEOUT = 1800


@dataclass
class Approved:
    approval: int
    reply: Reply


def approve(db: store.Store, review_no: int, original: str) -> Approved:
    """Record the user's approval of a final acceptance and queue the module for a local merge."""
    with db.transaction(actor="coordinator") as tx:
        rec = tx.get("item", str(review_no))
        if rec is None or rec.get("kind") != "review":
            raise AnswerRefused(f"没有交审事项 #{review_no}")
        if rec.get("node") != "final":
            raise AnswerRefused(f"交审事项 #{review_no} 不是最终验收（Spec／Plan 用 review approve）")
        if rec.get("state") != "open":
            raise AnswerRefused(f"交审事项 #{review_no} 已关闭（{rec.get('closedReason')}）")
        answered_at = store.now()
        text = _reply_text(review_no, rec, original, answered_at)
        approval = tx.allocate_number()
        tx.put("item", str(approval), {
            "state": "open", "kind": "merge-approval", "module": rec["module"], "review": review_no,
            "commit": rec["commit"], "from": rec["from"], "relayId": rec["relayId"],
            "answer": {"original": original, "answeredAt": answered_at},
            "closedReason": None, "mergeCommit": None, "revertCommit": None, "reason": None,
        }, action="merge-approved")
        body = tx.allocate_number()
        meta = tx.write_body(body, text)
        tx.put("item", str(review_no), dict(rec, state="closed", closedReason="answered",
                                            answer={"original": original, "answeredAt": answered_at, "body": body,
                                                    "approval": approval}),
               action="answered", data={"body": body})
    return Approved(approval, Reply(rec["from"], rec["relayId"], body, db.path / meta["path"]))


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
    code: int                 # 0 merged / 2 no check command / 3 checklist failed or empty queue / 4 revert failed / 5 returned
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


def _notice(tx, db: store.Store, result: RunResult, to: str, kind: str, basis: str, todo: str) -> None:
    text = protocol.render_coordination_notice(kind=kind, basis=basis, todo=todo)
    body = tx.allocate_number()
    meta = tx.write_body(body, text)
    result.sends.append({"to": to, "kind": kind, "body": body, "path": db.path / meta["path"]})


def run(project: str | os.PathLike, check_command: str | None = None, replace: bool = False) -> RunResult:
    """Merge the head of the queue, run the full check, and revert or abort on failure."""
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
        problems.append("集成基线不干净或集成分支没有被检出")
    if problems:
        return RunResult(3, [f"#{n}（{m}）没有合并："] + problems, approval=n)
    if pending_write:
        _write_config(db, cfg)

    result = RunResult(0, approval=n)
    merged = _git(checkout, "merge", "--no-ff", "--no-edit", "-m", f"合入 {m}（合并批准事项 #{n}）", m)
    revert = None
    if merged.returncode != 0:
        conflicted = _git(checkout, "diff", "--name-only", "--diff-filter=U").stdout.split()
        _git(checkout, "merge", "--abort")
        reason = f"与集成基线冲突：{'、'.join(conflicted) or merged.stderr.strip()[:200]}"
    else:
        result.merge_commit = _git(checkout, "rev-parse", "HEAD").stdout.strip()
        reason = _run_check(cfg, checkout)
        if reason:
            undo = _git(checkout, "revert", "-m", "1", "--no-edit", result.merge_commit)
            if undo.returncode != 0:
                return RunResult(4, [f"#{n}（{m}）{reason.splitlines()[0]}；撤销合并失败：{undo.stderr.strip()[:200]}",
                                     "集成 checkout 处于撤销中途，交用户决定"], approval=n, merge_commit=result.merge_commit)
            revert = _git(checkout, "rev-parse", "HEAD").stdout.strip()

    with db.transaction(actor="coordinator") as tx:
        current = tx.get("item", str(n))
        if reason:
            result.code = 5
            first = reason.splitlines()[0]
            tx.put("item", str(n), dict(current, state="closed", closedReason="returned", reason=reason,
                                        mergeCommit=result.merge_commit, revertCommit=revert),
                   action="returned")
            where = f"已撤销合并提交 {result.merge_commit[:7]}（撤销提交 {revert[:7]}）" if revert else "集成基线未改动"
            _notice(tx, db, result, rec["from"], "returned",
                    basis=f"最终验收的合并批准事项 #{n}；{first}；{where}",
                    todo="同步集成基线、修好后重新发最终验收【交审】")
            result.lines.append(f"#{n}（{m}）已退回：{first}")
        else:
            tx.put("item", str(n), dict(current, state="closed", closedReason="merged", mergeCommit=result.merge_commit),
                   action="merged")
            short = result.merge_commit[:7]
            _notice(tx, db, result, rec["from"], "wrap-up",
                    basis=f"最终验收的合并批准事项 #{n}；已合入集成分支 {short}",
                    todo="停止在本 worktree 开发，等协调会话收回 worktree")
            for name, s in sorted(tx.records("session").items()):
                if s.get("role") == "dev" and s.get("status") == "active" and name != rec["from"]:
                    _notice(tx, db, result, name, "sync-baseline",
                            basis=f"模块 {m} 已合入集成基线 {short}（合并批准事项 #{n}）",
                            todo="把集成分支合进你的模块分支，跑完整检查后继续")
            result.lines.append(f"#{n}（{m}）已合入集成分支 {short}")
    return result
