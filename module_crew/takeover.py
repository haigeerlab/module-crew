"""spec-guard takeover (interface 1.15): who approves each module's Spec and Plan, Codex as a reviewer, and narrowing
after an incident (see spec/crew-takeover-approve.md)."""

from __future__ import annotations

import hashlib
import json
import os
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


def predeclares(where: Path, module_id: str) -> str | None:
    """Why the Plan at `where` goes back to the user, or None: spec-guard's declaredScope decides, never parsed here
    (M1 note 11; codex-approval Q6). Malformed, unreadable or not answered counts as declaring something."""
    from module_crew import declared
    got = declared._interface(where)
    if isinstance(got, str):
        return f"读不到 spec-guard 的预先声明判定（{got}）"
    found, doc = got
    cmd = probe.safe_command(found.root, doc, "declaredScope", {"<project-root>": str(where), "<module-id>": module_id})
    if isinstance(cmd, str):
        return f"读不到 spec-guard 的预先声明判定（{cmd}）"
    try:
        ran = subprocess.run(cmd, cwd=found.root, capture_output=True, text=True, timeout=probe.MAP_TIMEOUT)
        result = json.loads(ran.stdout) if ran.returncode in (0, 4) else None
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return f"读不到 spec-guard 的预先声明判定（{exc}）"
    if ran.returncode == 4:
        code = result.get("error") if isinstance(result, dict) else None
        return f"Plan 预先声明格式错误（spec-guard：{code or '退出码 4'}）"
    if not isinstance(result, dict):
        return f"读不到 spec-guard 的预先声明判定（退出码 {ran.returncode}）"
    if result.get("declared") is True and any(result.get(k) for k in ("publicPaths", "dependencies", "configs", "patches")):
        return REASONS["pre-declared"]
    return None


def module(db: store.Store, project: str | os.PathLike, module_id: str, plan_root: Path | None = None,
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
    why = predeclares(Path(plan_root), module_id) if out.plan == "codex" and plan_root is not None else None
    if why:
        out.forced["plan"] = why
    return out


def approver(db: store.Store, project: str | os.PathLike, module_id: str, node: str,
             plan_root: Path | None = None) -> str:
    """"human" | "codex" for a review node; the interface proposal counts as the Spec, final acceptance follows
    final_reason (crew-takeover-merge decision 1)."""
    return approval(db, project, module_id, node, plan_root)[0]


def approval(db: store.Store, project: str | os.PathLike, module_id: str, node: str,
             plan_root: Path | None = None) -> tuple[str, str | None]:
    """(approver, why the user approves a step the takeover gives to Codex); `plan_root` is where spec-guard reads the
    Plan's pre-declared section (M1 notes 1, 11). The final acceptance: crew-takeover-merge's final_reason."""
    if node == "final":
        who, why = final_reason(db, project, module_id)
    else:
        item = {"spec": "spec", "interface": "spec", "plan": "plan"}.get(node)
        if item is None:
            return "human", None
        got = module(db, project, module_id, plan_root if item == "plan" else None)
        if getattr(got, item) != "codex":
            return "human", None
        who, why = ("human", got.forced[item]) if item in got.forced else ("codex", None)
    if who == "codex" and exhausted(db, module_id, node):
        return "human", EXHAUSTED
    return who, why


EXHAUSTED = "Codex 已审满两轮仍有阻断"


def exhausted(db: store.Store, module_id: str, node: str) -> bool:
    """M1-M2 report E: once Codex ran out of rounds for this module and node (since the module was last reopened),
    a resubmission goes to the user, as the over-limit draft's option B says."""
    since = store.round_since(store.records(db, "session"), module_id)
    items = store.records(db, "item")
    return any(e.get("type") == "item.codex-over-limit" and int(e["key"]) > since
               and (items.get(e["key"]) or {}).get("module") == module_id and (items.get(e["key"]) or {}).get("node") == node
               for e in store.events(db, kind="item"))


def final_reason(db: store.Store, project: str | os.PathLike, module_id: str) -> tuple[str, str | None]:
    """crew-takeover-merge decision 1, assumption 3: ("codex", None) when the module's merge is auto and the check
    ledger is on and its Spec and Plan are approved; ("human", reason) when merge is auto but one is missing;
    ("human", None) otherwise."""
    got = module(db, project, module_id)
    if not got.usable or got.merge != "auto":
        return "human", None
    from module_crew import checks, review
    if not checks.enabled(store.get(db, "config", "main")):
        return "human", "项目没开检查记账（checkLedger）或缺完整检查、快检查命令"
    done = review._approved_nodes(db).get(module_id, set())
    missing = [NODE for key, NODE in (("spec", "Spec"), ("plan", "Plan")) if key not in done]
    if missing:
        return "human", "、".join(missing) + " 还没批准"
    return "codex", None


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
    # M1-M2 report D: one event each time Codex runs out of rounds; codex-fallback later hands the item to the user
    out["overLimit"] = sum(1 for e in store.events(db, kind="item") if e.get("type") == "item.codex-over-limit")
    return out


def merge_counts(db: store.Store) -> dict:
    """crew-takeover-merge decision 10: auto releases and what became of their merge approvals."""
    items = store.records(db, "item").values()
    auto = [v for v in items if v.get("kind") == "merge-approval" and v.get("auto")]
    return {"released": sum(1 for v in items if v.get("kind") == "auto-release"),
            "merged": sum(1 for v in auto if v.get("closedReason") == "merged"),
            "returned": sum(1 for v in auto if v.get("closedReason") == "returned")}


def status(db: store.Store, project: str | os.PathLike) -> dict | None:
    """`status --json` store.takeover: None while no project or module takes anything over."""
    doc, lines = report(db, project)
    setting = doc["takeover"]
    if not setting["usable"] or (setting["value"] in (None, "none") and not any(
            m["spec"] != "human" or m["plan"] != "human" or m["merge"] != "human" for m in doc["modules"])):
        return None
    counts = doc["codex"]
    merged = merge_counts(db)           # crew-takeover-merge decision 10
    lines.append(f"自动合：已放行 {merged['released']} 次，其中合入 {merged['merged']} 次、退回 {merged['returned']} 次")
    doc = {**doc, "merge": merged}
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


# ---------------------------------------------------------------- Codex as a reviewer (decisions 3 to 6)

CODEX_REWORK_LIMIT = 2                 # spec-guard: two rounds with blocking findings, then the user
CODEX_DIR = "codex"
DONE_OUTCOMES = ("findings", "no_findings_in_scope")
TASK_TEXT = ("按 spec-guard 对 {what} 的要求审这份文件；阻断意见（severity: blocking）只限「照这份文件做会做错或做不成」，"
             "其余写成建议（severity: suggestion）")
FINAL_TEXT = ("最终验收：先读 spec/{module}.md 的「验收标准」一节，对照它逐条核对这份最终补丁；阻断意见（severity: blocking）"
              "只限某条验收标准没做到、做错，或照这份补丁合进去会坏掉已有行为，其余写成建议（severity: suggestion）")


class CodexRefused(Exception):
    """Nothing recorded (exit 3)."""


@dataclass
class CodexResult:
    code: int = 0
    lines: list[str] = field(default_factory=list)
    sends: list[dict] = field(default_factory=list)
    draft: str | None = None


def _codex_item(db: store.Store, n: int) -> dict:
    rec = store.get(db, "item", str(n))
    if rec is None or rec.get("kind") != "review":
        raise CodexRefused(f"没有交审事项 C{n}")
    if rec.get("state") != "open":
        raise CodexRefused(f"交审事项 C{n} 已关闭（{rec.get('closedReason')}）")
    if rec.get("reviewer") != "codex":
        raise CodexRefused(f"C{n} 不是 Codex 放行的节点（照人批流程走 review approve）")
    if rec.get("overLimit"):
        raise CodexRefused(f"C{n} Codex 已审满两轮仍有阻断：交用户决定，不再交 Codex")
    return rec


def _base(db: store.Store, worktree: Path, commit: str) -> str | None:
    """crew-takeover-merge decision 2: the merge base of the integration branch and the submitted commit."""
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch") or ""
    got = probe._git(worktree, "merge-base", f"refs/heads/{branch}", commit) if branch else None
    return got.stdout.strip() if got is not None and got.returncode == 0 and got.stdout.strip() else None


def _target(rec: dict) -> str:
    return "plan" if rec["node"] == "plan" else "spec"


def _history(db: store.Store, rec: dict, n: int) -> list[str]:
    """Codex reports for this module and node so far, oldest first: a resubmission gets a new C number but keeps
    counting (M1 notes 2, 3), the same way review._rounds counts rework notices and spec-guard counts rounds."""
    since = store.round_since(store.records(db, "session"), rec["module"])
    out: list[str] = []
    for key, other in sorted(store.records(db, "item").items(), key=lambda kv: int(kv[0])):
        if (since < int(key) <= n and other.get("kind") == "review" and other.get("module") == rec["module"]
                and other.get("node") == rec["node"]):
            out += list(other.get("codexReports") or [])
    return out


def codex_command(db: store.Store, n: int) -> tuple[list[str], Path]:
    """`review codex C<n>` (read only): the /delegate:review line for this round and where to save its stdout."""
    rec = _codex_item(db, n)
    reports = _history(db, rec, n)
    path = db.path / CODEX_DIR / f"C{n}-r{len(reports) + 1}.json"
    session = store.get(db, "session", rec["from"]) or {}
    worktree = session.get("worktree", "")
    args = ["/delegate:review", "--backend", "codex", "--repo", worktree]
    if rec["node"] == "final":          # crew-takeover-merge decision 2: the final patch as a commit range
        base = _base(db, Path(worktree), rec["commit"]) if worktree else None
        if base is None:
            raise CodexRefused(f"C{n} 取不到集成分支与交审提交 {rec['commit'][:7]} 的合并基点")
        args += ["--base", base, "--head", rec["commit"], "--spec", f"spec/{rec['module']}.md"]
    else:
        for f in rec["files"]:
            args += ["--paths", f["path"]]
        if rec["node"] == "plan":
            args += ["--spec", f"spec/{rec['module']}.md"]
    if reports:
        args += ["--previous-report", reports[-1]]
    what = WHAT[rec["node"]]
    args.append(json.dumps(FINAL_TEXT.format(module=rec["module"]) if rec["node"] == "final"
                           else TASK_TEXT.format(what=what), ensure_ascii=False))
    lines = [f"C{n}（{rec['module']} 的 {what}）第 {len(reports) + 1} 次交 Codex 审：由模块协调在本会话运行",
             "  " + " ".join(args),
             f"把标准输出的那份 JSON 原样存到 {path}，再运行 module-crew review codex-note C{n} --report {path}",
             "Codex 跑不成也照样交给 codex-note（它会停下、给出问用户的草稿）；不要自己审，也不要换后端"]
    head = probe._git(Path(worktree), "rev-parse", "HEAD").stdout.strip() if worktree else ""
    if head and head != rec["commit"]:
        lines.append(f"注意：模块 worktree 的 HEAD（{head[:7]}）不是交审提交（{rec['commit'][:7]}）；审的内容对不上时 codex-note 会拒收")
    return lines, path


def _report(path: str | os.PathLike) -> tuple[dict | None, str | None]:
    """The report, or why there is no conclusion (spec-guard codex-approval assumption 2)."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"审查报告读不出（{exc.__class__.__name__}）"
    if not isinstance(doc, dict):
        return None, "审查报告不是 JSON 对象"
    if doc.get("backend") != "codex":
        return None, f"审查后端不是 codex（{doc.get('backend')}）"
    if doc.get("execution_status") != "completed":
        diag = [str(x) for x in doc.get("diagnostics") or [] if x]
        return None, (f"Codex 审查没跑完（execution_status：{doc.get('execution_status')}"
                      + (f"；diagnostics：{'、'.join(diag)}" if diag else "") + "）")
    if doc.get("review_outcome") not in DONE_OUTCOMES:
        return None, f"Codex 审查没有结论（review_outcome：{doc.get('review_outcome')}）"
    if doc.get("unreviewed"):
        return None, "Codex 审查只覆盖了一部分文件"
    return doc, None


def _repeats(path: str | os.PathLike) -> bool:
    """M1-M2 report B: delegate refused before starting Codex (conditions_missing), so the same command fails the
    same way again; rerunning it is not the recommendation."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(doc, dict) and doc.get("execution_status") == "conditions_missing"


def _mismatch(rec: dict, doc: dict, worktree: Path) -> list[str]:
    """Decision 4 as measured: every submitted file is in scope.files with the sha256 of the submitted commit."""
    files = ((doc.get("scope") or {}).get("files")) or {}
    out = []
    for f in rec["files"]:
        shown = subprocess.run(["git", "-C", str(worktree), "show", f"{rec['commit']}:{f['path']}"], capture_output=True)
        want = hashlib.sha256(shown.stdout).hexdigest() if shown.returncode == 0 else None
        got = files.get(f["path"]) if isinstance(files, dict) else None
        if got is None:
            out.append(f"{f['path']} 不在审查报告的范围里")
        elif want != got:
            out.append(f"{f['path']} 审的不是交审提交 {rec['commit'][:7]} 里的内容")
    return out


def _final_mismatch(db: store.Store, rec: dict, doc: dict, worktree: Path) -> list[str]:
    """crew-takeover-merge decision 4.2 / AC4: a commits-mode review from the merge base to the submitted commit X,
    with every file changed in that range at X's content."""
    scope = doc.get("scope") or {}
    line = scope.get("baseline") or {}
    base = _base(db, worktree, rec["commit"])
    if not isinstance(line, dict) or line.get("mode") != "commits":
        return ["审查报告不是按提交范围审的（scope.baseline.mode 不是 commits）"]
    out = []
    if line.get("to") != rec["commit"]:
        out.append(f"审的不是交审提交 {rec['commit'][:7]}（报告的 to 是 {str(line.get('to'))[:7]}）")
    if base is None or line.get("from") != base:
        out.append(f"审查起点不是集成分支与交审提交的合并基点 {(base or '?')[:7]}")
    if out:
        return out
    files = scope.get("files") if isinstance(scope.get("files"), dict) else {}
    changed = probe._git(worktree, "diff", "--name-only", "--no-renames", base, rec["commit"]).stdout.split()
    if not changed:
        return ["最终补丁是空的"]
    for path in changed:
        shown = subprocess.run(["git", "-C", str(worktree), "show", f"{rec['commit']}:{path}"], capture_output=True)
        if shown.returncode != 0:
            continue                    # deleted at X: delegate lists it as not reviewed, which _report refuses
        if files.get(path) != hashlib.sha256(shown.stdout).hexdigest():
            out.append(f"{path} 不在审查报告的范围里，或审的不是交审提交里的内容")
    return out


def _blocking(doc: dict) -> tuple[list[str], list[str]]:
    """(blocking, suggestions) as one-line texts; a missing severity is blocking; an unresolved recheck item too."""
    block, advice = [], []
    for f in doc.get("findings") or []:
        if not isinstance(f, dict):
            continue
        where = f"{f.get('file') or ''}{':' + str(f['line']) if f.get('line') else ''}"
        text = (f.get("title") or "").strip() + (f"（{where}）" if where else "")
        fix = (f.get("suggestion") or "").strip()
        (advice if f.get("severity") == "suggestion" else block).append(text + (f"：{fix}" if fix else ""))
    for item in ((doc.get("recheck") or {}).get("items")) or []:
        if isinstance(item, dict) and item.get("status") == "unresolved":
            block.append("上一轮的阻断意见没解决：" + ((item.get("finding") or {}).get("title") or "").strip())
    return block, advice


WHAT = {"spec": "Spec", "interface": "接口提案", "plan": "Plan", "final": "最终验收"}


def _coordinator(db: store.Store) -> str:
    return next((name for name, r in store.records(db, "session").items()
                 if r.get("role") == "coordinator" and r.get("status") == "active"), "模块协调")


FINAL_BY_USER = "之后照今天的最终验收：用户批准合并 merge approve、只接受验收 merge accept、要求修改 review answer"


REPEATS = "（delegate 没启动 Codex 就拒绝了，照同一条命令重跑会同样失败：先排除上面的原因）"


def unavailable_draft(db: store.Store, rec: dict, n: int, why: str, repeats: bool = False) -> str:
    """M1-M2 report B: the cause with delegate's diagnostics; a failure that repeats puts the user's way first."""
    from module_crew import offload
    what = WHAT[rec["node"]]
    rerun = ("A", "排除原因后重跑" if repeats else "等 Codex 恢复后重跑",
             f"运行 review codex C{n}，照它给的命令重跑" + (REPEATS if repeats else ""))
    if rec["node"] == "final":          # crew-takeover-merge decision 3
        user = ("B", "这一次由你验收", f"review codex-fallback C{n} --original-file <答复>；{FINAL_BY_USER}")
        return "\n".join(offload.draft(
            _coordinator(db), rec["module"], f"{rec['module']} 的最终验收（交审 C{n}）Codex 审查没跑成，下一步怎么办",
            f"Codex 审查没跑成：{why}。这一项是自动合，Codex 不可用时停下等你，不会改由 Claude 自己审",
            [user, rerun] if repeats else [rerun, user])) + "\n"
    user = ("B", "这一项这次改由你批", f"之后照人批流程：review codex-fallback C{n} --original-file <答复>，再 review approve C{n}")
    return "\n".join(offload.draft(
        _coordinator(db), rec["module"], f"{rec['module']} 的 {what}（交审 C{n}）Codex 审查没跑成，下一步怎么办",
        f"Codex 审查没跑成：{why}。这一项由 Codex 放行，Codex 不可用时停下等你，不会改由 Claude 自己审",
        [user, rerun] if repeats else [rerun, user])) + "\n"


def over_limit_draft(db: store.Store, rec: dict, n: int, block: list[str]) -> str:
    from module_crew import offload
    what = WHAT[rec["node"]]
    if rec["node"] == "final":          # crew-takeover-merge decision 3
        return "\n".join(offload.draft(
            _coordinator(db), rec["module"], f"{rec['module']} 的最终验收（交审 C{n}）Codex 两轮后仍有阻断，怎么办",
            f"Codex 审了 {CODEX_REWORK_LIMIT} 轮返工后仍有 {len(block)} 条阻断意见：" + "；".join(block[:5]),
            [("A", "你来验收这一版", f"review codex-fallback C{n} --original-file <答复>；{FINAL_BY_USER}"),
             ("B", "照阻断意见再改一轮，改完交你验收（不再交 Codex）",
              f"review codex-fallback C{n} --original-file <答复> 后用 review answer C{n} 退回；模块重交的最终验收照人合")])) + "\n"
    return "\n".join(offload.draft(
        _coordinator(db), rec["module"], f"{rec['module']} 的 {what}（交审 C{n}）Codex 两轮后仍有阻断，怎么办",
        f"Codex 审了 {CODEX_REWORK_LIMIT} 轮返工后仍有 {len(block)} 条阻断意见：" + "；".join(block[:5]),
        [("A", "你来批这一版", f"review codex-fallback C{n} --original-file <答复>，再 review approve C{n}"),
         ("B", "照阻断意见再改一轮，改完交你批（不再交 Codex）",
          f"review codex-fallback C{n} --original-file <答复> 后用 review answer C{n} 退回；模块重交的{what}照人批")])) + "\n"


def codex_note(project: str | os.PathLike, n: int, report: str | os.PathLike) -> CodexResult:
    """`review codex-note C<n> --report <json>`: record Codex's conclusion; blocking → rework (two rounds at most),
    none → land as Codex's approval; no conclusion → stop and ask the user. Never a review of Claude's own."""
    from module_crew import protocol, review
    project = Path(project)
    db = store.open_store(project)
    rec = _codex_item(db, n)
    doc, why = _report(report)
    if doc is None:
        with db.transaction(actor="coordinator") as tx:
            tx.put("item", str(n), tx.get("item", str(n)), action="codex-unavailable", data={"reason": why,
                                                                                            "report": str(report)})
        return CodexResult(5, [f"C{n} 没有记结论：{why}", "把下面这份【等待用户】自检后发给用户（照现有规则转）；不要自己审：", ""],
                           draft=unavailable_draft(db, rec, n, why, _repeats(report)))
    worktree = Path((store.get(db, "session", rec["from"]) or {}).get("worktree", "/nonexistent"))
    bad = _final_mismatch(db, rec, doc, worktree) if rec["node"] == "final" else _mismatch(rec, doc, worktree)
    if bad:
        raise CodexRefused("审查报告和交审对不上，没有记：" + "；".join(bad) + f"。重跑 review codex C{n}")
    block, advice = _blocking(doc)
    rounds = len(_history(db, rec, n)) + 1
    saved = db.path / CODEX_DIR / f"C{n}-r{rounds}.json"
    if Path(report).resolve() != saved.resolve():
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(Path(report).read_bytes())
    verdict = f"有须修改项{len(block)}条" if block else (f"通过，附建议{len(advice)}条" if advice else "通过")
    row = {"from": "codex", "ref": f"R-{rounds}", "verdict": verdict, "at": store.now(), "report": str(saved),
           "points": "\n".join([f"须修改：{x}" for x in block] + [f"建议{i}：{x}" for i, x in enumerate(advice, 1)]),
           "text": f"Codex 审查第 {rounds} 次（报告 {saved}）：{verdict}", "suggestions": advice}
    if block:
        row["changes"] = block
    res = CodexResult()
    with db.transaction(actor="coordinator") as tx:
        cur = tx.get("item", str(n))
        cur = dict(cur, reviews=list(cur.get("reviews") or []) + [row],
                   codexReports=list(cur.get("codexReports") or []) + [str(saved)])
        if block:                       # crew-takeover-merge: a later blocking report withdraws an earlier pass
            cur.pop("codex", None)
        tx.put("item", str(n), cur, action="codex-noted", data={"round": rounds, "blocking": len(block)})
        if block:
            done = review._rounds(db, cur["module"], cur["node"])
            if done >= CODEX_REWORK_LIMIT:
                tx.put("item", str(n), dict(cur, overLimit=True), action="codex-over-limit")
                res.code = 5
                res.draft = over_limit_draft(db, cur, n, block)
                res.lines += [f"C{n} Codex 审了 {CODEX_REWORK_LIMIT} 轮返工后仍有阻断：不再返工，交用户决定（不降档）",
                              "把下面这份【等待用户】自检后发给用户：", ""]
                return res
            target = _target(cur)
            first = ("按 Codex 对最终补丁的阻断意见改（最终验收这一轮不用在文件里记）：\n" if cur["node"] == "final" else
                     f"先在你的 worktree 运行 /spec-guard:review-mark --target {target} --state codex-reviewed "
                     f"--review {saved} --confirm（把这一轮记进文件），再按阻断意见改：\n")
            todo = (first
                    + "\n".join(f"{i}. {x}" for i, x in enumerate(block, 1))
                    + ("\n建议（自己决定吸收与否，在文件「外部审查意见」一节每条写一句理由）：" + "；".join(advice) if advice else "")
                    + "\n改完提交、重新发【交审】；不同意就在【交审】里写「不同意：R-" + str(rounds) + "：<理由>」"
                    + f"\n审查原文：module-crew review show C{n}")
            body = tx.allocate_number()
            meta = tx.write_body(body, protocol.render_coordination_notice(
                "rework", f"Codex 审查 R-{rounds}（交审 C{n}）", todo, round=done + 1))
            tx.put("item", str(n), cur, action="rework-sent",
                   data={"module": cur["module"], "node": cur["node"], "round": done + 1, "body": body, "reviewer": "codex"})
            res.sends.append({"kind": "rework", "to": cur["from"], "replyTo": None, "body": body, "path": db.path / meta["path"]})
            res.lines.append(f"C{n} Codex 有 {len(block)} 条阻断：返工第 {done + 1} 轮，通知 {cur['from']}")
            return res
    if rec["node"] == "final":          # crew-takeover-merge decision 3: recorded, released later by merge auto
        codex = {"verdict": "pass", "report": str(saved), "fingerprint": (doc.get("scope") or {}).get("fingerprint"),
                 "rounds": rounds, "suggestions": len(advice)}
        with db.transaction(actor="coordinator") as tx:
            tx.put("item", str(n), dict(tx.get("item", str(n)), codex=codex), action="codex-passed", data=codex)
        res.lines += [f"C{n} Codex 对最终补丁没有阻断意见（建议 {len(advice)} 条）：可以自动合",
                      f"下一步：module-crew merge auto C{n}（放后台跑：放行、合进集成分支、跑完整检查；不问用户）"]
        return res
    landed = review._approve(project, [n], "", codex={"report": str(saved), "rounds": rounds, "suggestions": len(advice)})
    res.code = landed.code if landed.code in (0, 3) else 4
    res.lines += [f"C{n} Codex 没有阻断意见（建议 {len(advice)} 条）：放行"] + landed.lines
    res.sends += landed.sends
    return res


def codex_fallback(db: store.Store, n: int, original: str) -> list[str]:
    """Decision 6: the user chose to approve this one themselves (Codex unavailable or over the limit)."""
    if not original or not original.strip():
        raise CodexRefused("用户原话不能为空：改由用户批要用户明确说")
    rec = store.get(db, "item", str(n))
    if rec is None or rec.get("kind") != "review" or rec.get("state") != "open" or rec.get("reviewer") != "codex":
        raise CodexRefused(f"C{n} 不是未答的 Codex 放行交审")
    why = "codex-over-limit" if rec.get("overLimit") else "codex-unavailable"
    with db.transaction(actor="coordinator") as tx:
        cur = tx.get("item", str(n))
        cur = {k: v for k, v in cur.items() if k not in ("sentTo", "sentAt")}
        if cur["node"] == "final":      # crew-takeover-merge: the user's choice already answered the over-limit question
            cur = {k: v for k, v in cur.items() if k != "overLimit"}
        tx.put("item", str(n), dict(cur, reviewer="human", fallback=why), action="codex-fallback",
               data={"original": original, **store.source_field()})
    if rec["node"] == "final":
        return [f"C{n} 这一次由用户验收（{why}）：照今天的最终验收，用户的答复到了再 merge approve／merge accept／review answer C{n}"]
    return [f"C{n} 改由用户批（{why}）：照人批流程，用户的答复到了再 review approve C{n} 或 review answer C{n}"]


# ---------------------------------------------------------------- narrowing after an incident (decision 9)

class NarrowFailed(Exception):
    pass


def _narrow_args(root: Path, doc: dict, where: Path, module_id: str | None, reason: str) -> list[str]:
    """takeoverNarrow.command filled in: --source module-crew, the optional --module, --confirm."""
    cmd = probe.safe_command(root, doc, "takeoverNarrow", {"<project-root>": str(where), "<source>": "module-crew"})
    if isinstance(cmd, str):
        raise NarrowFailed(cmd)
    out = []
    for x in cmd:
        if x == "[--module <module-id>]":
            out += ["--module", module_id] if module_id else []
        elif x == "[--confirm]":
            out.append("--confirm")
        elif x.startswith("<one line"):
            out.append(" ".join(reason.split())[:200])
        elif x.startswith("<") or x.startswith("["):
            raise NarrowFailed(f"takeoverNarrow.command 有不认识的占位符 {x}，没有运行")
        else:
            out.append(x)
    return out


def _taken(value) -> bool:
    if isinstance(value, dict):
        return any(v != "human" for v in value.values())
    return value not in (None, "none")


def narrow(db: store.Store, project: str | os.PathLike, module_id: str | None, reason: str) -> dict | None:
    """One step stricter through spec-guard (merge → Plan → Spec): the project, and the module too when it has its own
    entry. None when nothing is taken over. Commits .agent/config.json on the integration branch."""
    from module_crew import commits, unqueued
    where = checkout(db, project)
    got = _interface(where)
    if isinstance(got, str):
        raise NarrowFailed(got)
    found, doc = got
    if not isinstance(doc.get("takeoverNarrow"), dict):
        raise NarrowFailed("装的 spec-guard 没有 takeoverNarrow")
    setting = project_setting(db, project)
    if not setting["usable"]:
        raise NarrowFailed(setting["reason"])
    mod = module(db, project, module_id) if module_id else None
    targets = ([None] if _taken(setting["value"]) else []) + \
              ([module_id] if mod and mod.usable and mod.source.startswith("moduleTakeover")
               and any(getattr(mod, k) != "human" for k in ITEMS) else [])
    if not targets:
        return None
    before = {"项目": describe_value(setting["value"])}
    if mod and module_id in targets:
        before[module_id] = line(mod)
    for target in targets:
        cmd = _narrow_args(found.root, doc, where, target, reason)
        try:
            ran = subprocess.run(cmd, cwd=found.root, capture_output=True, text=True, timeout=probe.MAP_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise NarrowFailed(f"收窄命令没跑成（{exc}）") from exc
        if ran.returncode != 0:
            raise NarrowFailed(f"收窄命令退出码 {ran.returncode}：{(ran.stderr or ran.stdout).strip()[:200]}")
    after = {"项目": describe_value(project_setting(db, project)["value"])}
    if mod and module_id in targets:
        after[module_id] = line(module(db, project, module_id))
    rel = ".agent/config.json"
    if probe._git(where, "diff", "--quiet", "--", rel).returncode == 0:
        return None                                   # already the strictest: spec-guard wrote nothing
    probe._git(where, "add", "--", rel)
    ran = probe._git(where, "commit", "-q", "-m",
                     commits.message(f"接管档位收窄：{reason}", commits.prefix_of(db)), "--", rel)
    if ran.returncode != 0:
        raise NarrowFailed(f".agent/config.json 已收窄但提交失败：{(ran.stderr or ran.stdout).strip()[:200]}；请把它单独提交")
    unqueued.mark(db, where, "takeover-narrow")
    commit = probe._git(where, "rev-parse", "HEAD").stdout.strip()
    return {"before": before, "after": after, "commit": commit, "targets": [t or "项目" for t in targets]}
