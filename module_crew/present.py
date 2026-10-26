"""How approval requests are shown to the user (see spec/crew-review-display.md).

Pure presentation plus the few git and spec-guard reads it needs: the parallel-boundary overlap of the Specs under
review, the final-acceptance tables, and the request cards (start, shared change, stuck).
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
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
    # S19: the Specs go to the system temp dir, not the state dir under .git, so review batch stays read-only
    # (Codex's default sandbox refuses writes to .git); the files live only while scopeOverlap runs.
    with tempfile.TemporaryDirectory(prefix="crew-overlap-") as tmp:
        pairs = []
        for n, v in pending:
            text = _spec_text(db, v)
            if text is None:
                return unchecked(f"C{n} 的 Spec 从交审提交里取不出")
            path = Path(tmp) / f"C{n}-spec.md"
            path.write_bytes(text)
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
    out = {"docs": docs, "code": code, "commits": commits, "dependencies": deps,
           "specDiff": revised["diff"] if revised else None, "planKnown": bool(planned)}
    out["declared"] = _declared_section(project, db, rec["module"], out)
    return out


def _declared_section(project: Path, db: store.Store, module: str, t: dict) -> dict:
    """crew-declared-scope decision 7: move the declared public files out of the docs and code tables into a section
    of their own, mark early landings and undeclared dependencies; `off` leaves the tables exactly as before."""
    from module_crew import declared
    if not declared.enabled(db):
        return {"state": "off", "reason": None, "files": []}
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch") or ""
    checkout = probe._checkout_of(project, branch) if branch else None
    scope = declared.read(checkout, module) if checkout else declared.Declared(module, reason="找不到集成分支所在的 checkout")
    if not scope.usable:
        return {"state": "unavailable", "reason": scope.reason, "files": []}
    sessions = store.records(db, "session")
    early = [(int(k), v) for k, v in store.records(db, "request").items()
             if v.get("closedReason") == "landed" and v.get("fromModule")
             and (sessions.get(v.get("from")) or {}).get("module") == module]
    files = []
    for table in ("docs", "code"):
        keep = []
        for r in t[table]:
            if not scope.inside(r["path"]):
                keep.append(r)
                continue
            row = {k: v for k, v in r.items() if k != "beyondPlan"}
            hit = max((n for n, v in early if r["path"] in v.get("files", [])), default=None)
            if hit is not None:
                row["landed"] = {"request": hit, "commit": str(dict(early)[hit].get("commit") or "")[:7]}
            files.append(row)
        t[table] = keep
    names = {d.get("name") for d in scope.dependencies}
    t["dependencies"] = [d if d.endswith("有改动，请看差异") or d.split(" ", 1)[0] in names else d + "（未声明）"
                         for d in t["dependencies"]]
    return {"state": "ok", "reason": None, "files": files}


def table_lines(t: dict) -> list[str]:
    """The 「改了哪些文件」 and 「Spec 中途改过吗」 items of a final-acceptance card, in reviewKinds.final order."""
    row = lambda r: (f"- {r['status']} {r['path']}" + (f"（+{r['added']} −{r['deleted']}" if r["status"] != "删除" else "（")
                     + ("，超出 Plan" if r.get("beyondPlan") else "") + "）").replace("（）", "")
    lines = ["改了哪些文件："]
    lines += ["文档："] + ([row(r) for r in t["docs"]] or ["- 无"])
    lines += ["代码：" + ("" if t["planKnown"] else "（超出 Plan：无法判断（Plan 没写文件））")] + ([row(r) for r in t["code"]] or ["- 无"])
    lines += _declared_lines(t.get("declared") or {}, row)
    lines += ["提交："] + ([f"- {c}" for c in t["commits"]] or ["- 无"])
    lines += ["新增依赖："] + ([f"- {d}" for d in t["dependencies"]] or ["- 无"])
    if t["specDiff"]:
        lines += ["Spec 中途改过吗：改过，差异如下（批准这次验收即同时批准修订后的 Spec）："] + t["specDiff"].rstrip("\n").splitlines()
    else:
        lines.append("Spec 中途改过吗：没有")
    return lines


def _declared_lines(d: dict, row) -> list[str]:
    """crew-declared-scope decision 7: the 「声明内公共文件」 section, nothing when the switch is off."""
    if d.get("state") == "unavailable":
        return [f"声明内公共文件：声明不可用：{d['reason']}，名单内外没有区分"]
    if d.get("state") != "ok":
        return []
    def landed(r):
        text = row(r)
        if not r.get("landed"):
            return text
        mark = f"已提前落地 C{r['landed']['request']}（{r['landed']['commit']}）"
        return text[:-1] + f"，{mark}）" if text.endswith("）") else f"{text}（{mark}）"
    return ["声明内公共文件："] + ([landed(r) for r in d["files"]] or ["- 无"])


# ------------------------------------------------------------------ request cards (decision 3)

def render_request(head: str, items: list[tuple[str, str]], note: str, why: str, effect: str, block: str,
                   extra: list[str] = ()) -> list[str]:
    """spec-guard's card skeleton: 「<模块> · <节点> · <编号>」, the fixed items, 注意／推荐理由／批了会怎样, one copy block."""
    return ([head] + [f"{name}：{text}" for name, text in items] + list(extra)
            + [f"注意：{note or '无'}", f"推荐理由：{why}", f"批了会怎样：{effect}", "复制块：", block])


def card_text(lines: list[str]) -> str:
    """How a command prints a card: the coordinator shows it in the reply, the copy block in a code block of its own."""
    return "给用户看的正文：\n" + "\n".join(f"  {x}" for x in lines)


def start_card(project: Path, db: store.Store | None, modules: list[dict], conflicts: list[dict]) -> list[str]:
    cfg = (store.get(db, "config", "main") or {}) if db is not None else {}
    top = Path(probe._git(project, "rev-parse", "--show-toplevel").stdout.strip() or project)
    crew = Path(cfg.get("crewDir") or top.parent / f"{top.name}-crew")
    ids = "、".join(m["id"] for m in modules)
    where = "；".join(f"{m['id']}：{crew / m['id']}（分支 {m['id']}）" for m in modules)
    note = "；".join(f"{'、'.join(c.get('modules', []))} 在 {'、'.join(c.get('paths', []))} 会撞" for c in conflicts)
    return render_request(f"{ids} · 开工 · 批准后编号",
                          [("开哪些模块", "；".join(f"{m['id']}（{m.get('responsibility', '')}）" for m in modules)),
                           ("各自的 worktree 与分支", where), ("会话从哪个宿主开", "Claude 桌面版（要开 Codex 会话时说一声）")],
                          note, "能力图上这几个模块依赖都已就绪、并行边界不冲突，有空位",
                          "为每个模块建 worktree 与分支、登记会话、生成开工说明；不写代码、不合并", f"开 {ids}")


def change_card(db: store.Store, number: int) -> list[str]:
    rec = store.get(db, "request", str(number)) or {}
    sender = rec.get("from", "")
    module = (store.get(db, "session", sender) or {}).get("module") or sender
    return render_request(f"{module} · 公共变更请求 · C{number}",
                          [("改哪些文件", "、".join(rec.get("files") or [])), ("为什么要改", rec.get("why", "")),
                           ("谁在等", f"{sender}" + ("（完全停住）" if rec.get("fullyStopped") else "（还能做别的）"))],
                          "公共文件改了会影响所有模块，批准后由模块协调改并通知各模块同步",
                          f"{module} 要改的是公共文件，按规矩不能自己改：{rec.get('what', '')}",
                          "模块协调在集成分支改这些文件、单独提交，再通知各模块同步", f"C{number} A")


def stuck_card(number: int, doc: dict, fields: dict) -> list[str]:
    module = doc.get("module") or "?"
    happened = next((p["text"] for p in doc.get("points") or [] if p["name"] == "出了什么事"), fields.get("要点", "").strip())
    options = [f"{o['letter']}：{o['text']}" + (f"（选了会怎样：{o['consequence']}）" if o.get("consequence") else "")
               for o in doc.get("options") or []]
    rec = doc.get("recommended") or "A"
    chosen = next((o for o in doc.get("options") or [] if o["letter"] == rec), {})
    return render_request(f"{module} · 卡住选做法 · C{number}", [("出了什么事", happened)],
                          "同一个目标第二次过不去，原因在模块以外", f"模块推荐 {rec}：{chosen.get('text', '')}",
                          chosen.get("consequence") or "按你选的做法继续", f"C{number} {rec}", extra=options)
