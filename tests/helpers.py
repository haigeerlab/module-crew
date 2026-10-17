"""Shared test helpers: throwaway git repositories and worktrees under a temp dir."""

from __future__ import annotations

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
