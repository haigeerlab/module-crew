"""spec-guard declaredScope: the public files a module's approved Plan declares (see spec/crew-declared-scope.md)."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from module_crew import probe, store

SWITCH = "declaredScope"


def enabled(db: store.Store | None) -> bool:
    """Decision 1: the project switch, off unless the user turned it on."""
    return db is not None and (store.get(db, "config", "main") or {}).get(SWITCH) == "on"


@dataclass
class Declared:
    module: str
    usable: bool = False
    reason: str | None = None
    approved_commit: str | None = None
    public_paths: list[str] = field(default_factory=list)
    configs: list[str] = field(default_factory=list)
    patches: list[str] = field(default_factory=list)
    dependencies: list[dict] = field(default_factory=list)

    def inside(self, path: str) -> bool:
        """Assumption 1: equal to a listed path, or under a listed directory (ends with /); never when unusable."""
        if not self.usable:
            return False
        if path in self.configs or path in self.patches:
            return True
        return any(path.startswith(p) if p.endswith("/") else path == p for p in self.public_paths)

    def paths(self) -> dict:
        return {"publicPaths": self.public_paths, "configs": self.configs, "patches": self.patches}


def _interface(project: str | os.PathLike):
    """(plugin, interface doc) of the installed spec-guard with declaredScope, or why it cannot be used."""
    found = probe.find_plugin("spec-guard", project)
    if isinstance(found, str):
        return f"找不到 spec-guard（{found}）"
    doc = probe.read_interface(found.root, probe.SPEC_GUARD_MAJOR)
    if isinstance(doc, str):
        return doc
    if "declaredScope" not in doc:
        return f"装的 spec-guard 接口 {doc.get('interface')} 低于 1.11（没有 declaredScope）"
    return found, doc


def interface_reason(project: str | os.PathLike) -> str | None:
    """Why the installed spec-guard has no declaredScope, or None when it has one."""
    got = _interface(project)
    return got if isinstance(got, str) else None


def read(project: str | os.PathLike, module: str) -> Declared:
    """Assumption 2: usable only when spec-guard says the Plan is approved and has the section; otherwise why not."""
    project = Path(project)
    out = Declared(module)
    got = _interface(project)
    if isinstance(got, str):
        out.reason = got
        return out
    found, doc = got
    cmd = probe.safe_command(found.root, doc, "declaredScope", {"<project-root>": str(project), "<module-id>": module})
    if isinstance(cmd, str):
        out.reason = cmd
        return out
    try:
        ran = subprocess.run(cmd, cwd=found.root, capture_output=True, text=True, timeout=probe.MAP_TIMEOUT)
        result = json.loads(ran.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        out.reason = f"declaredScope 没跑成（{exc}）"
        return out
    if not isinstance(result, dict):
        out.reason = f"declaredScope 没跑成（输出不是对象，退出码 {ran.returncode}）"
    elif ran.returncode == 4:
        out.reason = f"Plan 的预先声明一节格式错（{result.get('error')}）"
    elif ran.returncode != 0:
        out.reason = f"declaredScope 没跑成（退出码 {ran.returncode}：{(ran.stderr or ran.stdout).strip()[:200]}）"
    elif result.get("planApproved") is not True:
        out.reason = "Plan 批准后改过或未批准（planApproved 为 false）"
    elif result.get("declared") is not True:
        out.reason = "Plan 没有预先声明一节"
    else:
        lists = [result.get(k) for k in ("publicPaths", "configs", "patches", "dependencies")]
        if not all(isinstance(x, list) for x in lists):
            out.reason = "declaredScope 的输出缺少清单字段"
            return out
        out.usable = True
        out.approved_commit = result.get("approvedCommit")
        out.public_paths, out.configs, out.patches = (list(map(str, x)) for x in lists[:3])
        out.dependencies = [d for d in lists[3] if isinstance(d, dict)]
    return out
