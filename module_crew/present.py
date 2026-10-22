"""How approval requests are shown to the user (see spec/crew-review-display.md).

Pure presentation plus the few git and spec-guard reads it needs: the parallel-boundary overlap of the Specs under
review, the final-acceptance tables, and the request cards (start, shared change, stuck).
"""

from __future__ import annotations

import json
import re
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
    known = [c for c in map_conflicts if batch_mods & set(c.get("modules", []))]   # from the branch's Specs: still true
    unchecked = lambda why: {"state": "unchecked", "conflicts": known, "errors": [], "basis": None,
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


# ------------------------------------------------------------------ final acceptance tables (decisions 1, 2)

DOC_PREFIXES = ("docs/",)
STATUS = {"A": "新增", "M": "修改", "D": "删除", "R": "改名"}
MANIFESTS = ("package.json", "pyproject.toml", "go.mod", "Cargo.toml", "Gemfile")
_PKG_SKIP = {"name", "version", "description", "main", "type", "private", "license", "scripts", "dependencies",
             "devDependencies", "peerDependencies", "optionalDependencies", "engines"}


def _git(cwd: str | Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=30)


def is_doc(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return path.startswith(DOC_PREFIXES) or name.startswith(("README", "CHANGELOG")) or path.endswith(".md")


def _manifest(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return name in MANIFESTS or (name.startswith("requirements") and name.endswith(".txt"))


def _plan_paths(text: str) -> set[str]:
    """Paths the approved Plan names: in backticks, or on the lines of its 「会改哪些文件」 item."""
    found = set(re.findall(r"`([^`\s]+[./][^`\s]*)`", text))
    for line in text.splitlines():
        if re.match(r"^[-*\s#]*会改哪些文件", line):
            found |= {x.strip("`，、,;；。 ") for x in re.split(r"[、，,;；\s]+", line.split("：", 1)[-1].split(":", 1)[-1])
                      if "/" in x or "." in x}
    return {x for x in found if x}


def _beyond(path: str, planned: set[str]) -> bool:
    return not any(path == p or path.startswith(p.rstrip("/") + "/") for p in planned)


def _new_dependencies(wt: str, base: str, commit: str, path: str) -> list[str]:
    added = [x[1:] for x in _git(wt, "diff", "-U0", base, commit, "--", path).stdout.splitlines()
             if x.startswith("+") and not x.startswith("+++")]
    name = path.rsplit("/", 1)[-1]
    out = []
    for line in added:
        if name == "package.json":
            m = re.match(r'^\s*"([^"]+)"\s*:\s*"([^"]+)"', line)
            if m and m.group(1) not in _PKG_SKIP:
                out.append(f"{m.group(1)} {m.group(2)}")
        elif name.startswith("requirements"):
            m = re.match(r"^\s*([A-Za-z0-9_.\-\[\]]+)\s*([=<>!~].*)?$", line)
            if m and not line.strip().startswith(("#", "-")):
                out.append(" ".join(x.strip() for x in m.groups() if x))
        elif name == "pyproject.toml":
            m = re.match(r'^\s*"([A-Za-z0-9_.\-\[\]]+)\s*([=<>!~][^"]*)?"\s*,?\s*$', line)
            if m:
                out.append(" ".join(x.strip() for x in m.groups() if x))
        elif name == "go.mod":
            m = re.match(r"^\s*(?:require\s+)?([\w.\-/]+\.[\w.\-/]+)\s+(v[\w.\-+]+)", line)
            if m:
                out.append(f"{m.group(1)} {m.group(2)}")
        elif name == "Cargo.toml":
            m = re.match(r'^\s*([A-Za-z0-9_\-]+)\s*=\s*("[^"]+"|\{.*\})', line)
            if m:
                out.append(f"{m.group(1)} {m.group(2)}")
        elif name == "Gemfile":
            m = re.match(r"""^\s*gem\s+['"]([^'"]+)['"]""", line)
            if m:
                out.append(m.group(1))
    if added and not out:
        return [f"{path} 有改动，请看差异"]
    return [f"{x}（{path}）" for x in out]


def final_tables(project: Path, db: store.Store, rec: dict) -> dict:
    """Decision 1: docs, code, commits and new dependencies of a final review, from git, not the module's own counts."""
    wt = (store.get(db, "session", rec.get("from") or "") or {}).get("worktree") or str(project)
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch") or "HEAD"
    commit = rec["commit"]
    base = _git(wt, "merge-base", f"refs/heads/{branch}", commit).stdout.strip() or branch
    nums = {}
    for line in _git(wt, "diff", "--numstat", "-M", base, commit).stdout.splitlines():
        a, d, path = line.split("\t", 2)
        nums[path.split(" => ")[-1].rstrip("}")] = (int(a) if a.isdigit() else 0, int(d) if d.isdigit() else 0)
    plan = _git(wt, "show", f"refs/heads/{branch}:tasks/{rec['module']}/plan.md")
    planned = _plan_paths(plan.stdout) if plan.returncode == 0 else set()
    docs, code, deps = [], [], []
    for line in _git(wt, "diff", "--name-status", "-M", base, commit).stdout.splitlines():
        parts = line.split("\t")
        status, path = parts[0][:1], parts[-1]
        if path.startswith(("spec/", "tasks/")):
            continue
        added, deleted = nums.get(path, (0, 0))
        row = {"status": STATUS.get(status, status), "path": path, "added": added, "deleted": deleted}
        if is_doc(path):
            docs.append(row)
        else:
            row["beyondPlan"] = _beyond(path, planned) if planned else None
            code.append(row)
        if _manifest(path) and status != "D":
            deps += _new_dependencies(wt, base, commit, path)
    commits = list(reversed(_git(wt, "log", "--no-merges", "--format=%h %s", f"{base}..{commit}").stdout.splitlines()))
    revised = rec.get("specRevised")
    return {"docs": docs, "code": code, "commits": commits, "dependencies": deps,
            "specDiff": revised["diff"] if revised else None, "planKnown": bool(planned)}


def table_lines(t: dict) -> list[str]:
    """The 「改了哪些文件」 and 「Spec 中途改过吗」 items of a final-acceptance card, in reviewKinds.final order."""
    row = lambda r: (f"- {r['status']} {r['path']}" + (f"（+{r['added']} −{r['deleted']}" if r["status"] != "删除" else "（")
                     + ("，超出 Plan" if r.get("beyondPlan") else "") + "）").replace("（）", "")
    lines = ["改了哪些文件："]
    lines += ["文档："] + ([row(r) for r in t["docs"]] or ["- 无"])
    lines += ["代码：" + ("" if t["planKnown"] else "（超出 Plan：无法判断（Plan 没写文件））")] + ([row(r) for r in t["code"]] or ["- 无"])
    lines += ["提交："] + ([f"- {c}" for c in t["commits"]] or ["- 无"])
    lines += ["新增依赖："] + ([f"- {d}" for d in t["dependencies"]] or ["- 无"])
    if t["specDiff"]:
        lines += ["Spec 中途改过吗：改过，差异如下（批准这次验收即同时批准修订后的 Spec）："] + t["specDiff"].rstrip("\n").splitlines()
    else:
        lines.append("Spec 中途改过吗：没有")
    return lines
