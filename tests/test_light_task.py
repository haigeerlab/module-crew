"""crew-light-task: dispatch, hand-back, merge and escalation of light tasks (see spec/crew-light-task.md)."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from helpers import MergeCase, ReviewCase, git, make_worktree

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


def hand_back(n, wt, files, points=("- 做了：补说明", "- 实测：python3 -m unittest，OK", "- 没验证：无")):
    import hashlib
    lines = [f"- {f} sha256:{hashlib.sha256((Path(wt) / f).read_bytes()).hexdigest()[:16]}" for f in files]
    return "\n".join(["【交审】", "结束：无", "模块：无", "节点：最终验收", "文件：", *lines, "要点：", *points,
                      f"任务：T{n}", "改动统计：", "  1 file changed", "越界检查：与任务单一致"]) + "\n"


class TaskWorkCase(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")

    def start_task(self, expect=("docs/t.md",), kind="feature", write=("docs/t.md",)):
        n = new_task(self.db, self.repo, expect=expect, kind=kind)
        d = tasks.dispatch(self.db, self.repo, n)
        hooks.bind(self.db, d.relay, f"sid-t{n}", d.worktree)
        wt = Path(d.worktree)
        for f in write:
            (wt / f).parent.mkdir(parents=True, exist_ok=True)
            (wt / f).write_text(f"{f}\n", encoding="utf-8")
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", f"T{n}")
        return n, d


class HandBackTest(TaskWorkCase):
    """Acceptance 4, 7."""

    def test_recorded_and_returned(self):
        from module_crew import review
        n, d = self.start_task()
        out = review.add(self.db, hand_back(n, d.worktree, ["docs/t.md"]), d.relay, 501)
        self.assertEqual(out.code, 0, out.lines)
        rec = store.get(self.db, "item", str(out.number))
        self.assertEqual((rec["task"], rec["module"], rec["node"], rec["extraFiles"]), (n, None, "final", []))
        t = store.get(self.db, "task", str(n))
        self.assertEqual((t["state"], t["result"]["files"]), ("returned", ["docs/t.md"]))
        self.assertIn(f"T{n}", "\n".join(out.lines))

    def test_extra_files_and_overlap(self):
        from module_crew import review
        n, d = self.start_task(write=("docs/t.md", "docs/extra.md", "spec/b.md"))
        out = review.add(self.db, hand_back(n, d.worktree, ["docs/t.md"]), d.relay, 502)
        self.assertEqual(out.code, 0, out.lines)
        rec = store.get(self.db, "item", str(out.number))
        self.assertEqual(rec["extraFiles"], ["docs/extra.md", "spec/b.md"])
        self.assertEqual(rec["overlapExtra"], ["模块 b：spec/b.md"])
        self.assertTrue(any("越界重叠" in l and "升格" in l for l in out.lines), out.lines)

    def test_refusals(self):
        from module_crew import review
        n, d = self.start_task()
        text = hand_back(n, d.worktree, ["docs/t.md"])
        self.assertEqual(review.add(self.db, text, "shop-b", 503).code, 3)          # a module session
        tasks.advance(self.db, n, "escalated")
        self.assertEqual(review.add(self.db, text, d.relay, 504).code, 3)           # not working

    def test_bug_without_repro_hint(self):
        from module_crew import review
        n, d = self.start_task(kind="bug")
        out = review.add(self.db, hand_back(n, d.worktree, ["docs/t.md"]), d.relay, 505)
        self.assertEqual(out.code, 0, out.lines)
        self.assertTrue(any("复现测试" in l for l in out.lines), out.lines)

    def test_batch_and_hub(self):
        from module_crew import review, sources
        n, d = self.start_task()
        out = review.add(self.db, hand_back(n, d.worktree, ["docs/t.md"]), d.relay, 506)
        groups = review.batch(self.repo)["groups"]
        self.assertIn(f"T{n}", [g["module"] for g in groups])
        sources.add(self.db, "hub-a", "hub", "登记收件箱", protocol="2.4")
        bodies = [t for _, _, t in review.for_hub(self.repo)]
        self.assertFalse(any(f"任务：T{n}" in t for t in bodies))
        self.assertIn(out.number, review.held_for_old_hub(self.db, self.repo))
        sources.remove(self.db, "hub-a", "换成新版收件箱")
        sources.add(self.db, "hub-b", "hub", "登记新收件箱", protocol="2.5")
        texts = [t for _, _, t in review.for_hub(self.repo) if f"任务：T{n}" in t]
        self.assertEqual(len(texts), 1)
        self.assertNotIn("模块：", texts[0])


class TaskMergeTest(MergeCase):
    """Acceptance 5, 8."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")
        self.check = self.check_script(fail_if="BROKEN")

    start_task = TaskWorkCase.start_task

    def approve_task(self, kind="feature", write=("docs/t.md",), rid=600):
        from module_crew import merge, review
        n, d = self.start_task(kind=kind, expect=write, write=write)
        out = review.add(self.db, hand_back(n, d.worktree, list(write)), d.relay, rid)
        assert out.code == 0, out.lines
        return n, d, merge.approve(self.db, out.number, f"T{n} 验收通过").approval

    def test_queue_order(self):
        from module_crew import merge
        feat, _, a_feat = self.approve_task(write=("docs/f.md",), rid=601)
        mod = self.approve_final("c", 602)
        mod_b = self.approve_final("b", 603)
        bug, _, a_bug = self.approve_task(kind="bug", write=("docs/g.md",), rid=604)
        order = [n for n, _ in merge.queue(self.repo)]
        self.assertEqual(order, [a_bug, mod_b, mod, a_feat])        # bug, modules in Build order, feature

    def test_task_merge(self):
        from module_crew import merge
        n, d, approval = self.approve_task()
        res = merge.run(self.repo, check_command=self.check)
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(store.get(self.db, "task", str(n))["state"], "merged")
        self.assertTrue((self.repo / "docs" / "t.md").exists())
        kinds = {(x["to"], x["kind"]) for x in res.sends}
        self.assertIn((d.relay, "wrap-up"), kinds)
        self.assertIn(("shop-b", "sync-baseline"), kinds)
        self.assertIn(("shop-c", "sync-baseline"), kinds)
        wrap = next(x for x in res.sends if x["to"] == d.relay)
        self.assertTrue(Path(wrap["path"]).read_text(encoding="utf-8").rstrip().endswith(f"任务：T{n}"))
        self.assertFalse(any("最终验收那一格" in l or "gateTick" in l for l in res.lines), res.lines)
        cleaned = merge.cleanup(self.repo, f"T{n}", "收回")
        self.assertEqual(cleaned.code, 0, cleaned.lines)
        self.assertFalse(Path(d.worktree).exists())
        self.assertEqual(git(self.repo, "rev-parse", "--verify", f"task/t{n}").strip() != "", True)
        self.assertEqual(store.get(self.db, "session", d.relay)["status"], "retired")

    def test_task_returned_on_failed_check(self):
        from module_crew import merge, protocol
        n, d, approval = self.approve_task(write=("BROKEN",))
        before = git(self.repo, "rev-parse", "main")
        res = merge.run(self.repo, check_command=self.check)
        self.assertEqual(res.code, 5, res.lines)
        self.assertEqual(git(self.repo, "rev-parse", "main"), before)
        self.assertEqual(store.get(self.db, "task", str(n))["state"], "working")
        notice = Path(next(x for x in res.sends if x["to"] == d.relay)["path"]).read_text(encoding="utf-8")
        msg = protocol.parse(notice)
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual(msg.contract()["task"], f"T{n}")

    def test_working_task_gets_sync_notice(self):
        from module_crew import merge
        other, od = self.start_task(expect=("docs/o.md",), write=("docs/o.md",))
        self.approve_final("b", 610)
        res = merge.run(self.repo, check_command=self.check)
        self.assertEqual(res.code, 0, res.lines)
        self.assertIn((od.relay, "sync-baseline"), {(x["to"], x["kind"]) for x in res.sends})

    def test_cleanup_needs_merged(self):
        from module_crew import merge
        n, d = self.start_task()
        self.assertEqual(merge.cleanup(self.repo, f"T{n}", "收回").code, 3)


if __name__ == "__main__":
    unittest.main()
