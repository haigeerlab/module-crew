#!/usr/bin/env python3
"""Fixed command entry for sessions without hooks (see spec/crew-command-entry.md).

This file is copied as-is to <git-common-dir>/module-crew/bin/module-crew. Each run reads Claude's plugin install record,
finds the module-crew installed now (the same choice as probe.find_plugin) and hands over to its bin/module-crew, so
the path never names a version. It uses the standard library only and never imports module_crew: it has to find it first.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

NAME = "module-crew"


def _records_file() -> Path:
    override = os.environ.get("MODULE_CREW_PLUGINS_FILE")
    return Path(override) if override else Path.home() / ".claude" / "plugins" / "installed_plugins.json"


def _directory_source(plugins_dir: Path, market: str) -> Path | None:
    """Claude loads a directory marketplace's plugin from its source, not from the cached copy."""
    try:
        known = json.loads((plugins_dir / "known_marketplaces.json").read_text(encoding="utf-8"))
        source = known[market]["source"]
        if source.get("source") != "directory":
            return None
        repo = Path(source["path"])
        listed = json.loads((repo / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        rel = next(p["source"] for p in listed["plugins"] if p.get("name") == NAME)
        root = (repo / rel).resolve()
        json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, StopIteration):
        return None
    return root


def locate(project: str | os.PathLike) -> Path | str:
    """The install dir of module-crew for `project` (a project-scope install wins); a str says why there is none."""
    path = _records_file()
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return f"找不到 Claude 的插件安装记录：{path}"
    except (OSError, ValueError) as exc:
        return f"插件安装记录读不出：{path}（{exc}）"
    plugins = records.get("plugins") if isinstance(records, dict) else None
    if not isinstance(plugins, dict):
        return f"Claude 的插件安装记录格式和预期不同：{path}"
    entries = []
    for key, value in plugins.items():
        if "@" not in key or key.split("@", 1)[0] != NAME or not isinstance(value, list):
            continue
        entries += [{**e, "_market": key.split("@", 1)[1]} for e in value
                    if isinstance(e, dict) and isinstance(e.get("installPath"), str) and e["installPath"]]
    if not entries:
        return f"本机没有安装 {NAME}（安装记录 {path}）"
    here = os.path.realpath(project)
    scoped = [e for e in entries if e.get("projectPath") and os.path.realpath(e["projectPath"]) == here]
    users = [e for e in entries if e.get("scope") == "user"]
    chosen = (scoped or users or [None])[0]
    if chosen is None:
        return f"{NAME} 只装在别的项目里，这个仓库用不到"
    return _directory_source(path.parent, chosen["_market"]) or Path(chosen["installPath"])


def _project() -> Path:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return Path.cwd()
    return Path(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else Path.cwd()


def main(argv: list[str]) -> int:
    root = locate(_project())
    if isinstance(root, str):
        print(f"module-crew 固定入口：{root}", file=sys.stderr)
        return 2
    target = root / "bin" / NAME
    if not os.access(target, os.X_OK):
        print(f"module-crew 固定入口：装着的 {root} 里没有可执行的 bin/module-crew", file=sys.stderr)
        return 2
    os.execv(str(target), [str(target), *argv])
    return 2      # not reached


def entry(store_dir: str | os.PathLike) -> Path:
    """Where the launcher lives for a store."""
    return Path(store_dir) / "bin" / NAME


def install(store_dir: str | os.PathLike) -> tuple[Path, bool]:
    """Write this file as the store's launcher when its content differs; (path, changed). Never deletes anything."""
    target = entry(store_dir)
    data = Path(__file__).read_bytes()
    try:
        if target.read_bytes() == data:
            return target, False
    except OSError:
        pass
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".module-crew.")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.chmod(tmp, 0o755)
    os.replace(tmp, target)
    return target, True


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
