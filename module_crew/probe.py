"""Read-only readiness checks and status summary (see spec/crew-probe.md).

Reads Claude's plugin install records and the dependencies' interface.json files,
runs only spec-guard's declared mapView command and git, and never writes.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from module_crew import store
from module_crew.store import NotInRepo

RELAY_MAJOR = 2
SPEC_GUARD_MAJOR = 1
PLANNING_MINOR = 1  # spec-guard interface 1.1 brings the planning layer
MAP_TIMEOUT = 10
MIN_GIT = (2, 31)
NO_MAP = "/map --json 报告项目没有能力图"


@dataclass(frozen=True)
class Check:
    id: str
    state: str  # ok / blocker / warning
    reason: str = ""
    fix: str = ""
    code: str = ""   # machine-readable cause for callers that tolerate one (crew-coordinator-switch)


@dataclass(frozen=True)
class Plugin:
    root: Path
    version: str | None


# ---------------------------------------------------------------- dependencies

def _records_file() -> Path:
    override = os.environ.get("MODULE_CREW_PLUGINS_FILE")
    return Path(override) if override else Path.home() / ".claude" / "plugins" / "installed_plugins.json"


def _directory_source(plugins_dir: Path, market: str, name: str) -> Plugin | None:
    """Claude loads a directory marketplace's plugin from its source, not from the cached copy."""
    try:
        known = json.loads((plugins_dir / "known_marketplaces.json").read_text(encoding="utf-8"))
        source = known[market]["source"]
        if source.get("source") != "directory":
            return None
        repo = Path(source["path"])
        listed = json.loads((repo / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        rel = next(p["source"] for p in listed["plugins"] if p.get("name") == name)
        root = (repo / rel).resolve()
        meta = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration):
        return None
    return Plugin(root, meta.get("version"))


def find_plugin(name: str, project: str | os.PathLike) -> Plugin | str:
    """Install dir of `name` for `project`; a project-scope install wins. A str is the reason it was not found."""
    path = _records_file()
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return f"找不到 Claude 的插件安装记录：{path}"
    except (OSError, ValueError) as exc:
        return f"插件安装记录读不出：{path}（{exc}）"
    # The host's install record is not a public interface (boundary review 5, 0.9.7): a shape module-crew does not
    # know is reported as such, never as "not installed".
    odd = lambda what: f"Claude 的插件安装记录格式和预期不同（宿主可能改了格式）：{path}，{what}"
    if not isinstance(records, dict):
        return odd("顶层不是对象")
    plugins = records.get("plugins")
    if not isinstance(plugins, dict):
        return odd("没有 plugins 对象")
    entries = []
    for key, value in plugins.items():
        if "@" not in key or key.split("@", 1)[0] != name:
            continue
        if not isinstance(value, list) or not all(isinstance(e, dict) for e in value):
            return odd(f"{key} 的条目不是对象列表")
        for e in value:
            if not isinstance(e.get("installPath"), str) or not e["installPath"]:
                return odd(f"{key} 的条目缺 installPath")
            entries.append({**e, "_market": key.split("@", 1)[1]})
    if not entries:
        return f"本机没有安装 {name}"
    here = os.path.realpath(project)
    scoped = [e for e in entries if e.get("projectPath") and os.path.realpath(e["projectPath"]) == here]
    users = [e for e in entries if e.get("scope") == "user"]
    chosen = (scoped or users or [None])[0]
    if chosen is None:
        return f"{name} 只装在别的项目里，这个仓库用不到"
    live = _directory_source(path.parent, chosen["_market"], name)
    return live or Plugin(Path(chosen["installPath"]), chosen.get("version"))


def read_interface(root: Path, major: int) -> dict | str:
    """interface.json of a dependency when its major version matches; a str is the reason it cannot be used."""
    path = root / "interface.json"
    if not path.exists():
        return f"没有 interface.json（{path}），版本太旧或安装不完整"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        version = str(doc["interface"])
        got = int(version.split(".")[0])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return f"interface.json 读不出：{path}（{exc}）"
    if got != major:
        return f"接口主版本是 {version}，需要 {major}.x"
    return doc


def _version_tuple(doc: dict) -> tuple[int, int]:
    parts = (str(doc.get("interface", "0")).split(".") + ["0"])[:2]
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return 0, 0


def check_relay(project: str | os.PathLike) -> Check:
    found = find_plugin("agent-relay", project)
    if isinstance(found, str):
        return Check("agent-relay", "blocker", found, "安装 agent-relay（接口 2.x），在本项目或用户级启用")
    doc = read_interface(found.root, RELAY_MAJOR)
    if isinstance(doc, str):
        return Check("agent-relay", "blocker", doc, "升级 agent-relay 到接口 2.x 的版本")
    return Check("agent-relay", "ok", f"agent-relay {found.version or '?'}，接口 {doc['interface']}")


def safe_command(root: Path, doc: dict, entry: str, fill: dict[str, str]) -> list[str] | str:
    """interface.json <entry>.command with placeholders filled in; a str says why it is unsafe to run."""
    command = (doc.get(entry) or {}).get("command")
    if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
        return f"interface.json 的 {entry}.command 不是字符串数组，不安全，没有运行"
    if command[0] != "python3":
        return f"{entry}.command 不是以 python3 开头（{command[0]}），不安全，没有运行"
    scripts = [x for x in command[1:] if x.endswith(".py")]
    if len(scripts) != 1:
        return f"{entry}.command 里找不到唯一的脚本路径，不安全，没有运行"
    base = root.resolve()
    script = scripts[0]
    if os.path.isabs(script) or not (base / script).resolve().is_relative_to(base):
        return f"{entry}.command 的脚本 {script} 不在 spec-guard 安装目录内，不安全，没有运行"
    return [fill.get(x, x) for x in command]


def _map_command(root: Path, doc: dict, project: Path) -> list[str] | str:
    return safe_command(root, doc, "mapView", {"<project-root>": str(project)})


def run_map(root: Path, doc: dict, project: Path, timeout: float = MAP_TIMEOUT) -> dict | str:
    """Run spec-guard's declared /map --json; a str is the reason there is no usable result."""
    command = _map_command(root, doc, project)
    if isinstance(command, str):
        return command
    try:
        out = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"/map --json 超时（{timeout:g} 秒）"
    except OSError as exc:
        return f"/map --json 运行不了：{exc}"
    if out.returncode == 3:
        return NO_MAP
    if out.returncode != 0:
        return f"/map --json 退出码 {out.returncode}：{out.stderr.strip()[:200]}"
    try:
        result = json.loads(out.stdout)
    except ValueError:
        return "/map --json 的输出不是 JSON"
    if not isinstance(result, dict):
        return "/map --json 的输出不是 JSON 对象"
    return result


def check_spec_guard(project: str | os.PathLike, timeout: float = MAP_TIMEOUT) -> tuple[Check, Check, dict | None]:
    """(spec-guard, spec-guard-planning, map) for the project."""
    project = Path(project)
    fix_install = "安装并启用 spec-guard，在本仓库运行 /spec-guard:setup-convention"
    found = find_plugin("spec-guard", project)
    if isinstance(found, str):
        return (Check("spec-guard", "blocker", found, fix_install),
                Check("spec-guard-planning", "blocker", "spec-guard 不可用", fix_install), None)
    doc = read_interface(found.root, SPEC_GUARD_MAJOR)
    if isinstance(doc, str):
        return (Check("spec-guard", "blocker", doc, "安装接口 1.x 的 spec-guard"),
                Check("spec-guard-planning", "blocker", "spec-guard 不可用", "安装接口 1.x 的 spec-guard"), None)
    result = run_map(found.root, doc, project, timeout)
    if isinstance(result, str):
        no_map = result == NO_MAP
        fix = "按原因处理；没有能力图时先用 /spec 写能力图" if no_map else "检查 spec-guard 安装是否完整"
        return (Check("spec-guard", "blocker", result, fix, "no-capability-map" if no_map else ""),
                Check("spec-guard-planning", "blocker", "/map --json 不可用", fix), None)
    sg = Check("spec-guard", "ok", f"spec-guard {found.version or '?'}，接口 {doc['interface']}")
    return sg, _planning(doc, result), result


def check_enabled(project: Path) -> Check:
    """spec-guard is enabled for this project once setup-convention wrote .agent/config.json (crew-coordinator-switch)."""
    if (Path(project) / ".agent" / "config.json").is_file():
        return Check("spec-guard-enabled", "ok", "项目已启用 spec-guard")
    return Check("spec-guard-enabled", "blocker", "项目还没启用 spec-guard（没有 .agent/config.json）",
                 "先在本仓库运行 /spec-guard:setup-convention")


def _planning(doc: dict, result: dict) -> Check:
    """Planning layer usable = interface >= 1.1, switch on, and /map exposes startable."""
    if _version_tuple(doc) < (SPEC_GUARD_MAJOR, PLANNING_MINOR):
        return Check("spec-guard-planning", "blocker",
                     f"规划层未发版：当前 interface {doc['interface']}，需要 interface 1.1",
                     "等 spec-guard 发布规划层（预计 0.68.0）后升级")
    if result.get("moduleConcurrency") != "on":
        return Check("spec-guard-planning", "blocker", "moduleConcurrency 没有打开",
                     "用 /spec-guard:config 把 moduleConcurrency 设为 on")
    if not isinstance(result.get("startable"), dict):
        return Check("spec-guard-planning", "blocker", "/map --json 没有 startable",
                     "升级 spec-guard 到带可开工列表的版本")
    return Check("spec-guard-planning", "ok", "规划层可用")


# ---------------------------------------------------------------- repository

def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=30)


def check_git(project: str | os.PathLike) -> Check:
    """Raises NotInRepo outside a git repository; a bare repository or an old git is a blocker."""
    project = Path(project)
    inside = _git(project, "rev-parse", "--git-dir")
    if inside.returncode != 0:
        raise NotInRepo(f"{project} 不在 git 仓库里")
    version = subprocess.run(["git", "--version"], capture_output=True, text=True).stdout
    nums = tuple(int(x) for x in (version.split()[2].split(".")[:2] if len(version.split()) > 2 else []) if x.isdigit())
    if len(nums) < 2 or nums < MIN_GIT:
        return Check("git", "blocker", f"git 版本太旧：{version.strip()}，需要 2.31 以上", "升级 git")
    if _git(project, "rev-parse", "--is-bare-repository").stdout.strip() == "true":
        return Check("git", "blocker", "这是裸仓库，不能建 worktree 开发", "在有工作区的 checkout 里运行")
    return Check("git", "ok", version.strip())


def _integration_branch(project: Path) -> str | None:
    try:
        cfg = store.get(store.open_store(project), "config", "main") or {}
    except store.StoreError:
        cfg = {}
    branch = cfg.get("integrationBranch")
    if isinstance(branch, str) and branch:
        return branch
    head = _git(project, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    return None if head in ("", "HEAD") else head


def _checkout_of(project: Path, branch: str) -> Path | None:
    listing = _git(project, "worktree", "list", "--porcelain").stdout
    path = None
    for line in listing.splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree "):])
        elif line == f"branch refs/heads/{branch}" and path is not None:
            return path
    return None


def check_baseline(project: str | os.PathLike) -> Check:
    project = Path(project)
    branch = _integration_branch(project)
    if branch is None:
        return Check("baseline", "blocker", "当前不在任何分支上，也没有设定集成分支", "切到集成分支，或在状态库 config 里设 integrationBranch")
    checkout = _checkout_of(project, branch)
    if checkout is None:
        return Check("baseline", "blocker", f"集成分支 {branch} 没有被任何 checkout 检出",
                     f"在某个 checkout 里 git switch {branch}")
    changed = [x for x in _git(checkout, "--no-optional-locks", "status", "--porcelain").stdout.splitlines() if x.strip()]
    if changed:
        return Check("baseline", "blocker", f"集成分支所在的 checkout 不干净：{checkout}（{branch}）有 {len(changed)} 个文件未提交或未跟踪",
                     "提交或清理这些改动后再开工")
    return Check("baseline", "ok", f"集成分支 {branch}，在 {checkout}，工作区干净")


# ---------------------------------------------------------------- summary

OPEN_KINDS = ("item", "request", "ticket")


def summarize_store(project: Path) -> tuple[Check, dict | None]:
    try:
        db = store.open_store(project)
    except store.StoreNotFound:
        return Check("store", "warning", "未建库", "crew-start 开工时会建；也可以先运行 module-crew store init"), None
    except store.StoreError as exc:
        return Check("store", "warning", f"状态库读不出：{exc}", "运行 module-crew store check 排查"), None
    try:
        sessions = store.records(db, "session")
        open_counts = {k: sum(1 for r in store.records(db, k).values() if r.get("state") != "closed")
                       for k in OPEN_KINDS}
    except store.StoreError as exc:
        return Check("store", "warning", f"状态库读不出：{exc}", "运行 module-crew store check 排查"), None
    active = [{"name": name, **{k: rec.get(k) for k in ("role", "module", "worktree")}, "bound": bool(rec.get("hostSession"))}
              for name, rec in sorted(sessions.items()) if rec.get("status") == "active"]
    try:
        coord, seen = _coordinator_summary(db, sessions)
    except store.StoreError as exc:
        return Check("store", "warning", f"状态库读不出：{exc}", "运行 module-crew store check 排查"), None
    return Check("store", "ok", str(db.path)), {"sessions": active, "open": open_counts,
                                                "coordinator": coord, "sightings": seen}


SIGHTINGS_SHOWN = 10


def _coordinator_summary(db: store.Store, sessions: dict) -> tuple[dict | None, dict]:
    """crew-coordinator-switch: who the coordinator is, where, bound or not; and conversations seen but not registered."""
    from module_crew.hooks import _home_of
    coords = sorted(((n, s) for n, s in sessions.items() if s.get("role") == "coordinator"),
                    key=lambda kv: kv[1].get("status") != "active")
    coord = None
    if coords:
        name, rec = coords[0]
        home = _home_of(db, rec)
        coord = {"name": name, "state": rec.get("status"), "home": str(home) if home else None,
                 "branch": (store.get(db, "config", "main") or {}).get("integrationBranch"),
                 "bound": bool((rec.get("hostSession") or {}).get("sessionId"))}
    rows = sorted(store.records(db, "sighting").values(), key=lambda r: r.get("firstSeen") or "", reverse=True)
    recent = [{k: r.get(k) for k in ("cwd", "branch", "firstSeen", "told")} for r in rows[:SIGHTINGS_SHOWN]]
    return coord, {"count": len(rows), "recent": recent}


def summarize_map(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    modules = [m for m in doc.get("modules") or [] if isinstance(m, dict)]
    return {"done": sum(1 for m in modules if m.get("status") == "done"), "total": len(modules),
            "activeModule": doc.get("activeModule"),
            "inProgress": [m.get("id") for m in modules if m.get("status") == "in_progress"]}


@dataclass(frozen=True)
class Report:
    checks: dict[str, Check]
    store: dict | None
    map: dict | None = None
    startable: dict | None = field(default=None)

    @property
    def blocked(self) -> bool:
        return any(c.state == "blocker" for c in self.checks.values())

    def to_json(self) -> dict:
        return {"schemaVersion": 1, "blocked": self.blocked,
                "checks": [{"id": c.id, "state": c.state, "reason": c.reason, "fix": c.fix} for c in self.checks.values()],
                "store": self.store, "map": summarize_map(self.map), "startable": self.startable,
                "host": "模块协调：Claude 桌面版；模块会话：Claude 或 Codex 桌面版"}


def run(project: str | os.PathLike | None = None, timeout: float = MAP_TIMEOUT) -> Report:
    """All checks plus the summaries; raises NotInRepo outside a git repository. Never writes."""
    project = Path(project) if project is not None else Path.cwd()
    git_check = check_git(project)
    root = Path(_git(project, "rev-parse", "--show-toplevel").stdout.strip() or project)
    relay = check_relay(root)
    sg, planning, map_doc = check_spec_guard(root, timeout)
    enabled = check_enabled(root)
    baseline = check_baseline(root) if git_check.state == "ok" else Check("baseline", "blocker", "git 不可用")
    store_check, summary = summarize_store(root)
    checks = {c.id: c for c in (git_check, relay, sg, enabled, planning, baseline, store_check)}
    startable = map_doc.get("startable") if map_doc and planning.state == "ok" else None
    return Report(checks, summary, map_doc, startable)
