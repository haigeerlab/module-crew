"""crew-light-task: dispatch, hand-back, merge and escalation of light tasks (see spec/crew-light-task.md)."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from helpers import ReviewCase, git, make_worktree

from module_crew import hooks, start, store, tasks


def run(event, cwd, sid=None, **extra):
    payload = {"cwd": str(cwd), **({"session_id": sid} if sid else {}), **extra}
    out = hooks.run_hook(event, json.dumps(payload))
    return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""


def new_task(db, project, expect=("docs/t.md",), kind="feature"):
    return tasks.add(db, project, kind, "改文档", "补一段说明", list(expect), "说明写好", "加一段说明").number


def register_task(db, n, worktree, name=None):
    name = name or f"shop-t{n}"
    with db.transaction(actor="t") as tx:
        tx.put("session", name, {"role": "task", "host": "claude-desktop", "status": "active", "task": n,
                                 "worktree": str(worktree)}, action="registered")
    return name


class TaskRoleTest(ReviewCase):
    """The `task` registration role, slots and hooks."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")
        self.n = new_task(self.db, self.repo)
        self.wt = make_worktree(self.repo, f"task-t{self.n}")

    def test_store_validates_task_role(self):
        register_task(self.db, self.n, self.wt)
        for bad in ({"task": None}, {"task": "T3"}, {"worktree": "rel/path"}):
            with self.subTest(bad=bad), self.assertRaises(store.StoreError):
                with self.db.transaction(actor="t") as tx:
                    tx.put("session", "shop-tx", {"role": "task", "host": "claude-desktop", "status": "active",
                                                  "task": 99, "worktree": "/tmp/x", **bad}, action="registered")
        with self.assertRaises(store.StoreError):       # one in-use session per task
            register_task(self.db, self.n, self.wt, name="shop-other")

    def test_task_sessions_take_no_module_slot(self):
        before = start.plan(self.repo).slots
        register_task(self.db, self.n, self.wt)
        self.assertEqual(start.plan(self.repo).slots, before)

    def test_hook_in_task_worktree(self):
        name = register_task(self.db, self.n, self.wt)
        hooks.bind(self.db, name, "sid-task", self.wt)
        text = run("session-start", self.wt, "sid-task")
        self.assertIn(f"你是轻任务 T{self.n} 的会话", text)
        self.assertIn("你只和它说话", text)
        self.assertIn(f"T{self.n}", run("prompt", self.wt, "sid-task"))
        stranger = run("session-start", self.wt, "sid-other")
        self.assertIn(f"本目录属于轻任务 T{self.n}", stranger)
        self.assertIn(f"module-crew bind {name}", stranger)
        self.assertIsNone(store.get(self.db, "sighting", "sid-other"))

    def test_bind_only_in_its_worktree(self):
        name = register_task(self.db, self.n, self.wt)
        with self.assertRaises(hooks.BindRefused):
            hooks.bind(self.db, name, "sid-task", self.repo)


class DispatchTest(ReviewCase):
    """Acceptance 2, 3."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")

    def test_dispatch_ready_task(self):
        n = new_task(self.db, self.repo, kind="bug")
        slots = start.plan(self.repo).slots
        r = tasks.dispatch(self.db, self.repo, n)
        wt = self.tmp / "repo-crew" / f"task-t{n}"
        self.assertEqual((Path(r.worktree), r.branch, r.relay), (wt, f"task/t{n}", f"shop-t{n}"))
        self.assertEqual(git(wt, "rev-parse", "--abbrev-ref", "HEAD").strip(), f"task/t{n}")
        self.assertEqual(git(wt, "rev-parse", "HEAD"), git(self.repo, "rev-parse", "main"))
        sess = store.get(self.db, "session", f"shop-t{n}")
        self.assertEqual((sess["role"], sess["task"], sess["worktree"]), ("task", n, str(wt)))
        t = store.get(self.db, "task", str(n))
        self.assertEqual((t["state"], t["assignee"], t["branch"]), ("dispatched", f"shop-t{n}", f"task/t{n}"))
        text = store.read_body(self.db, r.kickoff)
        for words in (f"轻任务 T{n}", "补一段说明", "docs/t.md", "说明写好", f"module-crew bind shop-t{n}",
                      "模块协调：shop-coord", "先写一个能复现问题的测试", "模块：无", f"任务：T{n}", "越界检查",
                      "类型：卡住选做法", "不改公共文件"):
            self.assertIn(words, text)
        self.assertEqual(start.plan(self.repo).slots, slots)

    def test_only_ready(self):
        n = new_task(self.db, self.repo)
        tasks.advance(self.db, n, "cancelled")
        with self.assertRaises(tasks.TaskRefused):
            tasks.dispatch(self.db, self.repo, n)
        holder = new_task(self.db, self.repo, expect=("x/",))
        queued = new_task(self.db, self.repo, expect=("x/a",))
        self.assertEqual(store.get(self.db, "task", str(queued))["state"], "queued")
        with self.assertRaises(tasks.TaskRefused):
            tasks.dispatch(self.db, self.repo, queued)

    def test_bind_makes_working(self):
        n = new_task(self.db, self.repo)
        r = tasks.dispatch(self.db, self.repo, n)
        hooks.bind(self.db, r.relay, "sid-task", r.worktree)
        self.assertEqual(store.get(self.db, "task", str(n))["state"], "working")
        self.assertIn(f"你是轻任务 T{n} 的会话", run("session-start", r.worktree, "sid-task"))

    def test_cli(self):
        n = new_task(self.db, self.repo)
        out = self.run_cli("task", "dispatch", f"T{n}", "--json")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        doc = json.loads(out.stdout)
        self.assertEqual(doc["relay"], f"shop-t{n}")
        self.assertTrue(Path(doc["kickoffPath"]).exists())


if __name__ == "__main__":
    unittest.main()
