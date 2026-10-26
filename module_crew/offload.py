"""Quota offload: Codex implements a module's Tasks through delegate, the coordinator checks and commits for it
(see spec/crew-codex-offload.md).

module-crew never runs delegate itself (its scripts are not an interface): `start` writes the task text and the
`/delegate:run` line for the coordinator, `settle` reads what came back. Every new behaviour needs the project switch
`codexOffload`, off unless the user turned it on.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
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
