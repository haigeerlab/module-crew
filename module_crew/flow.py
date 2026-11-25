"""spec-guard flow v2 (S110, interface 1.18): requirement -> design (with regression) -> build -> final acceptance by the
regression cases, the Plan never reviewed. One place decides whether a module follows it and what that changes for
reviews, starting and display (see spec/crew-flow-v2.md). A module without a tier is an old module, unchanged."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from module_crew import store

TIERS = ("bug", "small", "normal", "important")
STEP_WORDS = {"design": "写技术方案", "regression": "写回归"}


def tier_of(row: dict | None) -> str | None:
    """Decision 1: the tier /map --json gives the module (interface 1.18); None for an old module or an older spec-guard.
    spec-guard already reads an unknown tier as normal; a stray non-empty value is read the same way here."""
    value = (row or {}).get("tier") if isinstance(row, dict) else None
    if value is None or value == "":
        return None
    return value if value in TIERS else "normal"


def row_of(map_doc: dict | str | None, module_id: str) -> dict | None:
    if not isinstance(map_doc, dict):
        return None
    return next((m for m in map_doc.get("modules") or [] if isinstance(m, dict) and m.get("id") == module_id), None)


def _map(db: store.Store, project: str | os.PathLike) -> dict | str:
    from module_crew import takeover
    return takeover._map(takeover.checkout(db, project))


def tier(db: store.Store, project: str | os.PathLike, module_id: str, map_doc: dict | None = None) -> str | None:
    """The module's flow v2 tier, read from the integration checkout's /map --json; None when unreadable (old flow)."""
    doc = map_doc if map_doc is not None else _map(db, Path(project))
    return tier_of(row_of(doc, module_id))


def is_v2(tier_value: str | None) -> bool:
    return tier_value is not None


def full_docs(tier_value: str | None) -> bool:
    """normal and important write the design and the regression document; bug and small one document."""
    return tier_value in ("normal", "important")


def step_word(row: dict | None) -> str | None:
    """The document step a flow v2 module is on (/map step design or regression), for display."""
    return STEP_WORDS.get((row or {}).get("step")) if isinstance(row, dict) else None


def summarize(map_doc: dict | None) -> dict[str, str]:
    """module id -> tier for every flow v2 module in the map (probe / status)."""
    return {m["id"]: t for m in (map_doc or {}).get("modules") or []
            if isinstance(m, dict) and isinstance(m.get("id"), str) and (t := tier_of(m)) is not None}


# decision 3: which review nodes each kind of module takes (interface proposals stand for the Spec, as today)
PLAN_REFUSED = "新流程模块的 Plan 不交审：写完 tasks/{m}/plan.md、todo.md 提交后直接构建"
ONE_DOC = "bug／小改动只写一份文档（spec/{m}.md），没有技术方案"
OLD_DESIGN = ("「技术方案」节点只用于 spec-guard 新流程模块（/map --json 的 tier 不为空）；{m} 是老模块，照 Spec → Plan 交审")


def refuse(tier_value: str | None, node: str, module_id: str) -> str | None:
    """Why this module cannot take a review at this node, or None (decision 3)."""
    if tier_value is None:
        return OLD_DESIGN.format(m=module_id) if node == "design" else None
    if node == "plan":
        return PLAN_REFUSED.format(m=module_id)
    if node == "design" and not full_docs(tier_value):
        return ONE_DOC.format(m=module_id)
    return None


def design_files(module_id: str) -> tuple[str, str]:
    return f"tasks/{module_id}/design.md", f"tasks/{module_id}/regression.md"


def transition_node(tier_value: str | None, node: str, files: list[dict], module_id: str) -> str:
    """Decision 9: until the contract names 技术方案, a full-docs module sends its design as 节点：Spec listing the
    design and the regression document and not spec/<id>.md; that review is the design node."""
    listed = {f.get("path") for f in files}
    if (node == "spec" and full_docs(tier_value) and set(design_files(module_id)) <= listed
            and f"spec/{module_id}.md" not in listed):
        return "design"
    return node


SPEC_NODES = {"spec", "interface"}


def ready_to_start(tier_value: str, nodes_now: set[str], nodes_here: set[str]) -> tuple[bool, str | None]:
    """Decision 5, flow v2 only: (send the start notice now, why not when the approval would otherwise look like it).
    bug/small start once the requirement is approved; normal/important once the requirement and the design are.
    Like S53, re-approving a document already approved before does not start the build again."""
    gate = "design" if full_docs(tier_value) else "spec"
    has = {("spec" if n in SPEC_NODES else n) for n in nodes_now}
    here = {("spec" if n in SPEC_NODES else n) for n in nodes_here}
    if not ({"spec", gate} <= has):
        return False, None
    if gate not in here:
        return False, ("这次批的不是开工所需的最后一份（" + ("技术方案" if gate == "design" else "需求") + "以前已批），"
                       "没有发开工通知；修订是否影响已开工的构建由用户定")
    return True, None


def start_todo(module_id: str, step: str) -> str:
    """Decision 5: the start notice's 要你做什么 for a flow v2 module (`step` is sync.STEP)."""
    return (f"{step}（spec/{module_id}.md、tasks/{module_id}/ 冲突时 sync 自动取集成分支的版本，它带批准标记），"
            f"然后写 tasks/{module_id}/plan.md（只留任务与检查点）、tasks/{module_id}/todo.md，不交审，提交后按它构建；"
            "公共文件只能经【公共变更请求】改")


def after_release(tier_value: str | None, node: str, module_id: str) -> str | None:
    """The next step a 放行 notice names for a flow v2 module (None: an old module, today's text)."""
    if tier_value is None:
        return None
    if node in SPEC_NODES and full_docs(tier_value):
        return (f"写技术方案 tasks/{module_id}/design.md 与回归 tasks/{module_id}/regression.md，"
                "一起交审（节点 技术方案）")
    return "等开工通知"


# decision 11: a flow v2 module's final acceptance reports by regression case
CASE_LINE = re.compile(r"^\s*(?:[-*]\s*)?(R\d+)\s*[：:]")
REGRESSION_VIEW = "regressionView"      # interface draft v1 regression_view --json; name checked at Checkpoint 4


def case_ids(evidence: list[str]) -> list[str]:
    return [m.group(1) for line in evidence if (m := CASE_LINE.match(line))]


def regression_cases(where: Path, module_id: str) -> list[dict] | None:
    """spec-guard's parsed regression cases for the module, or None when the installed spec-guard has no reader
    (module-crew never parses the Markdown itself)."""
    from module_crew import probe
    found = probe.find_plugin("spec-guard", where)
    if isinstance(found, str):
        return None
    doc = probe.read_interface(found.root, probe.SPEC_GUARD_MAJOR)
    if isinstance(doc, str) or not isinstance(doc.get(REGRESSION_VIEW), dict):
        return None
    cmd = probe.safe_command(found.root, doc, REGRESSION_VIEW, {"<project-root>": str(where), "<module-id>": module_id})
    if isinstance(cmd, str):
        return None
    try:
        ran = subprocess.run(cmd, cwd=found.root, capture_output=True, text=True, timeout=probe.MAP_TIMEOUT)
        got = json.loads(ran.stdout) if ran.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    cases = got.get("cases") if isinstance(got, dict) else got
    return [c for c in cases if isinstance(c, dict)] if isinstance(cases, list) else None


def final_reasons(evidence: list[str], cases: list[dict] | None, module_id: str) -> list[str]:
    """Why a flow v2 final acceptance is refused: no R<n> line at all, or (with spec-guard's reader) cases left out.
    manual cases are the user's to test and may be missing or written 待用户测."""
    have = set(case_ids(evidence))
    if not have:
        return [f"新流程模块的「验收结果」按回归用例写：每行以用例编号开头（R1：<结果与证据>），用例见 tasks/{module_id}/regression.md"
                "（bug／小改动见 spec 的回归用例一节）"]
    if cases is None:
        return []
    missing = [str(c.get("id")) for c in cases
               if c.get("id") and str(c.get("id")) not in have and (c.get("method") or c.get("execution")) != "manual"]
    return [f"「验收结果」缺这些回归用例：{'、'.join(missing)}（执行方式为 manual 的写「待用户测」即可）"] if missing else []
