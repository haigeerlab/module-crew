"""`module-crew host-check`: can this module session do module-crew's work here? (see spec/crew-codex-host.md)

Read-only towards the repository and the store.  The one write is a temporary file created and removed inside the
checkout's own git directory: that is exactly what Codex desktop's default sandbox refuses (it does not let a session
write `.git`, and a worktree's git directory lives outside the worktree), so it is the check that matters most.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
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
    else:
        _check(rep, "registered", False, "这里不是登记过的在用模块会话的 worktree",
               "确认工作目录是开工说明写的 worktree；不对就把输出发给模块协调")
    _check_version(rep, db)
    _check_git_writable(rep, cwd, ("--absolute-git-dir",),
                        "提交会失败：Codex 默认沙箱不让写 .git，请用户在本会话批准提权（能选本会话一直允许就选）后再试")
    return _done(rep)


def _check_version(rep: Report, db: store.Store) -> None:
    want, have = (store.get(db, "config", "main") or {}).get("pluginVersion"), plugin_version()
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
