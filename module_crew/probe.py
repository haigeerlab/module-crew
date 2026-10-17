"""Read-only readiness checks and status summary (see spec/crew-probe.md).

Reads Claude's plugin install records and the dependencies' interface.json files,
runs only spec-guard's declared mapView command and git, and never writes.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

RELAY_MAJOR = 2
SPEC_GUARD_MAJOR = 1


@dataclass(frozen=True)
class Check:
    id: str
    state: str  # ok / blocker / warning
    reason: str = ""
    fix: str = ""


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
    entries = [{**e, "_market": key.split("@", 1)[1]}
               for key, value in ((records.get("plugins") or {}) if isinstance(records, dict) else {}).items()
               if key.split("@", 1)[0] == name and "@" in key
               for e in (value or []) if isinstance(e, dict)]
    if not entries:
        return f"本机没有安装 {name}"
    here = os.path.realpath(project)
    scoped = [e for e in entries if e.get("projectPath") and os.path.realpath(e["projectPath"]) == here]
    users = [e for e in entries if e.get("scope") == "user"]
    chosen = (scoped or users or [None])[0]
    if chosen is None:
        return f"{name} 只装在别的项目里，这个仓库用不到"
    live = _directory_source(path.parent, chosen["_market"], name)
    return live or Plugin(Path(chosen.get("installPath", "")), chosen.get("version"))


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
