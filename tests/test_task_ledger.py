"""crew-task-ledger: the coordinator's record of light tasks (see spec/crew-task-ledger.md)."""

from __future__ import annotations

import argparse
import unittest

from helpers import ReviewCase, StartCase, git

from module_crew import coordinator, refs, store, tasks


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


if __name__ == "__main__":
    unittest.main()
