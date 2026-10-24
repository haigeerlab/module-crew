"""`module-crew host-check`: can this module session do module-crew's work here? (see spec/crew-codex-host.md)

Read-only towards the repository and the store.  The one write is a temporary file created and removed inside the
checkout's own git directory: that is exactly what Codex desktop's default sandbox refuses (it does not let a session
write `.git`, and a worktree's git directory lives outside the worktree), so it is the check that matters most.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import types
from dataclasses import dataclass, field
from pathlib import Path

from module_crew import hooks, store

ROOT = Path(__file__).resolve().parents[1]


def plugin_version() -> str | None:
    try:
        return json.loads((ROOT / "interface.json").read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError):
        return None


@dataclass
class Report:
    code: int                                   # 0 all passed / 3 something failed / 2 not in a module-crew repository
    checks: list[dict] = field(default_factory=list)   # {"id", "ok", "reason", "fix"}
    module: str | None = None
    host: str | None = None
    role: str | None = None                     # crew-codex-coordinator: "dev" / "task" / "coordinator" / None


def _check(rep: Report, cid: str, ok: bool, reason: str, fix: str = "") -> None:
    rep.checks.append({"id": cid, "ok": ok, "reason": reason, "fix": "" if ok else fix})


def run(cwd: str | Path) -> Report:
    cwd = Path(cwd)
    try:
        db = store.open_store(cwd)
    except store.StoreError as exc:
        rep = Report(2)
        _check(rep, "store", False, f"不在 module-crew 管理的仓库里：{exc}", "到开工说明写的 worktree 里运行")
        return rep
    rep = Report(0)
    _check(rep, "store", True, f"状态库可读：{db.path}")
    role = hooks.detect(cwd)
    rep.role = role.kind if role is not None else None
    if role is not None and role.kind == "coordinator":
        return _coordinator(rep, db, cwd, role)
    if role is not None and role.kind == "dev":
        rep.module = role.module
        rep.host = (store.get(db, "session", role.name) or {}).get("host")
        _check(rep, "registered", True, f"登记的模块会话：{role.name}（模块 {role.module}，{rep.host}）")
    elif role is not None and role.kind == "task":     # S24: a light task's own worktree
        rep.host = (store.get(db, "session", role.name) or {}).get("host")
        _check(rep, "registered", True, f"登记的轻任务会话：{role.name}（轻任务 T{role.task}，{rep.host}）")
    else:
        _check(rep, "registered", False, "这里不是登记过的在用模块会话的 worktree",
               "确认工作目录是开工说明写的 worktree；不对就把输出发给模块协调")
    _check_version(rep, db)
    _check_git_writable(rep, cwd, ("--absolute-git-dir",),
                        "提交会失败：Codex 默认沙箱不让写 .git，请用户在本会话批准提权（能选本会话一直允许就选）后再试")
    _check_commit_hooks(rep, cwd)
    return _done(rep)


HOOK_RUN_GIT = (2, 36)      # `git hook run`
HOOK_TIMEOUT = 300


def git_version() -> tuple[int, ...]:
    words = subprocess.run(["git", "--version"], capture_output=True, text=True).stdout.split()
    return tuple(int(x) for x in (words[2].split(".")[:2] if len(words) > 2 else []) if x.isdigit())


def _check_commit_hooks(rep: Report, cwd: Path) -> None:
    """S22 (LIVE-SAAS): a worktree without its dependencies cannot run the project's commit hooks (lefthook, husky),
    and the format problems only surfaced when review approve committed to the integration branch."""
    from module_crew import commits, start
    if not commits.hooks_active(cwd):
        _check(rep, "commit-hooks", True, "项目没设提交钩子，不用试跑")
        return
    have = git_version()
    if have < HOOK_RUN_GIT:
        _check(rep, "commit-hooks", True, f"提交钩子未检查：git {'.'.join(map(str, have)) or '版本不明'} 没有 git hook run，"
               "要 2.36 以上")
        return
    try:
        ran = subprocess.run(["git", "hook", "run", "--ignore-missing", "pre-commit"], cwd=cwd, capture_output=True,
                             text=True, timeout=HOOK_TIMEOUT)
    except subprocess.TimeoutExpired:
        ok, tail = False, [f"{HOOK_TIMEOUT} 秒没跑完"]
    else:
        ok = ran.returncode == 0
        tail = [line for line in (ran.stdout + ran.stderr).splitlines() if line.strip()][-commits.HOOK_TAIL:]
        tail = tail or [f"退出码 {ran.returncode}，没有输出"]
    cmds = start.install_commands(cwd)
    fix = "先在本 worktree 装依赖" + (f"（{'；'.join(cmds)}）" if cmds else "") + "，再跑一次 module-crew host-check"
    _check(rep, "commit-hooks", ok, "提交钩子能跑：pre-commit 试跑通过" if ok
           else "提交钩子跑不通：pre-commit 试跑失败，最后几行：\n" + "\n".join(f"   {line}" for line in tail), fix)


def entry_version(db: store.Store) -> str | None:
    """S24: the version the store's fixed entry hands over to now, i.e. what the coordinator really runs.

    Loads the store's own copy of the launcher (nothing else) and asks its locate(); None when that cannot tell."""
    from module_crew import launcher
    path = launcher.entry(db.path)
    common = db.path.parent
    project = common.parent if common.name == ".git" else common
    try:
        # Compile from source rather than import it: an import would cache bytecode next to the entry (T167).
        mod = types.ModuleType("module_crew_fixed_entry")
        mod.__file__ = str(path)
        exec(compile(Path(path).read_bytes(), str(path), "exec"), mod.__dict__)
        root = mod.locate(project)
        if isinstance(root, str):
            return None
        version = json.loads((Path(root) / "interface.json").read_text(encoding="utf-8")).get("version")
    except Exception:       # a missing, old or broken copy: fall back to the recorded version
        return None
    return version if isinstance(version, str) else None


def _check_version(rep: Report, db: store.Store) -> None:
    have = plugin_version()
    running = entry_version(db)
    if running is not None:
        _check(rep, "version", running == have, f"module-crew {have}，固定入口当前转到 {running}（模块协调在跑的版本）",
               "两边装的 module-crew 版本不同：请用户把两个宿主的插件装成同一版本")
        return
    want = (store.get(db, "config", "main") or {}).get("pluginVersion")
    if want is None:
        _check(rep, "version", True, f"module-crew {have} 能运行（状态库没记版本，未比对）")
    else:
        _check(rep, "version", want == have, f"module-crew {have}，模块协调开工时是 {want}",
               "两边装的 module-crew 版本不同：请用户把两个宿主的插件装成同一版本")


def _check_git_writable(rep: Report, cwd: Path, which: tuple[str, ...], fix: str) -> None:
    gitdir = subprocess.run(["git", "-C", str(cwd), "rev-parse", *which], capture_output=True, text=True, timeout=30)
    path = Path(gitdir.stdout.strip()) if gitdir.returncode == 0 else None
    try:
        if path is None:
            raise OSError(gitdir.stderr.strip() or "找不到 git 目录")
        with tempfile.NamedTemporaryFile(dir=path, prefix=".module-crew-host-check-"):
            pass
        _check(rep, "git-writable", True, f"能写 git 目录：{path}")
    except OSError as exc:
        _check(rep, "git-writable", False, f"写不了 git 目录 {path}：{exc}", fix)


def _coordinator(rep: Report, db: store.Store, cwd: Path, role) -> Report:
    """crew-codex-coordinator decision 3: what the coordinator needs in the integration checkout."""
    from module_crew import launcher, probe
    rep.host = (store.get(db, "session", role.name) or {}).get("host")
    _check(rep, "registered", True, f"登记的模块协调：{role.name}（{rep.host}），这里是集成 checkout")
    _check_version(rep, db)
    _check_git_writable(rep, cwd, ("--path-format=absolute", "--git-common-dir"),
                        "模块协调的写命令都写状态库与 .git：Codex 默认沙箱不让写，请申请在沙箱外运行这些命令"
                        "（用户在本线程批准，能选本会话一直允许就选）")
    found = probe.find_plugin("spec-guard", cwd)
    if isinstance(found, str):
        _check(rep, "spec-guard", False, f"找不到 spec-guard：{probe.plugin_missing(found)}", "交审、批准标记与勾选要用它：请用户装好 spec-guard 后再试")
    else:
        _check(rep, "spec-guard", True, f"spec-guard：{found.root}")
    entry = launcher.entry(db.path)
    _check(rep, "entry", entry.is_file(), f"固定入口：{entry}" + ("" if entry.is_file() else "（不存在）"),
           "经用户原话运行一次 module-crew permissions apply 写出固定入口")
    return _done(rep)


def _done(rep: Report) -> Report:
    if any(not c["ok"] for c in rep.checks):
        rep.code = 3
    return rep


def render(rep: Report) -> list[str]:
    lines = [f"{'✅' if c['ok'] else '❌'} {c['reason']}" + (f"\n   怎么办：{c['fix']}" if c["fix"] else "") for c in rep.checks]
    lines.append("agent-relay 是会话里的工具，命令行查不到：请用 bridge_agents 确认自己的邮箱名已注册、身份对得上")
    return lines
