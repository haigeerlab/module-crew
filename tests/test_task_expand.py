"""S49: an escalated light task may be expanded and kept as a light task (answer D), via `task scope`."""

from __future__ import annotations

import argparse
import contextlib
import io
import os
from pathlib import Path
from unittest import mock

from test_light_task import TaskWorkCase, escalation, new_task

from module_crew import inbox, store, tasks


def escalation_with_d(n):
    return escalation(n).replace("  选了会怎样：丢弃改动\n",
                                 "  选了会怎样：丢弃改动\nD：批准扩项，继续当轻任务做\n  选了会怎样：任务单加上 src/cache.py\n")


class ExpandTest(TaskWorkCase):

    def escalate(self, text=escalation, expect=("docs/t.md",)):
        n, d = self.start_task(expect=expect)
        out = inbox.add(self.db, text(n), d.relay, 800)
        self.assertEqual(out.code, 0, out.lines)
        self.assertIn("扩项", " ".join(out.lines))
        return n, out.number

    def test_d_answer_points_to_task_scope(self):
        n, item = self.escalate(escalation_with_d)
        reply = inbox.answer(self.db, item, "扩项吧，加上 cache", "D")
        self.assertEqual(store.get(self.db, "task", str(n))["state"], "escalated")
        self.assertTrue(any("扩项" in x and f"task scope T{n}" in x for x in reply.notes), reply.notes)

    def test_expand_updates_card_and_goes_back_to_work(self):
        n, item = self.escalate(escalation_with_d)
        inbox.answer(self.db, item, "扩项吧", "D")
        r = tasks.scope(self.db, n, ["docs/t.md", "src/cache.py"], "说明与缓存都好", "加上 src/cache.py 一起做",
                        what="补说明并修缓存", project=self.repo)
        self.assertEqual(r.kind, "expanded")
        t = store.get(self.db, "task", str(n))
        self.assertEqual((t["state"], t["what"], t["expectedFiles"], t["done"]),
                         ("working", "补说明并修缓存", ["docs/t.md", "src/cache.py"], "说明与缓存都好"))
        last = store.events(self.db, key=str(n), kind="task")[-1]
        self.assertEqual((last["type"], last["data"]["original"]), ("task.expanded", "加上 src/cache.py 一起做"))
        text = Path(r.path).read_text(encoding="utf-8")
        for words in ("扩项", "补说明并修缓存", "src/cache.py", "说明与缓存都好"):
            self.assertIn(words, text)
        self.assertNotIn("缩小", text)

    def test_expand_reports_overlap_without_refusing(self):
        holder = new_task(self.db, self.repo, expect=("src/cache.py",))
        n, _ = self.escalate()
        r = tasks.scope(self.db, n, ["docs/t.md", "src/cache.py"], "说明写好", "加上 cache", project=self.repo)
        self.assertEqual(r.clashes, [f"T{holder}：src/cache.py"])
        self.assertEqual(store.get(self.db, "task", str(n))["state"], "working")
        self.assertEqual(store.events(self.db, key=str(n), kind="task")[-1]["data"]["clashes"], r.clashes)

    def test_expand_keeps_what_when_not_given(self):
        n, _ = self.escalate()
        tasks.scope(self.db, n, ["docs/", "src/cache.py"], "说明写好", "加上 cache", project=self.repo)
        self.assertEqual(store.get(self.db, "task", str(n))["what"], "补一段说明")

    def test_same_list_is_neither_shrink_nor_expand(self):
        n, _ = self.escalate()
        r = tasks.scope(self.db, n, ["docs/t.md"], "只改一点", "按原单做，标准改一下")
        self.assertEqual(r.kind, "adjusted")
        text = Path(r.path).read_text(encoding="utf-8")
        self.assertNotIn("缩小", text)
        self.assertNotIn("扩项", text)

    def test_working_task_cannot_change_what(self):
        n = new_task(self.db, self.repo, expect=("docs/", "src/a.py"))
        tasks.advance(self.db, n, "dispatched", assignee=f"shop-t{n}")
        with self.assertRaises(tasks.TaskRefused):
            tasks.scope(self.db, n, ["docs/t.md"], "说明写好", "收窄并改做法", what="别的事")
        self.assertEqual(store.get(self.db, "task", str(n))["expectedFiles"], ["docs/", "src/a.py"])

    def test_kickoff_offers_d(self):
        n = new_task(self.db, self.repo)
        d = tasks.dispatch(self.db, self.repo, n)
        self.assertIn("D 批准扩项", store.read_body(self.db, d.kickoff))

    def run_cli_scope(self, n, files, what=None):
        from module_crew import __main__ as cli
        args = argparse.Namespace(action="scope", number=n, expect=",".join(files), done="说明写好",
                                  what=what, original="用户的决定", original_file=None)
        out = io.StringIO()
        here = os.getcwd()
        os.chdir(self.repo)         # the overlap check reads module branches from the current repository
        try:
            with mock.patch.object(store, "open_store", return_value=self.db), contextlib.redirect_stdout(out):
                self.assertEqual(cli._task(args), 0)
        finally:
            os.chdir(here)
        return out.getvalue()

    def test_cli_shrink_unchanged(self):
        n, _ = self.escalate(expect=("docs/t.md", "src/a.py"))
        text = self.run_cli_scope(n, ["docs/t.md"])
        self.assertIn("已缩小，回到在做", text)
        self.assertNotIn("扩项", text)
        self.assertEqual(store.events(self.db, key=str(n), kind="task")[-1]["type"], "task.scoped")

    def test_cli_says_expand_and_overlap(self):
        holder = new_task(self.db, self.repo, expect=("src/cache.py",))
        n, _ = self.escalate()
        text = self.run_cli_scope(n, ["docs/t.md", "src/cache.py"], what="补说明并修缓存")
        self.assertIn("已扩项，回到在做", text)
        self.assertIn(f"重叠：T{holder}：src/cache.py", text)
        self.assertNotIn("缩小", text)

