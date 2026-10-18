"""Expansion point: propose which modules to open, then prepare worktrees, registrations and kickoffs
(see spec/crew-start.md). Opening the sessions themselves is done by the coordinator with the desktop tools.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from module_crew import probe, role, store

DEFAULT_MAX = 3


@dataclass
class Proposal:
    slots: int
    modules: list[dict] = field(default_factory=list)      # {"id", "responsibility", "dependsOn"}
    conflicts: list[dict] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


def _open_store(project: Path) -> store.Store | None:
    try:
        return store.open_store(project)
    except store.StoreNotFound:
        return None


def _config(db: store.Store | None) -> dict:
    return (store.get(db, "config", "main") or {}) if db else {}


def _active_devs(db: store.Store | None) -> dict[str, dict]:
    if db is None:
        return {}
    return {k: v for k, v in store.records(db, "session").items()
            if v.get("role") == "dev" and v.get("status") == "active"}


def _counted_devs(db: store.Store | None) -> dict[str, dict]:
    """Module sessions that take a slot: suspended ones (waiting on an outside condition) do not."""
    return {k: v for k, v in _active_devs(db).items() if not v.get("suspended")}


def plan(project: str | os.PathLike, max_modules: int | None = None) -> Proposal:
    """Read-only: free slots and the first startable modules in Build order."""
    project = Path(project)
    report = probe.run(project)
    db = _open_store(project)
    limit = _config(db).get("maxModules") or max_modules or DEFAULT_MAX
    slots = max(limit - len(_counted_devs(db)), 0)
    blockers = [f"{c.id}：{c.reason}" for c in report.checks.values() if c.state == "blocker"]
    if _config(db).get("mode") == "serial":
        from module_crew.failure import SERIAL_BLOCKER
        blockers.append(SERIAL_BLOCKER)
    if blockers:
        return Proposal(slots, blockers=blockers)
    modules = {m.get("id"): m for m in report.map.get("modules") or [] if isinstance(m, dict)}
    picked = [{"id": mid, "responsibility": modules.get(mid, {}).get("responsibility", ""),
               "dependsOn": list(modules.get(mid, {}).get("dependsOn") or [])}
              for mid in (report.startable or {}).get("modules", [])][:slots]
    return Proposal(slots, picked, list((report.startable or {}).get("conflicts", [])))


SHORT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,18}[a-z0-9]$")


@dataclass
class PrepareResult:
    code: int                                   # 0 done / 3 refused, nothing written / 4 stopped part-way
    lines: list[str] = field(default_factory=list)
    approval: int | None = None
    prepared: list[dict] = field(default_factory=list)   # {"id", "worktree", "branch", "relayName", "kickoff"}


def _git(cwd: Path, *args: str):
    return probe._git(cwd, *args)


def _toplevel(project: Path) -> Path:
    return Path(_git(project, "rev-parse", "--show-toplevel").stdout.strip())


def _settings(project: Path, db: store.Store | None, short: str | None, max_modules: int | None) -> tuple[dict, list[str]]:
    """Run configuration to use, plus refusal reasons about it."""
    cfg = _config(db)
    reasons = []
    if cfg:
        if short is not None and short != cfg.get("projectShort"):
            reasons.append(f"项目简称已定为 {cfg.get('projectShort')}，不能改成 {short}")
        if max_modules is not None and max_modules != cfg.get("maxModules"):
            reasons.append(f"上限已定为 {cfg.get('maxModules')}，不能在这里改")
        return cfg, reasons
    if short is None or not SHORT_RE.match(short):
        reasons.append("项目简称必须给出：小写字母、数字、连字符，2～20 位，不以连字符开头或结尾")
    top = _toplevel(project)
    branch = _git(project, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    return {"projectShort": short, "integrationBranch": branch, "maxModules": max_modules or DEFAULT_MAX,
            "crewDir": str(top.parent / f"{top.name}-crew")}, reasons


def validate(project: Path, modules: list[str], original: str, short: str | None,
             max_modules: int | None) -> tuple[list[str], dict, Proposal]:
    reasons = []
    if not original or not original.strip():
        reasons.append("用户原话不能为空：只记用户在本会话亲手输入的话")
    db = _open_store(project)
    cfg, cfg_reasons = _settings(project, db, short, max_modules)
    reasons += cfg_reasons
    proposal = plan(project, cfg.get("maxModules"))
    reasons += proposal.blockers
    if proposal.blockers:
        return reasons, cfg, proposal
    report = probe.run(project)
    startable = (report.startable or {}).get("modules", [])
    active = {v.get("module") for v in _active_devs(db).values()}
    if len(set(modules)) != len(modules) or not modules:
        reasons.append("模块清单为空或有重复")
    if len(modules) > proposal.slots:
        reasons.append(f"空位只有 {proposal.slots} 个，要开 {len(modules)} 个")
    for m in modules:
        if m in active:
            reasons.append(f"{m} 已有在用的模块会话")
        elif m not in startable:
            reasons.append(f"{m} 不在可开工列表（startable.modules）里")
    for m in modules:
        if (Path(cfg["crewDir"]) / m).exists():
            reasons.append(f"{m} 的 worktree 目录已存在：{Path(cfg['crewDir']) / m}")
        if _git(project, "rev-parse", "--verify", "--quiet", f"refs/heads/{m}").returncode == 0:
            reasons.append(f"{m} 的分支已存在")
    return reasons, cfg, proposal


def prepare(project: str | os.PathLike, modules: list[str], original: str, short: str | None = None,
            max_modules: int | None = None) -> PrepareResult:
    project = Path(project)
    reasons, cfg, proposal = validate(project, modules, original, short, max_modules)
    if reasons:
        return PrepareResult(3, ["没有执行，原因："] + reasons)
    info = {m["id"]: m for m in plan(project, len(modules) + len(_counted_devs(_open_store(project)))).modules}
    db = _open_store(project) or store.init_store(project)[0]
    short = cfg["projectShort"]
    coord = f"{short}-coord"
    with db.transaction(actor=coord) as tx:
        if not tx.get("config", "main"):
            tx.put("config", "main", cfg, action="set")
        if not any(v.get("role") == "coordinator" and v.get("status") == "active" for v in tx.records("session").values()):
            tx.put("session", coord, {"role": "coordinator", "host": "claude-desktop", "status": "active"},
                   action="registered")
        approval = tx.allocate_number()
        tx.put("item", str(approval), {
            "state": "closed", "kind": "start", "from": coord, "relayId": None, "modules": list(modules),
            "closedReason": "answered", "answer": {"original": original, "answeredAt": store.now()},
        }, action="start-approved")
    result = PrepareResult(0, approval=approval)
    result.lines.append(f"开工批准事项 #{approval}：{'、'.join(modules)}")
    for m in modules:
        path = Path(cfg["crewDir"]) / m
        if path.exists():  # checked again: git would create the branch before refusing a busy directory
            result.code = 4
            result.lines.append(f"{m}：worktree 目录在校验之后被占用（{path}），已停下")
            break
        added = _git(project, "worktree", "add", "-b", m, str(path), cfg["integrationBranch"])
        if added.returncode != 0:
            result.code = 4
            left = _git(project, "rev-parse", "--verify", "--quiet", f"refs/heads/{m}").returncode == 0
            result.lines.append(f"{m}：建 worktree 失败，已停下（{added.stderr.strip()[:200]}）"
                                + ("；git 已留下分支 " + m + "，请决定是否删除" if left else ""))
            break
        relay = f"{short}-{m}"
        text = render_kickoff(m, info.get(m, {}), path, cfg, relay, coord, approval)
        with db.transaction(actor=coord) as tx:
            tx.put("session", relay, {"role": "dev", "host": "claude-desktop", "status": "active",
                                      "module": m, "worktree": str(path)}, action="registered")
            body = tx.allocate_number()
            tx.write_body(body, text)
        result.prepared.append({"id": m, "worktree": path, "branch": m, "relayName": relay, "kickoff": body,
                                "kickoffPath": db.path / "bodies" / f"{body}.txt"})
    done = [p["id"] for p in result.prepared]
    if result.code == 4:
        result.lines.append(f"已完成：{'、'.join(done) or '无'}；未完成的模块请处理原因后单独重跑")
    roles = _role_commands(project)
    for p in result.prepared:
        p["role"] = _set_role(roles, "setModule", p["worktree"], p["id"])
    checkout = probe._checkout_of(project, cfg["integrationBranch"])
    if checkout is None:
        result.lines.append("集成 checkout 角色标记未设：找不到集成分支所在的 checkout")
    else:
        kind, module = role.read(Path(checkout))
        if kind == "none":
            result.lines.append("集成 checkout " + _set_role(roles, "setCoordinator", Path(checkout), None))
        elif kind == "coordinator":
            result.lines.append("集成 checkout 角色标记：已是 coordinator")
        else:
            result.lines.append(f"集成 checkout 角色标记已是 {('module ' + module) if module else kind}，没有覆盖，请用户决定")
    if result.prepared:
        result.lines.append(f"开会话之前：协调会话先用 agent-relay bridge_register 注册邮箱名 {coord}（wake: \"auto\"），模块只和这个名字说话")
    return result


def _role_commands(project: Path) -> tuple[Path, dict] | str:
    found = probe.find_plugin("spec-guard", project)
    if isinstance(found, str):
        return found
    doc = probe.read_interface(found.root, probe.SPEC_GUARD_MAJOR)
    if isinstance(doc, str):
        return doc
    commands = (doc.get("checkoutRole") or {}).get("commands")
    if not isinstance(commands, dict):
        return "spec-guard 的 interface.json 没有 checkoutRole 入口（需要 interface 1.1）"
    return found.root, commands


def _set_role(roles: tuple[Path, dict] | str, key: str, checkout: Path, module: str | None) -> str:
    """Write one checkout role marker; failures are reported, never fatal."""
    want = f"module {module}" if module else "coordinator"
    if isinstance(roles, str):
        return f"角色标记未设：{roles}"
    root, commands = roles
    cmd = probe.safe_command(root, {key: {"command": commands.get(key)}}, key,
                             {"<module-id>": module or "", "<checkout-root>": str(checkout)})
    if isinstance(cmd, str):
        return f"角色标记未设：{cmd}"
    cmd = cmd + ["--confirm"]
    manual = " ".join(cmd)
    try:
        ran = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=probe.MAP_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"角色标记未设：{exc}；可在 spec-guard 目录手动执行：{manual}"
    if ran.returncode != 0 or role.read(checkout) != (("module", module) if module else ("coordinator", None)):
        why = (ran.stderr or ran.stdout).strip()[:200] or f"退出码 {ran.returncode}"
        return f"角色标记未设：{why}；可在 spec-guard 目录手动执行：{manual}"
    return f"角色标记：{want}"


def render_kickoff(module: str, info: dict, worktree: Path, cfg: dict, relay: str, coord: str, approval: int) -> str:
    deps = "\n".join(f"spec/{d}.md" for d in info.get("dependsOn") or []) or "无"
    return "\n".join([
        f"你是 module-crew 的模块会话，负责模块 {module}：{info.get('responsibility', '')}。",
        "先加载 crew-dev skill，照它的规则做；规则不要抄进这个 worktree 的 CLAUDE.md。",
        "",
        f"工作目录：{worktree}（分支 {module}，从集成分支 {cfg['integrationBranch']} 切出）",
        f"邮箱名：{relay}，用 agent-relay bridge_register 注册，wake: \"auto\"",
        f"协调会话：{coord}（你只和它说话）",
        f"开会话依据：用户批准事项 #{approval}",
        "",
        f"这一步只做：用 /spec 写 spec/{module}.md 与 tasks/{module}/plan.md、todo.md，写好后给协调会话发【交审】（节点 Spec、Plan 各一条，或接口提案）。",
        "收到开工类【协调通知】之前不要开始构建。",
        "",
        f"接口：\n{deps}",
        "全局约束：不改公共文件（要改发【公共变更请求】）；被挡住发【等待其他会话】；发出前 module-crew protocol check。",
    ]) + "\n"
