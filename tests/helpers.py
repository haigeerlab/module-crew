"""Shared test helpers: throwaway git repositories and worktrees under a temp dir."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_TMP_ROOT = Path(tempfile.gettempdir()).resolve()


def git(cwd: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t",
                          "-c", "commit.gpgsign=false", *args],
                         check=True, capture_output=True, text=True)
    return out.stdout


def make_repo(parent: Path) -> Path:
    repo = parent / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_text("x\n")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "init")
    return repo


def make_worktree(repo: Path, name: str) -> Path:
    path = repo.parent / name
    git(repo, "worktree", "add", "-q", "-b", name, str(path))
    return path


class RepoCase(unittest.TestCase):
    """Each test gets a fresh repo under the system temp dir; nothing else is touched."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="crew-test-")).resolve()
        assert self.tmp.is_relative_to(_TMP_ROOT), self.tmp
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = make_repo(self.tmp)

    def run_cli(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        return subprocess.run([str(PLUGIN_ROOT / "bin" / "module-crew"), *args], cwd=cwd or self.repo,
                              capture_output=True, text=True, env=env)


def allocate_worker(cwd: str, count: int) -> list[int]:
    """Run in a child process: allocate `count` numbers, one transaction and one item each."""
    from module_crew import store

    db = store.open_store(cwd)
    got = []
    for _ in range(count):
        with db.transaction(actor=f"p{os.getpid()}") as tx:
            n = tx.allocate_number()
            tx.put("item", str(n), {"pid": os.getpid()}, action="created")
        got.append(n)
    return got


FAKE_MAP = '''import json, os, sys, time
mode = os.environ.get("FAKE_MAP_MODE", "plain")
if os.environ.get("FAKE_MAP_FILE"):
    print(open(os.environ["FAKE_MAP_FILE"], encoding="utf-8").read())
    sys.exit(0)
if mode == "slow":
    time.sleep(5)
if mode == "exit3":
    print(json.dumps({"schemaVersion": 1, "error": "no-capability-map"}))
    sys.exit(3)
if mode == "garbage":
    print("not json")
    sys.exit(0)
doc = {"schemaVersion": 1, "totals": {"done": 1, "in_progress": 1}, "activeModule": "b",
       "modules": [{"id": "a", "status": "done"}, {"id": "b", "status": "in_progress"}, {"id": "c", "status": "ready"}]}
if mode in ("on", "on-no-startable"):
    doc["moduleConcurrency"] = "on"
    doc["buildOrderGroups"] = [["a"], ["b", "c"]]
if mode == "on":
    doc["startable"] = {"modules": ["c"], "conflicts": []}
print(json.dumps(doc))
'''


class FakePlugins:
    """Fake Claude install records plus fake spec-guard / agent-relay install dirs under a temp dir."""

    def __init__(self, root: Path):
        self.root = root
        self.records = root / "plugins" / "installed_plugins.json"
        self.records.parent.mkdir(parents=True, exist_ok=True)
        self.entries: dict[str, list] = {}
        self.count = 0
        self.write()

    def write(self) -> None:
        self.records.write_text(json.dumps({"version": 2, "plugins": self.entries}))

    def install(self, name: str, interface: dict | str | None, scope: str = "user",
                project: Path | None = None, map_script: bool = False) -> Path:
        self.count += 1
        path = self.root / "cache" / f"{name}-{self.count}"
        path.mkdir(parents=True)
        if isinstance(interface, dict):
            (path / "interface.json").write_text(json.dumps(interface))
        elif isinstance(interface, str):
            (path / "interface.json").write_text(interface)
        if map_script:
            (path / "hooks").mkdir()
            (path / "hooks" / "map_view.py").write_text(FAKE_MAP)
        entry = {"scope": scope, "installPath": str(path), "version": "9.9.9"}
        if project is not None:
            entry["projectPath"] = str(project)
        self.entries.setdefault(f"{name}@m", []).append(entry)
        self.write()
        return path


def spec_guard_interface(version: str = "1.0", command: list | None = None) -> dict:
    return {"interface": version, "mapView": {
        "command": command or ["python3", "-B", "hooks/map_view.py", "--json", "--project", "<project-root>"],
        "schemaVersion": 1}}


class ProbeCase(RepoCase):
    """RepoCase plus isolated plugin records; never reads the real ~/.claude."""

    def setUp(self) -> None:
        super().setUp()
        self.plugins = FakePlugins(self.tmp / "claude")
        old = os.environ.get("MODULE_CREW_PLUGINS_FILE")
        os.environ["MODULE_CREW_PLUGINS_FILE"] = str(self.plugins.records)
        self.addCleanup(lambda: os.environ.__setitem__("MODULE_CREW_PLUGINS_FILE", old) if old
                        else os.environ.pop("MODULE_CREW_PLUGINS_FILE", None))
        self.addCleanup(lambda: os.environ.pop("FAKE_MAP_MODE", None))
        self.addCleanup(lambda: os.environ.pop("FAKE_MAP_FILE", None))


def seed_sessions(db) -> None:
    """One coordinator, two active module sessions and one retired one."""
    rows = {
        "shop-coord": {"role": "coordinator", "host": "claude-desktop", "status": "active"},
        "shop-a": {"role": "dev", "host": "claude-desktop", "status": "active", "module": "a", "worktree": "/tmp/wa"},
        "shop-b": {"role": "dev", "host": "claude-desktop", "status": "active", "module": "b", "worktree": "/tmp/wb"},
        "shop-old": {"role": "dev", "host": "claude-desktop", "status": "retired", "module": "c", "worktree": "/tmp/wc"},
    }
    with db.transaction(actor="test") as tx:
        for name, rec in rows.items():
            tx.put("session", name, rec, action="registered")


WAIT_USER = """{marker}【等待用户】
结束：{end}
来自：{sender}
要你决定：{decide}
要点：
- 第一行要点
- 第二行要点
选项与我的建议：
推荐 A：方案甲
  选了会怎样：快
B：方案乙
  选了会怎样：稳
你该回：A
是否完全停住：是
"""


def wait_user(decide="先做哪个", end="无", sender="a", marker="", scope=""):
    text = WAIT_USER.format(marker=marker, end=end, sender=sender, decide=decide)
    if scope:
        text = text.replace("是否完全停住：是\n", f"是否完全停住：是\n{scope}")
    return text


START_MAP = {
    "schemaVersion": 1, "activeModule": None, "moduleConcurrency": "on",
    "buildOrderGroups": [["a"], ["b", "c", "d"], ["e"]],
    "modules": [
        {"id": "a", "responsibility": "地基", "dependsOn": [], "status": "done"},
        {"id": "b", "responsibility": "支付页", "dependsOn": ["a"], "status": "ready"},
        {"id": "c", "responsibility": "订单页", "dependsOn": ["a"], "status": "ready"},
        {"id": "d", "responsibility": "帮助页", "dependsOn": [], "status": "ready"},
        {"id": "e", "responsibility": "汇总", "dependsOn": ["b", "c"], "status": "not_ready"},
    ],
    "startable": {"modules": ["b", "c", "d"], "conflicts": []},
}


class StartCase(ProbeCase):
    """Relay 2.0 + spec-guard 1.1 whose /map --json is START_MAP (or whatever set_map writes)."""

    def setUp(self) -> None:
        super().setUp()
        self.plugins.install("agent-relay", {"interface": "2.0"})
        self.plugins.install("spec-guard", spec_guard_interface("1.1"), map_script=True)
        self.map_file = self.tmp / "map.json"
        self.set_map(START_MAP)
        os.environ["FAKE_MAP_FILE"] = str(self.map_file)

    def set_map(self, doc: dict) -> None:
        self.map_file.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
