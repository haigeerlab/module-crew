"""How approval requests are shown to the user (see spec/crew-review-display.md).

Pure presentation plus the few git and spec-guard reads it needs: the parallel-boundary overlap of the Specs under
review, the final-acceptance tables, and the request cards (start, shared change, stuck).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from module_crew import probe, store

PENDING_NODES = ("spec", "interface")


def _spec_text(db: store.Store, rec: dict) -> bytes | None:
    """The Spec as committed in the review's submission."""
    wt = (store.get(db, "session", rec.get("from") or "") or {}).get("worktree")
    if not wt:
        return None
    shown = subprocess.run(["git", "-C", wt, "show", f"{rec['commit']}:spec/{rec['module']}.md"], capture_output=True,
                           timeout=30)
    return shown.stdout if shown.returncode == 0 else None


def overlap(project: Path, db: store.Store, open_items: list[tuple[int, dict]], map_conflicts: list[dict]) -> dict:
    """Decision 4: conflicts / none / unchecked — 「无」 only when a comparison really ran."""
    batch_mods = {v["module"] for _, v in open_items if v.get("module")}
    pending = [(n, v) for n, v in open_items if v.get("node") in PENDING_NODES and v.get("module")]
    if not pending:
        found = [c for c in map_conflicts if batch_mods & set(c.get("modules", []))]
        return {"state": "conflicts" if found else "none", "conflicts": found, "errors": [], "basis": "集成分支上的 Spec",
                "reason": None}
    names = "、".join(dict.fromkeys(v["module"] for _, v in pending))
    unchecked = lambda why: {"state": "unchecked", "conflicts": [], "errors": [], "basis": None,
                             "reason": f"{names} 的 Spec 还在交审中，{why}"}
    found = probe.find_plugin("spec-guard", project)
    if isinstance(found, str):
        return unchecked(f"找不到 spec-guard（{found}）")
    doc = probe.read_interface(found.root, probe.SPEC_GUARD_MAJOR)
    if isinstance(doc, str):
        return unchecked(doc)
    if "scopeOverlap" not in doc:
        return unchecked(f"装的 spec-guard 接口 {doc.get('interface')} 低于 1.10（没有 scopeOverlap），比不了")
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch") or ""
    checkout = probe._checkout_of(project, branch) or project
    tmp = db.path / "tmp"
    tmp.mkdir(exist_ok=True)
    pairs = []
    for n, v in pending:
        text = _spec_text(db, v)
        if text is None:
            return unchecked(f"C{n} 的 Spec 从交审提交里取不出")
        path = tmp / f"C{n}-spec.md"
        store._atomic_write_bytes(path, text)        # overwritten next time, never deleted (decision 5)
        pairs.append(f"{v['module']}={path}")
    cmd = probe.safe_command(found.root, doc, "scopeOverlap", {"<project-root>": str(checkout), "<module-id>=<spec-file>": pairs[0]})
    if isinstance(cmd, str):
        return unchecked(cmd)
    for pair in pairs[1:]:
        cmd += ["--spec", pair]
    try:
        ran = subprocess.run(cmd, cwd=found.root, capture_output=True, text=True, timeout=probe.MAP_TIMEOUT)
        result = json.loads(ran.stdout) if ran.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return unchecked(f"scopeOverlap 没跑成（{exc}）")
    if not isinstance(result, dict):
        return unchecked(f"scopeOverlap 退出码 {ran.returncode}：{(ran.stderr or ran.stdout).strip()[:200]}")
    conflicts = [c for c in result.get("conflicts") or [] if batch_mods & set(c.get("modules", []))]
    errors = list(result.get("errors") or [])
    if conflicts:
        return {"state": "conflicts", "conflicts": conflicts, "errors": errors, "basis": "交审中的 Spec", "reason": None}
    if errors:
        out = unchecked("spec-guard 报了读不出的并行边界")
        out["errors"] = errors
        return out
    return {"state": "none", "conflicts": [], "errors": [], "basis": "交审中的 Spec", "reason": None}


def overlap_lines(o: dict) -> list[str]:
    lines = [f"⚠️ 并行边界重叠：{'、'.join(c.get('modules', []))} 在 {'、'.join(c.get('paths', []))}" for c in o["conflicts"]]
    if o["state"] == "none":
        lines.append(f"并行边界重叠：无（已按{o['basis']} 比对）")
    elif o["state"] == "unchecked":
        lines.append(f"未比对：{o['reason']}")
    lines += [f"  并行边界读不出：{e.get('module') or '?'}（{e.get('source')}）{e.get('error')}" for e in o["errors"]]
    return lines
