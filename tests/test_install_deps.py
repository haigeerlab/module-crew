"""S22 (T62): install dependencies first, and host-check runs the commit hooks (LIVE-SAAS: worktrees had no
node_modules, so lefthook/husky did nothing until review approve committed to the integration branch)."""

import fnmatch
import os
import unittest
from pathlib import Path
from unittest import mock

from helpers import PLUGIN_ROOT, ReviewCase, StartCase, git

from module_crew import hooks, hostcheck, permissions, start, store, tasks

FIRST = "先在本 worktree 装依赖，再写 Spec／动手"


def commit_files(repo: Path, *names: str) -> None:
    for name in names:
        (repo / name).write_text("x\n", encoding="utf-8")
    git(repo, "add", *names)
    git(repo, "commit", "-q", "-m", "lockfiles")


class InstallCommandsTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.root = Path(tempfile.mkdtemp(prefix="crew-test-"))
        self.addCleanup(__import__("shutil").rmtree, self.root, True)

    def cmds(self, *names):
        for name in names:
            (self.root / name).write_text("x\n", encoding="utf-8")
        return start.install_commands(self.root)

    def test_each_lockfile(self):
        cases = {"pnpm-lock.yaml": ["pnpm install --frozen-lockfile"], "package-lock.json": ["npm ci"],
                 "yarn.lock": ["yarn install"], "uv.lock": ["uv sync"]}
        for name, want in cases.items():
            with self.subTest(name=name):
                for p in self.root.iterdir():
                    p.unlink()
                self.assertEqual(self.cmds(name), want)

    def test_requirements_files_and_none(self):
        self.assertEqual(start.install_commands(self.root), [])
        self.assertEqual(self.cmds("requirements.txt", "requirements-dev.txt"),
                         ["python3 -m venv .venv", ".venv/bin/pip install -r requirements-dev.txt",
                          ".venv/bin/pip install -r requirements.txt"])

    def test_js_and_python_together(self):
        self.assertEqual(self.cmds("pnpm-lock.yaml", "uv.lock", "requirements.txt"),
                         ["pnpm install --frozen-lockfile", "uv sync"])

    def test_commands_are_allowed_by_both_hosts(self):
        """The generated commands must run without a permission prompt (permissions.LOCKFILE_*)."""
        names = ["pnpm-lock.yaml", "package-lock.json", "yarn.lock", "uv.lock", "requirements.txt"]
        for name in names:
            for p in self.root.iterdir():
                p.unlink()
            for cmd in self.cmds(name):
                with self.subTest(cmd=cmd):
                    self.assertTrue(any(fnmatch.fnmatchcase(cmd, pat) for pat in permissions.LOCKFILE_CLAUDE), cmd)
                    self.assertTrue(any(cmd == pre or cmd.startswith(pre + " ") for pre in permissions.LOCKFILE_CODEX), cmd)


class ModuleKickoffTest(StartCase):
    def test_module_kickoff_installs_first(self):
        commit_files(self.repo, "pnpm-lock.yaml")
        res = start.prepare(self.repo, ["b"], "开 b", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        text = store.read_body(store.open_store(self.repo), res.prepared[0]["kickoff"])
        self.assertIn(FIRST, text)
        self.assertIn("pnpm install --frozen-lockfile", text)
        self.assertLess(text.index(FIRST), text.index("这一步只做"))

    def test_no_lockfile_no_install_line(self):
        res = start.prepare(self.repo, ["b"], "开 b", short="shop")
        text = store.read_body(store.open_store(self.repo), res.prepared[0]["kickoff"])
        self.assertNotIn(FIRST, text)


class TaskKickoffTest(ReviewCase):
    def test_task_kickoff_installs_first(self):
        commit_files(self.repo, "package-lock.json")
        db = store.open_store(self.repo)
        hooks.bind(db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")
        n = tasks.add(db, self.repo, "feature", "改文档", "补一段说明", ["docs/t.md"], "说明写好", "加一段说明").number
        text = store.read_body(db, tasks.dispatch(db, self.repo, n).kickoff)
        self.assertIn(FIRST, text)
        self.assertIn("npm ci", text)
        self.assertLess(text.index(FIRST), text.index("做完、提交"))


class CommitHookCheckTest(StartCase):
    def setUp(self):
        super().setUp()
        res = start.prepare(self.repo, ["b"], "开 b", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        self.wt = res.prepared[0]["worktree"]

    def hook(self, body):
        path = self.repo / ".git" / "hooks" / "pre-commit"
        path.write_text(body, encoding="utf-8")
        os.chmod(path, 0o755)

    def check(self):
        rep = hostcheck.run(self.wt)
        return rep, next(c for c in rep.checks if c["id"] == "commit-hooks")

    def test_no_hooks(self):
        rep, c = self.check()
        self.assertTrue(c["ok"])
        self.assertEqual(rep.code, 0, rep.checks)

    def test_hook_runs(self):
        self.hook("#!/bin/sh\necho ok\n")
        rep, c = self.check()
        self.assertTrue(c["ok"], c)
        self.assertEqual(rep.code, 0)

    def test_hook_fails_reports_tail_and_install(self):
        commit_files(self.repo, "pnpm-lock.yaml")
        git(self.wt, "merge", "-q", "main")
        self.hook("#!/bin/sh\n" + "".join(f"echo line{i}\n" for i in range(20))
                  + "echo 'Can not find lefthook' >&2\nexit 1\n")
        rep, c = self.check()
        self.assertFalse(c["ok"])
        self.assertEqual(rep.code, 3)
        self.assertIn("Can not find lefthook", c["reason"])
        self.assertIn("line19", c["reason"])
        self.assertNotIn("line0\n", c["reason"] + "\n")
        self.assertIn("装依赖", c["fix"])
        self.assertIn("pnpm install --frozen-lockfile", c["fix"])
        self.assertIn("Can not find lefthook", "\n".join(hostcheck.render(rep)))

    def test_old_git_not_checked(self):
        self.hook("#!/bin/sh\nexit 1\n")
        with mock.patch.object(hostcheck, "git_version", return_value=(2, 35)):
            rep, c = self.check()
        self.assertTrue(c["ok"])
        self.assertIn("未检查", c["reason"])
        self.assertIn("2.36", c["reason"])


class SkillsTest(unittest.TestCase):
    def test_both_dev_skills_install_at_start(self):
        for path in (PLUGIN_ROOT / "skills" / "crew-dev" / "SKILL.md", PLUGIN_ROOT / "codex-skills" / "crew-dev" / "SKILL.md"):
            with self.subTest(path=path):
                self.assertIn("开工先装依赖", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
