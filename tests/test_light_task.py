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


if __name__ == "__main__":
    unittest.main()
