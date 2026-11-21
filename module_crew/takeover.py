"""spec-guard takeover (interface 1.15): who approves each module's Spec and Plan, Codex as a reviewer, and narrowing
after an incident (see spec/crew-takeover-approve.md)."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from module_crew import probe, store

MIN_SPEC_GUARD = (0, 91, 0)
MIN_DELEGATE = (1, 5)
SHOW = ("python3", "-B", "hooks/project_config.py", "show", "--project", "<project-root>", "--format", "json")
ITEMS = ("spec", "plan", "merge")
WORDS = {"human": "人批", "codex": "Codex 放行"}
MERGE_WORDS = {"human": "人合", "auto": "自动合"}
REASONS = {"new-module": "新模块", "multi-module": "跨模块", "cross-module": "跨模块", "cross-unknown": "跨模块判不了",
           "risk-path": "碰高风险路径", "risk-unknown": "高风险清单读不到", "pre-declared": "Plan 有预先声明"}


@dataclass
class Items:
    """One module's effective takeover as module-crew applies it: human unless spec-guard gives the step to Codex."""
    module: str
    spec: str = "human"
    plan: str = "human"
    merge: str = "human"
    source: str = "default"
    forced: dict = field(default_factory=dict)     # item -> why the user approves whatever the takeover says
    usable: bool = False
    reason: str | None = None
    narrowed: dict | None = None

    @property
    def active(self) -> bool:
        return self.usable and (any(getattr(self, k) != "human" for k in ITEMS) or bool(self.forced))


def _version(text: str | None) -> tuple[int, ...] | None:
    try:
        return tuple(int(x) for x in (text or "").split("."))
    except ValueError:
        return None


def checkout(db: store.Store, project: str | os.PathLike) -> Path:
    """The tier is read where the integration branch is checked out (crew-autonomy-tier assumption 3)."""
    from module_crew import autonomy
    return autonomy.integration_checkout(db, project)


def _interface(where: Path):
    found = probe.find_plugin("spec-guard", where)
    if isinstance(found, str):
        return f"找不到 spec-guard（{found}）"
    doc = probe.read_interface(found.root, probe.SPEC_GUARD_MAJOR)
    if isinstance(doc, str):
        return doc
    if not isinstance(doc.get("takeover"), dict):
        return f"装的 spec-guard 接口 {doc.get('interface')} 低于 1.15（没有 takeover）"
    return found, doc


_CACHE: dict = {}


def _stamp(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def _map(where: Path) -> dict | str:
    """spec-guard's /map --json, read once per config change; a str says why there is none."""
    got = _interface(where)
    if isinstance(got, str):
        return got
    found, doc = got
    key = ("map", str(where), str(found.root), _stamp(where / ".agent" / "config.json"),
           _stamp(where / "spec" / "CAPABILITY-MAP.md"))
    if key not in _CACHE:
        _CACHE[key] = probe.run_map(found.root, doc, where)
    return _CACHE[key]


def predeclares(plan_text: str | None) -> bool:
    """A Plan whose 预先声明 section says anything but 无 (spec-guard codex-approval Q6: the user approves it)."""
    if not plan_text:
        return False
    m = re.search(r"^## 预先声明[^\n]*\n(.*?)(?=^## |\Z)", plan_text, re.S | re.M)
    if not m:
        return False
    for line in m.group(1).splitlines():
        text = line.strip().lstrip("-*").strip()
        if not text:
            continue
        text = text.split("：", 1)[1].strip() if "：" in text and not text.startswith("无") else text
        if not text.startswith("无"):
            return True
    return False


def module(db: store.Store, project: str | os.PathLike, module_id: str, plan_text: str | None = None,
           map_doc: dict | None = None) -> Items:
    """Decision 1 (as measured): the module's takeover from /map --json, then the user's own steps forced back."""
    doc = map_doc if map_doc is not None else _map(checkout(db, project))
    if isinstance(doc, str):
        return Items(module_id, reason=doc)
    row = next((m for m in doc.get("modules") or [] if isinstance(m, dict) and m.get("id") == module_id), None)
    if row is None:
        return Items(module_id, reason=f"/map --json 里没有模块 {module_id}")
    t = row.get("takeover")
    if not isinstance(t, dict):
        return Items(module_id, reason="/map --json 的模块没有 takeover（spec-guard 低于 0.91.0？）")
    out = Items(module_id, spec=t.get("spec") if t.get("spec") == "codex" else "human",
                plan=t.get("plan") if t.get("plan") == "codex" else "human",
                merge=t.get("merge") if t.get("merge") == "auto" else "human",
                source=str(t.get("source") or "default"), usable=True,
                narrowed=t.get("narrowed") if isinstance(t.get("narrowed"), dict) else None)
    reasons = (row.get("important") or {}).get("reasons") or []
    if out.spec == "codex" and reasons:
        out.forced["spec"] = "重要需求：" + "、".join(REASONS.get(r, r) for r in reasons)
    if out.plan == "codex" and predeclares(plan_text):
        out.forced["plan"] = REASONS["pre-declared"]
    return out


def approver(db: store.Store, project: str | os.PathLike, module_id: str, node: str, plan_text: str | None = None) -> str:
    """"human" | "codex" for a review node; the interface proposal counts as the Spec, final acceptance stays human."""
    item = {"spec": "spec", "interface": "spec", "plan": "plan"}.get(node)
    if item is None:
        return "human"
    got = module(db, project, module_id, plan_text)
    return "codex" if getattr(got, item) == "codex" and item not in got.forced else "human"


def line(items: Items) -> str:
    """Decision 2: 批准方式：Spec …、Plan …、合并 …"""
    def word(item: str) -> str:
        if item in items.forced:
            return f"人批（{items.forced[item]}）"
        return WORDS[getattr(items, item)]
    return f"批准方式：Spec {word('spec')}、Plan {word('plan')}、合并 {MERGE_WORDS[items.merge]}"


def project_setting(db: store.Store, project: str | os.PathLike) -> dict:
    """The project's takeover as spec-guard reports it (preset name or custom object)."""
    where = checkout(db, project)
    got = _interface(where)
    if isinstance(got, str):
        return {"value": "none", "source": "default", "usable": False, "reason": got}
    found, _ = got
    if not (found.root / SHOW[2]).resolve().is_relative_to(found.root.resolve()):
        return {"value": "none", "source": "default", "usable": False, "reason": f"{SHOW[2]} 不在 spec-guard 安装目录内，没有运行"}
    cmd = [str(where) if x == "<project-root>" else x for x in SHOW]
    try:
        ran = subprocess.run(cmd, cwd=found.root, capture_output=True, text=True, timeout=probe.MAP_TIMEOUT)
        items = json.loads(ran.stdout).get("items") if ran.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError) as exc:
        return {"value": "none", "source": "default", "usable": False, "reason": f"读档位的命令没跑成（{exc}）"}
    item = next((i for i in items or [] if isinstance(i, dict) and i.get("key") == "takeover"), None)
    if item is None:
        return {"value": "none", "source": "default", "usable": False, "reason": "spec-guard 的配置输出里没有 takeover"}
    return {"value": item.get("value"), "source": str(item.get("source") or "default"), "usable": True, "reason": None}


def describe_value(value) -> str:
    if isinstance(value, dict):
        return "自定义（" + "、".join(f"{k}={v}" for k, v in value.items()) + "）"
    return {"none": "不接管", "plan": "只接管 Plan", "merge": "接管到合并"}.get(value, str(value))


def in_use(db: store.Store) -> list[str]:
    sessions = store.records(db, "session")
    return sorted({r["module"] for r in sessions.values()
                   if r.get("role") == "dev" and r.get("status") == "active" and r.get("module")})


def report(db: store.Store, project: str | os.PathLike) -> tuple[dict, list[str]]:
    """`tier` (read only): the project's takeover and each module in use."""
    setting = project_setting(db, project)
    doc_map = _map(checkout(db, project))
    rows = [module(db, project, m, map_doc=doc_map if isinstance(doc_map, dict) else None) if isinstance(doc_map, dict)
            else Items(m, reason=doc_map) for m in in_use(db)]
    doc = {"takeover": setting,
           "modules": [{"module": r.module, "spec": r.spec, "plan": r.plan, "merge": r.merge, "forced": r.forced,
                        "source": r.source, "narrowed": r.narrowed} for r in rows if r.usable],
           "codex": codex_counts(db)}
    if not setting["usable"]:
        lines = [f"读不到接管档位：{setting['reason']}，按人批"]
    else:
        lines = [f"接管档位：{describe_value(setting['value'])}（{setting['source']}）"]
    lines += [f"{r.module}：{line(r)}" + (f"（模块单独设，{r.source}）" if r.source.startswith("moduleTakeover") else "")
              for r in rows if r.usable and r.active]
    return doc, lines


def codex_counts(db: store.Store) -> dict:
    """Decision 7: Codex approvals, kept apart from the user's."""
    out = {"spec": 0, "plan": 0, "reworked": 0, "overLimit": 0}
    for rec in store.records(db, "item").values():
        if rec.get("kind") == "codex-approval":
            for node in (rec.get("codex") or {}).get("nodes") or []:
                key = "spec" if node in ("spec", "interface") else node
                if key in out:
                    out[key] += 1
            out["reworked"] += 1 if (rec.get("codex") or {}).get("rounds", 1) > 1 else 0
        elif rec.get("kind") == "review" and rec.get("reviewer") == "codex" and rec.get("overLimit"):
            out["overLimit"] += 1
    return out


def status(db: store.Store, project: str | os.PathLike) -> dict | None:
    """`status --json` store.takeover: None while no project or module takes anything over."""
    doc, lines = report(db, project)
    setting = doc["takeover"]
    if not setting["usable"] or (setting["value"] in (None, "none") and not any(
            m["spec"] != "human" or m["plan"] != "human" or m["merge"] != "human" for m in doc["modules"])):
        return None
    counts = doc["codex"]
    lines.append(f"Codex 放行：Spec {counts['spec']} 次、Plan {counts['plan']} 次；其中返工后才放行 {counts['reworked']} 次；"
                 f"超限交用户 {counts['overLimit']} 次")
    return {**doc, "lines": lines}


def status_lines(doc: dict | None) -> list[str]:
    return [f"  {x}" for x in (doc or {}).get("lines") or []]


def preflight(db: store.Store, project: str | os.PathLike) -> tuple[int, list[str]]:
    """Before /spec-guard:config writes takeover: spec-guard ≥ 0.91.0 with takeover and takeoverNarrow, delegate ≥ 1.5."""
    where = checkout(db, project)
    reasons = []
    found = probe.find_plugin("spec-guard", where)
    if isinstance(found, str):
        reasons.append(f"找不到 spec-guard（{found}）")
    else:
        got = _version(found.version)
        if got is None or got < MIN_SPEC_GUARD:
            reasons.append(f"本机 spec-guard {found.version or '版本读不出'} 低于 0.91.0：先升级")
        doc = probe.read_interface(found.root, probe.SPEC_GUARD_MAJOR)
        if isinstance(doc, str):
            reasons.append(doc)
        elif not all(isinstance(doc.get(k), dict) for k in ("takeover", "takeoverNarrow")):
            reasons.append(f"装的 spec-guard 接口 {doc.get('interface')} 没有 takeover／takeoverNarrow（要 1.15）")
    dlg = probe.find_plugin("delegate", where)
    if isinstance(dlg, str):
        reasons.append(f"找不到 delegate（{dlg}）：Codex 放行要它")
    else:
        try:
            ddoc = json.loads((dlg.root / "interface.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            ddoc = {}
        report_doc = ((ddoc.get("review") or {}).get("report") or {})
        if (_version(str(ddoc.get("interface"))) or (0,)) < MIN_DELEGATE or "severity" not in report_doc:
            reasons.append(f"装的 delegate 接口 {ddoc.get('interface') or '读不出'} 低于 1.5（审查报告没有 severity）")
    if reasons:
        return 3, ["不能写 takeover：", *(f"- {r}" for r in reasons)]
    return 0, [f"可以写 takeover：本机 spec-guard {found.version}（接口有 takeover、takeoverNarrow），delegate 接口 ≥ 1.5。"
               "引用用户原话后用 /spec-guard:config 写入，写完把 .agent/config.json 单独提交"]
