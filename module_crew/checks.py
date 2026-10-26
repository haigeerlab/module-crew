"""Quick and full checks kept apart, and a ledger of check results per tree (see spec/crew-check-ledger.md).

With the project switch `checkLedger` on, sessions run the project's quick check (`quickCheckCommand`) after a sync,
before an early landing and for themselves; the full check (`checkCommand`) runs only in the merge queue and once per
integration baseline. Every result is recorded under `<tree>.<quick|full>` so the same tree is never checked twice.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from module_crew import store

SWITCH = "checkLedger"
QUICK = "quickCheckCommand"
KINDS = ("quick", "full")


class ConfigRefused(Exception):
    pass


def enabled(cfg: dict | None) -> bool:
    """The switch is on and both commands are there; anything else behaves as today."""
    cfg = cfg or {}
    return cfg.get(SWITCH) == "on" and bool(cfg.get(QUICK)) and bool(cfg.get("checkCommand"))


def command_problem(text: str) -> str | None:
    """S30 rule for a command written to the config: argv without a shell, so no shell operators."""
    from module_crew import merge
    try:
        argv = shlex.split(text)
    except ValueError as exc:
        return f"检查命令拆不开：{exc}"
    if not argv:
        return "检查命令不能为空"
    bad = next((t for t in argv if t.startswith(merge._SHELL_OPS) or t.endswith(merge._SHELL_OPS)), None)
    if bad is not None:
        return (f"检查命令里有 shell 运算符（「{bad}」）：module-crew 不经 shell 执行检查命令，运算符会被当成普通参数。"
                f"改用两种写法之一：把这些步骤写进项目脚本，检查命令写这个脚本；或写成 /bin/sh -c '<原命令>'")
    return None


def set_config(db: store.Store, quick: str | None, switch: str | None, original: str) -> list[str]:
    """`config set --quick-check-command / --check-ledger`; raises ConfigRefused and writes nothing when refused."""
    if quick is not None:
        problem = command_problem(quick)
        if problem:
            raise ConfigRefused(problem)
    with db.transaction(actor="coordinator") as tx:
        cfg = dict(tx.get("config", "main") or {})
        changed = {}
        if quick is not None:
            changed[QUICK] = quick
        if switch is not None:
            changed[SWITCH] = switch
        new = {**cfg, **changed}
        if switch == "on":
            missing = [k for k in ("checkCommand", QUICK) if not new.get(k)]
            if missing:
                raise ConfigRefused(f"打开检查记账前要先有 {'、'.join(missing)}："
                                    + ("用 config set --quick-check-command \"<项目的快检查脚本>\" 设快检查；" if QUICK in missing else "")
                                    + ("完整检查命令由第一次 merge run --check-command 写入" if "checkCommand" in missing else ""))
        tx.put("config", "main", new, action="set", data={**changed, "original": original})
    lines = []
    if quick is not None:
        lines.append(f"已设快检查命令：{quick}")
    if switch is not None:
        lines.append("已打开检查记账（平时跑快检查，完整检查只在合并队列与基线检查里跑）" if switch == "on"
                     else "已关掉检查记账（检查账保留，不再使用）")
    return lines


def key(tree: str, kind: str) -> str:
    return f"{tree}.{kind}"


def lookup(db: store.Store, tree: str, kind: str, command: str) -> dict | None:
    """The recorded result for this tree and kind, only when it was run with the same command."""
    rec = store.get(db, "check", key(tree, kind))
    return rec if rec and rec.get("command") == command else None


def record(db: store.Store, entry: dict) -> dict:
    if entry.get("kind") not in KINDS or entry.get("result") not in ("pass", "fail"):
        raise ValueError(f"检查账记录不合法：{entry!r}")
    with db.transaction(actor="checks") as tx:
        return tx.put("check", key(entry["tree"], entry["kind"]), entry, action="recorded")


@dataclass
class Outcome:
    code: int                   # 0 pass / 3 refused / 4 timed out or could not run (not recorded) / 5 failed / 6 merge lock held
    lines: list[str] = field(default_factory=list)
    entry: dict | None = None


NAMES = {"quick": "快检查", "full": "完整检查"}
RESULT_NAMES = {"pass": "通过", "fail": "失败"}


def _git(cwd: Path, *args: str):
    from module_crew import probe
    return probe._git(cwd, *args)


def clean_tree(top: Path) -> str | None:
    """HEAD's tree when the working tree has nothing uncommitted and no untracked (not ignored) file, else None."""
    if _git(top, "--no-optional-locks", "status", "--porcelain").stdout.strip():
        return None
    return _git(top, "rev-parse", "HEAD^{tree}").stdout.strip() or None


def run_command(command: str, cwd: Path, timeout: int) -> tuple[str | None, int | None, str, int]:
    """(result or None when it never ran or timed out, exit code, output tail or reason, seconds) — argv, no shell."""
    from module_crew import merge
    argv = shlex.split(command)
    shown = json.dumps(argv, ensure_ascii=False)
    start = time.monotonic()
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, None, f"检查超时（{timeout} 秒）", int(time.monotonic() - start)
    except OSError as exc:
        return None, None, f"{merge.CANNOT_RUN}（实际执行的参数：{shown}）：{exc}", int(time.monotonic() - start)
    seconds = int(time.monotonic() - start)
    tail = "\n".join((done.stdout + done.stderr).strip().splitlines()[-40:])
    if done.returncode in (126, 127):
        return None, done.returncode, f"{merge.CANNOT_RUN}（退出码 {done.returncode}；实际执行的参数：{shown}）：{tail}", seconds
    return ("pass" if done.returncode == 0 else "fail"), done.returncode, tail, seconds


def describe(entry: dict) -> str:
    inherited = f"，继承自树 {entry['inheritedFrom'][:7]}" if entry.get("inheritedFrom") else ""
    return (f"树 {entry['tree'][:7]} 的{NAMES[entry['kind']]}{RESULT_NAMES[entry['result']]}"
            f"（{entry.get('by') or '?'}，{entry.get('startedAt') or '?'}{inherited}）")


def failed_lines(tail: str) -> list[str]:
    from module_crew import merge
    return [line.strip() for line in tail.splitlines() if merge._FAILED.match(line.strip())][:5]


def _timeout(cfg: dict) -> int:
    from module_crew import merge
    return int(cfg.get("checkTimeout") or merge.DEFAULT_CHECK_TIMEOUT)


def check_tree(db: store.Store, cfg: dict, kind: str, tree: str, cwd: Path, by: str, commit: str | None,
               rerun: bool = False) -> Outcome:
    """Report the recorded result for this tree, or run the check and record it (decisions 1, 2)."""
    command = cfg[QUICK] if kind == "quick" else cfg["checkCommand"]
    if not rerun:
        known = lookup(db, tree, kind, command)
        if known is None and kind == "quick":
            full = lookup(db, tree, "full", cfg["checkCommand"])
            known = full if full and full["result"] == "pass" else None
        if known is not None:
            return Outcome(0 if known["result"] == "pass" else 5, [f"已记过，不重跑：{describe(known)}（要重跑加 --rerun）"]
                           + _fail_tail(known), known)
    started = store.now()
    result, code, tail, seconds = run_command(command, cwd, _timeout(cfg))
    if result is None:
        return Outcome(4, [f"{NAMES[kind]}没有跑成，不记账：{tail}"])
    entry = {"tree": tree, "kind": kind, "command": command, "result": result, "exitCode": code, "tail": tail,
             "commit": commit, "where": str(cwd), "by": by, "startedAt": started, "seconds": seconds, "inheritedFrom": None}
    record(db, entry)
    return Outcome(0 if result == "pass" else 5, [f"已记账：{describe(entry)}，用时 {seconds} 秒"] + _fail_tail(entry), entry)


def _fail_tail(entry: dict) -> list[str]:
    if entry["result"] != "fail":
        return []
    hits = failed_lines(entry.get("tail") or "")
    return [f"退出码 {entry.get('exitCode')}" + (f"：{'；'.join(hits)}" if hits else "")]


def quick(cwd: str | os.PathLike, rerun: bool = False) -> Outcome:
    """`check quick` in a module or light-task worktree (decision 3)."""
    from module_crew import hooks
    cwd = Path(cwd)
    try:
        db = store.open_store(cwd)
    except store.StoreError as exc:
        return Outcome(3, [f"不在 module-crew 管理的仓库里：{exc}"])
    cfg = store.get(db, "config", "main") or {}
    if not enabled(cfg):
        return Outcome(3, ["检查记账没打开（项目开关 checkLedger）：照今天的做法跑完整检查"])
    role = hooks.detect(cwd)
    if role is None or role.kind not in ("dev", "task"):
        return Outcome(3, ["这里不是登记过的模块或轻任务 worktree：check quick 只在那里跑（集成 checkout 的快检查经 change land）"])
    top = Path(_git(cwd, "rev-parse", "--show-toplevel").stdout.strip() or cwd)
    tree = clean_tree(top)
    if tree is None:
        return Outcome(3, ["工作区有未提交的改动或未跟踪的文件：先提交再跑快检查（只给干净的树记账）"])
    head = _git(top, "rev-parse", "HEAD").stdout.strip()
    out = check_tree(db, cfg, "quick", tree, top, role.name, head, rerun)
    if out.code == 5:
        out.lines += baseline_hint(db, cfg)
    return out


def baseline_hint(db: store.Store, cfg: dict) -> list[str]:
    return []


def show(cwd: str | os.PathLike, rev: str = "HEAD") -> tuple[int, list[dict]]:
    cwd = Path(cwd)
    db = store.open_store(cwd)
    tree = _git(cwd, "rev-parse", f"{rev}^{{tree}}").stdout.strip()
    if not tree:
        return 3, []
    rows = [r for k in KINDS if (r := store.get(db, "check", key(tree, k)))]
    return 0, rows


def listing(db: store.Store, limit: int = 20) -> list[dict]:
    rows = sorted(store.records(db, "check").values(), key=lambda r: r.get("startedAt") or "", reverse=True)
    return rows[:limit]


def baseline(project: str | os.PathLike, rerun: bool = False) -> Outcome:
    return Outcome(3, ["基线检查还没实现"])


def note_full(db: store.Store, cfg: dict, checkout: Path, exit_code: int, tail: str, started: str) -> None:
    """merge run's full check (decision 4): recorded with the switch on, never used to skip the check."""
    if not enabled(cfg):
        return
    tree = _git(checkout, "rev-parse", "HEAD^{tree}").stdout.strip()
    commit = _git(checkout, "rev-parse", "HEAD").stdout.strip()
    seconds = int((datetime.fromisoformat(store.now()) - datetime.fromisoformat(started)).total_seconds())
    record(db, {"tree": tree, "kind": "full", "command": cfg["checkCommand"], "result": "pass" if exit_code == 0 else "fail",
                "exitCode": exit_code, "tail": tail, "commit": commit, "where": str(checkout), "by": "merge-run",
                "startedAt": started, "seconds": seconds, "inheritedFrom": None})


def inherit(db: store.Store, cfg: dict, checkout: Path, merge_commit: str, module: str) -> dict | None:
    """Decision 5: when everything after the merge commit only ticked the module's todo or marked its Spec, the
    integration head's tree gets the merge tree's passing full check, noted as inherited."""
    if not enabled(cfg):
        return None
    head = _git(checkout, "rev-parse", "HEAD").stdout.strip()
    if head == merge_commit:
        return None
    changed = set(_git(checkout, "diff", "--name-only", merge_commit, head).stdout.split())
    if not changed or not changed <= {f"tasks/{module}/todo.md", f"spec/{module}.md"}:
        return None
    merged = _git(checkout, "rev-parse", f"{merge_commit}^{{tree}}").stdout.strip()
    source = lookup(db, merged, "full", cfg["checkCommand"])
    if source is None or source["result"] != "pass":
        return None
    tree = _git(checkout, "rev-parse", "HEAD^{tree}").stdout.strip()
    entry = {**source, "tree": tree, "commit": head, "inheritedFrom": merged}
    record(db, entry)
    return entry


QUICK_STEP = "跑 `module-crew check quick`（快检查）"
FULL_STEP = "跑完整检查"


def after_sync(cfg: dict | None) -> str:
    """Decision 8: what a session runs after `module-crew sync`; unchanged while the switch is off."""
    return QUICK_STEP if enabled(cfg) else FULL_STEP
