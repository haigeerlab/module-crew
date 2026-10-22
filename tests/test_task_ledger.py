"""crew-task-ledger: the coordinator's record of light tasks (see spec/crew-task-ledger.md)."""

from __future__ import annotations

import argparse
import json
import unittest

from helpers import ReviewCase, StartCase, git

from module_crew import coordinator, hooks, refs, store, tasks


def add(db, project, expect=("src/a.py",), kind="feature", **kw):
    return tasks.add(db, project, kind, kw.pop("title", "导出按钮"), kw.pop("what", "加一个导出按钮"), list(expect),
                     kw.pop("done", "按钮能导出 CSV"), kw.pop("original", "加个导出按钮"), **kw)


class CoordCase(StartCase):
    def setUp(self):
        super().setUp()
        code, lines = coordinator.up(self.repo, "shop", "升级", session_id="sid-coord")
        assert code == 0, lines
        self.db = store.open_store(self.repo)


class RecordTest(CoordCase):
    """Acceptance 1, 9."""

    def test_add_records_and_numbers(self):
        with self.db.transaction(actor="t") as tx:
            before = tx.allocate_number()
            tx.put("item", str(before), {"state": "closed"}, action="created")
        r = add(self.db, self.repo)
        self.assertGreater(r.number, before)
        rec = store.get(self.db, "task", str(r.number))
        self.assertEqual((rec["type"], rec["state"], rec["expectedFiles"], rec["original"]),
                         ("feature", "ready", ["src/a.py"], "加个导出按钮"))
        self.assertEqual(refs.task(r.number), f"T{r.number}")
        again = add(self.db, self.repo, expect=("src/other.py",))
        self.assertEqual(again.number, r.number + 1)               # tasks advance the shared counter too
        with self.db.transaction(actor="t") as tx:
            self.assertEqual(tx.allocate_number(), again.number + 1)

    def test_refusals(self):
        for bad in ({"expect": ()}, {"expect": ("/abs/x",)}, {"expect": ("../x",)}, {"expect": ("a/../b",)},
                    {"kind": "chore"}, {"original": " "}, {"what": ""}, {"done": ""}, {"title": ""},
                    {"caused_by": "#3"}, {"caused_by": "X3"}):
            with self.subTest(bad=bad), self.assertRaises(tasks.TaskRefused):
                add(self.db, self.repo, **bad)

    def test_caused_by(self):
        first = add(self.db, self.repo)
        bug = add(self.db, self.repo, kind="bug", expect=("src/b.py",), caused_by=f"T{first.number}")
        self.assertEqual(store.get(self.db, "task", str(bug.number))["causedBy"], f"T{first.number}")
        c = add(self.db, self.repo, kind="bug", expect=("src/c.py",), caused_by="c12")
        self.assertEqual(store.get(self.db, "task", str(c.number))["causedBy"], "C12")

    def test_parse_accepts_t(self):
        self.assertEqual(refs.parse("T15"), 15)
        self.assertEqual(refs.parse("t7"), 7)
        with self.assertRaises(argparse.ArgumentTypeError):
            refs.parse("#15")

    def test_store_rejects_bad_record(self):
        with self.assertRaises(store.StoreError):
            with self.db.transaction(actor="t") as tx:
                tx.put("task", "99", {"type": "feature", "state": "nowhere", "expectedFiles": ["a"]}, action="added")


class NoCoordinatorTest(StartCase):
    def test_refused_without_coordinator(self):
        db = store.init_store(self.repo)[0]
        with self.assertRaises(tasks.TaskRefused) as ctx:
            add(db, self.repo)
        self.assertIn("模块协调", str(ctx.exception))


def set_state(db, n, state, **fields):
    with db.transaction(actor="t") as tx:
        tx.put("task", str(n), {**tx.get("task", str(n)), "state": state, **fields}, action="test")


class OverlapTest(ReviewCase):
    """Acceptance 2, 3: in-progress tasks, ready tasks and module branches' changed files."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def test_same_file_queues(self):
        first = add(self.db, self.repo, expect=("src/a.py",))
        set_state(self.db, first.number, "working")
        second = add(self.db, self.repo, expect=("src/a.py", "src/z.py"))
        self.assertEqual(second.state, "queued")
        self.assertEqual(second.clashes, [f"T{first.number}：src/a.py"])
        self.assertEqual(store.get(self.db, "task", str(second.number))["state"], "queued")

    def test_directory_contains(self):
        first = add(self.db, self.repo, expect=("src/",))
        self.assertEqual(add(self.db, self.repo, expect=("src/x.py",)).state, "queued")   # ready holds its files
        set_state(self.db, first.number, "cancelled")
        third = add(self.db, self.repo, expect=("lib/y.py",))
        self.assertEqual(third.state, "ready")
        self.assertEqual(add(self.db, self.repo, expect=("lib/",)).state, "queued")

    def test_returned_actual_files_count(self):
        first = add(self.db, self.repo, expect=("src/a.py",))
        set_state(self.db, first.number, "returned", result={"files": ["src/extra.py"]})
        self.assertEqual(add(self.db, self.repo, expect=("src/extra.py",)).state, "queued")

    def test_finished_tasks_do_not_count(self):
        for state in ("merged", "cancelled", "promoted"):
            t = add(self.db, self.repo, expect=(f"done/{state}.py",))
            set_state(self.db, t.number, state)
            self.assertEqual(add(self.db, self.repo, expect=(f"done/{state}.py",)).state, "ready", state)

    def test_module_branch_changes(self):
        r = add(self.db, self.repo, expect=("spec/b.md",))
        self.assertEqual(r.state, "queued")
        self.assertIn("模块 b：spec/b.md", r.clashes)

    def test_free_task_notes_modules(self):
        r = add(self.db, self.repo, expect=("docs/new.md",))
        self.assertEqual((r.state, r.clashes), ("ready", []))
        self.assertTrue(any("模块 b" in n and "以后可能" in n for n in r.notes), r.notes)


class QueueTest(CoordCase):
    """Acceptance 4, 5, 6."""

    def test_next_bug_first_and_one_of_two(self):
        holder = add(self.db, self.repo, expect=("src/",))
        set_state(self.db, holder.number, "working")
        feat = add(self.db, self.repo, expect=("src/a.py",))
        bug = add(self.db, self.repo, kind="bug", expect=("src/a.py",))
        other = add(self.db, self.repo, expect=("src/b.py",))
        self.assertEqual([feat.state, bug.state, other.state], ["queued"] * 3)
        self.assertEqual(tasks.next_ready(self.db, self.repo), [])              # still blocked
        set_state(self.db, holder.number, "merged")
        promoted = tasks.next_ready(self.db, self.repo)
        self.assertEqual(promoted, [bug.number, other.number])                 # bug first; feat clashes with the bug
        self.assertEqual(store.get(self.db, "task", str(feat.number))["state"], "queued")

    def test_advance_checks_transitions(self):
        t = add(self.db, self.repo)
        tasks.advance(self.db, t.number, "dispatched", assignee="shop-t1")
        tasks.advance(self.db, t.number, "working")
        with self.assertRaises(tasks.TaskRefused):
            tasks.advance(self.db, t.number, "promoted")
        tasks.advance(self.db, t.number, "returned", result={"files": ["src/a.py"]})
        tasks.advance(self.db, t.number, "merged")
        with self.assertRaises(tasks.TaskRefused):
            tasks.advance(self.db, t.number, "working")
        rec = store.get(self.db, "task", str(t.number))
        self.assertEqual((rec["state"], rec["assignee"]), ("merged", "shop-t1"))

    def test_queued_cannot_jump_to_merged(self):
        t = add(self.db, self.repo)
        with self.assertRaises(tasks.TaskRefused):
            tasks.advance(self.db, t.number, "merged")

    def test_cancel(self):
        t = add(self.db, self.repo)
        tasks.cancel(self.db, t.number, "不做了")
        rec = store.get(self.db, "task", str(t.number))
        self.assertEqual(rec["state"], "cancelled")
        ev = store.events(self.db, key=str(t.number), kind="task")[-1]
        self.assertEqual(ev["data"]["original"], "不做了")
        done = add(self.db, self.repo, expect=("x.py",))
        for state in ("dispatched", "working", "returned", "merged"):
            tasks.advance(self.db, done.number, state)
        with self.assertRaises(tasks.TaskRefused):
            tasks.cancel(self.db, done.number, "撤回")
        with self.assertRaises(tasks.TaskRefused):
            tasks.cancel(self.db, t.number, "")

    def test_unknown_number(self):
        with self.assertRaises(tasks.TaskRefused):
            tasks.advance(self.db, 999, "working")


class CliTest(CoordCase):
    """Acceptance 8 and the command line."""

    def words(self, text="加个导出按钮"):
        path = self.tmp / f"w{abs(hash(text))}.txt"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def cli_add(self, *extra, expect="src/a.py", kind="feature"):
        return self.run_cli("task", "add", "--type", kind, "--title", "导出", "--what", "加导出按钮", "--expect", expect,
                            "--done", "能导出 CSV", "--original-file", self.words(), *extra)

    def test_add_list_show_next_cancel(self):
        out = self.cli_add()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        n = store.records(self.db, "task")
        first = int(next(iter(n)))
        self.assertIn(f"已记下任务 T{first}", out.stdout)
        self.assertIn("可开", out.stdout)
        tasks.advance(self.db, first, "dispatched")
        second = self.cli_add("--json", expect="src/a.py,src/b.py", kind="bug")
        doc = json.loads(second.stdout)
        self.assertEqual((doc["state"], doc["clashes"]), ("queued", [f"T{first}：src/a.py"]))
        listed = self.run_cli("task", "list")
        self.assertIn(f"T{first}", listed.stdout)
        self.assertIn(f"T{doc['number']}", listed.stdout)
        shown = self.run_cli("task", "show", f"T{doc['number']}")
        self.assertIn("src/b.py", shown.stdout)
        self.assertIn("排队", shown.stdout)
        self.assertEqual(self.run_cli("task", "next").returncode, 0)
        bad = self.run_cli("task", "show", "T999")
        self.assertEqual(bad.returncode, 3)
        cancel = self.run_cli("task", "cancel", f"T{doc['number']}", "--original-file", self.words("这个 bug 不修了"))
        self.assertEqual(cancel.returncode, 0, cancel.stdout + cancel.stderr)
        self.assertEqual(store.get(self.db, "task", str(doc["number"]))["state"], "cancelled")
        self.assertNotIn(f"T{doc['number']}", self.run_cli("task", "list").stdout)
        self.assertIn(f"T{doc['number']}", self.run_cli("task", "list", "--all").stdout)

    def test_refusal_exit_3(self):
        out = self.cli_add(expect="../x")
        self.assertEqual(out.returncode, 3)
        self.assertIn("相对路径", out.stderr)

    def test_show_rejects_other_kinds(self):
        with self.db.transaction(actor="t") as tx:
            n = tx.allocate_number()
            tx.put("item", str(n), {"state": "open"}, action="created")
        self.assertEqual(self.run_cli("task", "show", f"C{n}").returncode, 3)

    def test_takeover_keeps_tasks(self):
        self.cli_add()
        before = store.records(self.db, "task")
        hooks.takeover(self.db, "shop-coord", "换个会话接管")
        hooks.bind(self.db, "shop-coord", "sid-new", self.repo, original="你来做模块协调")
        self.assertEqual(store.records(self.db, "task"), before)


if __name__ == "__main__":
    unittest.main()
