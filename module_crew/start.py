"""Expansion point: propose which modules to open, then prepare worktrees, registrations and kickoffs
(see spec/crew-start.md). Opening the sessions themselves is done by the coordinator with the desktop tools.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from module_crew import probe, store

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


def plan(project: str | os.PathLike, max_modules: int | None = None) -> Proposal:
    """Read-only: free slots and the first startable modules in Build order."""
    project = Path(project)
    report = probe.run(project)
    db = _open_store(project)
    limit = _config(db).get("maxModules") or max_modules or DEFAULT_MAX
    slots = max(limit - len(_active_devs(db)), 0)
    blockers = [f"{c.id}：{c.reason}" for c in report.checks.values() if c.state == "blocker"]
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
    reasons, cfg, _ = validate(project, modules, original, short, max_modules)
    if reasons:
        return PrepareResult(3, ["没有执行，原因："] + reasons)
    return PrepareResult(0)
