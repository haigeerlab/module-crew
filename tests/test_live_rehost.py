"""crew-live-rehost: move an unfinished batch from Codex to Claude Code in one step (see the Spec)."""

import json
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from helpers import RepoCase, ReviewCase, git, review_text

from module_crew import hooks, mergelock, permissions, rehost as rh, review, store
from test_permissions import PermCase


def rehost(**extra):
    return {"from": "codex-desktop", "at": store.now(), "original": "迁到 Claude，旧会话已停，确认码 ABC234", "batch": 7, **extra}


def dev_rehost(**extra):
    return rehost(**{"snapshot": {"head": "a" * 40, "dirty": [" M a.py", "?? b.txt"]}, "inventory": "pending", **extra})


class StoreRehostTest(RepoCase):
    """Task 1: the store accepts the rehost record and previousSessions reasons, and rejects bad ones."""

    def setUp(self):
        super().setUp()
        self.db, _ = store.init_store(self.repo)
        self.wt = str(self.repo.parent / "wt-a")

    def put(self, key, rec):
        with self.db.transaction(actor="t") as tx:
            tx.put("session", key, rec, action="registered")

    def dev(self, **extra):
        return {"role": "dev", "host": "claude-desktop", "status": "active", "module": "a", "worktree": self.wt, **extra}

    def coord(self, **extra):
        return {"role": "coordinator", "host": "claude-desktop", "status": "active", **extra}

    def test_dev_with_rehost_accepted(self):
        self.put("shop-a", self.dev(rehost=dev_rehost()))
        self.assertEqual(store.get(self.db, "session", "shop-a")["rehost"]["inventory"], "pending")

    def test_coordinator_rehost_without_snapshot_accepted(self):
        self.put("shop-coord", self.coord(rehost=rehost()))
        self.assertEqual(store.get(self.db, "session", "shop-coord")["rehost"]["batch"], 7)

    def test_previous_session_reason_accepted(self):
        prev = [{"sessionId": "old-codex", "at": store.now(), "reason": "rehost"}]
        self.put("shop-a", self.dev(previousSessions=prev))
        self.assertEqual(store.get(self.db, "session", "shop-a")["previousSessions"][0]["reason"], "rehost")

    def test_bad_rehost_records(self):
        cases = {
            "not a dict": ("dev", "codex"),
            "from claude": ("dev", dev_rehost(**{"from": "claude-desktop"})),
            "empty original": ("dev", dev_rehost(original=" ")),
            "batch zero": ("dev", dev_rehost(batch=0)),
            "at missing": ("dev", {k: v for k, v in dev_rehost().items() if k != "at"}),
            "dev without snapshot": ("dev", rehost(inventory="pending")),
            "dirty not list": ("dev", dev_rehost(snapshot={"head": "x", "dirty": "M a"})),
            "bad inventory": ("dev", dev_rehost(inventory="done")),
            "coordinator with inventory": ("coordinator", rehost(inventory="pending")),
        }
        for name, (role, rec) in cases.items():
            with self.subTest(name):
                with self.assertRaises(store.InvalidSession):
                    self.put("x", self.dev(rehost=rec) if role == "dev" else self.coord(rehost=rec))

    def test_bad_previous_reason(self):
        with self.assertRaises(store.InvalidSession):
            self.put("shop-a", self.dev(previousSessions=[{"sessionId": "s", "at": store.now(), "reason": ""}]))


def as_caller(claude=None, codex=None):
    """Patch the environment so the code sees a Claude session, a Codex thread, or a terminal."""
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")}
    if claude:
        env["CLAUDE_CODE_SESSION_ID"] = claude
    if codex:
        env["CODEX_THREAD_ID"] = codex
    return mock.patch.dict(os.environ, env, clear=True)


def to_codex(db):
    """The crew as LIVE-SAAS has it: coordinator and module sessions all on Codex, each bound to a Codex thread."""
    sessions = store.records(db, "session")
    with db.transaction(actor="t") as tx:
        for name, rec in sessions.items():
            if rec.get("status") != "active":
                continue
            new = {**rec, "host": "codex-desktop", "hostSession": {"sessionId": f"codex-{name}", "boundAt": store.now()}}
            if rec.get("role") == "coordinator":
                new["hostHandover"] = {"from": "claude-desktop", "to": "codex-desktop", "at": store.now(),
                                       "original": "换到 Codex", "pending": False}
            tx.put("session", name, new, action="registered")


class RehostCase(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        to_codex(self.db)

    def check(self, sid=None, cwd=None, **who):
        with as_caller(**who):
            return rh.check(self.repo, cwd or self.repo, sid)


class CheckTest(RehostCase):
    """Task 2 (acceptance 1, 2): the blocking list and the confirmation code."""

    def ids(self, doc):
        return {c["id"]: c["ok"] for c in doc["checks"]}

    def test_ready_gives_code_and_sessions(self):
        (self.wt["b"] / "new.txt").write_text("x", encoding="utf-8")
        code, doc, lines = self.check(claude="sid-new")
        self.assertEqual(code, 0, lines)
        self.assertRegex(doc["code"], r"^[A-Z2-9]{6}$")
        self.assertIn(f"确认码：{doc['code']}", lines)
        row = next(r for r in doc["sessions"] if r["module"] == "b")
        self.assertEqual(row["dirty"], ["?? new.txt"])
        self.assertTrue(row["head"])
        self.assertIn("?? new.txt", "\n".join(lines))
        json.dumps(doc)

    def test_terminal_also_ready(self):
        self.assertEqual(self.check()[0], 0)

    def test_each_blocker(self):
        def coord_claude():
            rec = store.get(self.db, "session", "shop-coord")
            with self.db.transaction(actor="t") as tx:
                tx.put("session", "shop-coord", {k: v for k, v in rec.items() if k != "hostHandover"} | {"host": "claude-desktop"},
                       action="registered")

        def dev_claude():
            rec = store.get(self.db, "session", "shop-b")
            with self.db.transaction(actor="t") as tx:
                tx.put("session", "shop-b", {**rec, "host": "claude-desktop"}, action="registered")

        def offload_running():
            with self.db.transaction(actor="t") as tx:
                tx.put("offload", "b", {"module": "b", "state": "running"}, action="assigned")

        cases = {
            "coordinator-host": (coord_claude, {}),
            "all-codex": (dev_claude, {}),
            "offload": (offload_running, {}),
            "caller": (None, {"codex": "codex-x"}),
            "cwd": (None, {"cwd": self.wt["b"]}),
        }
        for cid, (setup, kw) in cases.items():
            with self.subTest(cid):
                db_before = store.records(self.db, "session")
                if setup:
                    setup()
                cwd = kw.pop("cwd", None)
                code, doc, lines = self.check(cwd=cwd, **kw)
                self.assertEqual(code, 3, lines)
                self.assertIsNone(doc["code"])
                self.assertFalse(self.ids(doc)[cid], doc["checks"])
                with self.db.transaction(actor="t") as tx:     # undo the setup for the next case
                    for n, r in db_before.items():
                        tx.put("session", n, r, action="registered")
                    if cid == "offload":
                        tx.put("offload", "b", {"module": "b", "state": "idle"}, action="assigned")

    def test_bound_caller_refused(self):
        code, doc, _ = self.check(sid="codex-shop-b", claude="codex-shop-b")
        self.assertEqual(code, 3)
        self.assertFalse(self.ids(doc)["caller"])

    def test_merge_lock_blocks(self):
        with mock.patch.object(mergelock, "read", return_value={"running": True, "approval": 9}):
            code, doc, lines = self.check(claude="sid-new")
        self.assertEqual(code, 3)
        self.assertIn("C9", "\n".join(lines))

    def test_spec_guard_missing_blocks(self):
        self.plugins.entries.pop("spec-guard@m")
        self.plugins.write()
        code, doc, _ = self.check(claude="sid-new")
        self.assertEqual(code, 3)
        self.assertFalse(self.ids(doc)["spec-guard"])

    def test_code_stable_then_changes(self):
        first = self.check(claude="sid-new")[1]["code"]
        self.assertEqual(self.check(claude="sid-new")[1]["code"], first)
        (self.wt["c"] / "x.py").write_text("1", encoding="utf-8")
        second = self.check(claude="sid-new")[1]["code"]
        self.assertNotEqual(second, first)
        git(self.wt["c"], "add", "-A")
        git(self.wt["c"], "commit", "-q", "-m", "x")
        third = self.check(claude="sid-new")[1]["code"]
        self.assertNotIn(third, (first, second))
        rec = store.get(self.db, "session", "shop-c")
        with self.db.transaction(actor="t") as tx:
            tx.put("session", "shop-c", {**rec, "hostSession": {"sessionId": "codex-other", "boundAt": store.now()}},
                   action="registered")
        self.assertNotIn(self.check(claude="sid-new")[1]["code"], (first, second, third))

    def test_check_cli_is_read_only_for_any_session(self):
        before = (store.records(self.db, "session"), len(store.events(self.db)))
        env = {k: v for k, v in os.environ.items() if k != "CODEX_THREAD_ID"}
        out = self.run_cli("coordinator", "rehost", "--check", "--json", env={**env, "CLAUDE_CODE_SESSION_ID": "sid-new"})
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(json.loads(out.stdout)["ready"])
        self.assertEqual((store.records(self.db, "session"), len(store.events(self.db))), before)


class ToClaudeCase(RehostCase):
    def code(self, **who):
        return self.check(**who)[1]["code"]

    def words(self, code):
        return f"把这批迁到 Claude，Codex 里 7 个旧会话我已停下并归档，确认码 {code}"

    def go(self, original=None, code=None, sid="sid-new", cwd=None, **who):
        who = who or ({"claude": sid} if sid else {})
        code = code or self.code(**who)
        with as_caller(**who):
            return rh.rehost(self.repo, original if original is not None else self.words(code), code, sid, cwd or self.repo)

    def snap(self):
        return (store.records(self.db, "session"), store.records(self.db, "item"), store.records(self.db, "ticket"),
                store.records(self.db, "request"), store.records(self.db, "task"), len(store.events(self.db)))


class ToClaudeTest(ToClaudeCase):
    """Task 3 (acceptance 2, 3, 4): checks, the narrow guard, and the one transaction."""

    def test_refusals_write_nothing(self):
        good = self.code(claude="sid-new")
        cases = {
            "wrong code": dict(code="ZZZZZZ", original=self.words("ZZZZZZ")),
            "no code in words": dict(code=good, original="迁到 Claude，旧会话已停"),
            "not stopped": dict(code=good, original=f"迁到 Claude，确认码 {good}"),
            "empty": dict(code=good, original=" "),
        }
        for name, kw in cases.items():
            with self.subTest(name):
                before = self.snap()
                code, lines = self.go(**kw)
                self.assertEqual(code, 3, lines)
                self.assertEqual(self.snap(), before)

    def test_code_stale_after_change(self):
        good = self.code(claude="sid-new")
        (self.wt["b"] / "late.txt").write_text("x", encoding="utf-8")
        before = self.snap()
        code, lines = self.go(code=good, original=self.words(good))
        self.assertEqual(code, 3, lines)
        self.assertIn("重新 --check", "\n".join(lines))
        self.assertEqual(self.snap(), before)

    def test_guard_exit_7(self):
        cases = {"codex thread": dict(sid="codex-x", codex="codex-x"),
                 "bound caller": dict(sid="codex-shop-b", claude="codex-shop-b"),
                 "outside integration": dict(sid="sid-new", claude="sid-new", cwd=self.wt["b"])}
        for name, kw in cases.items():
            with self.subTest(name):
                before = self.snap()
                sid, cwd = kw.pop("sid"), kw.pop("cwd", None)
                code, lines = self.go(code="ABCDEF", original=self.words("ABCDEF"), sid=sid, cwd=cwd, **kw)
                self.assertEqual(code, 7, lines)
                self.assertEqual(self.snap(), before)

    def test_moves_everyone(self):
        with self.db.transaction(actor="t") as tx:
            tx.put("item", str(tx.allocate_number()), {"kind": "review", "module": "b", "node": "spec", "state": "open"}, action="t")
            tx.put("request", str(tx.allocate_number()), {"from": "shop-c", "files": ["x.ts"], "state": "open"}, action="t")
            tx.put("ticket", str(tx.allocate_number()), {"from": "shop-b", "state": "open"}, action="t")
        (self.wt["b"] / "wip.py").write_text("x", encoding="utf-8")
        items_before = self.snap()[1:5]
        code, lines = self.go()
        self.assertEqual(code, 0, lines)
        sessions = store.records(self.db, "session")
        moved = {n: r for n, r in sessions.items() if r.get("status") == "active"}
        self.assertEqual({r["host"] for r in moved.values()}, {"claude-desktop"})
        coord = moved["shop-coord"]
        self.assertEqual(coord["hostSession"]["sessionId"], "sid-new")
        self.assertEqual(coord["hostHandover"]["from"], "codex-desktop")
        self.assertFalse(coord["hostHandover"]["pending"])
        self.assertNotIn("snapshot", coord["rehost"])
        for name in ("shop-b", "shop-c"):
            rec = moved[name]
            self.assertNotIn("hostSession", rec)
            self.assertEqual(rec["previousSessions"][-1], {**rec["previousSessions"][-1], "sessionId": f"codex-{name}", "reason": "rehost"})
            self.assertEqual(rec["rehost"]["inventory"], "pending")
        self.assertIn("?? wip.py", moved["shop-b"]["rehost"]["snapshot"]["dirty"])
        self.assertEqual(self.snap()[1:5], items_before)
        ev = [e for e in store.events(self.db) if e["type"] == "session.rehosted"]
        self.assertEqual(len(ev), 3)
        self.assertTrue(all("确认码" in e["data"]["original"] for e in ev))

    def test_terminal_leaves_coordinator_unbound(self):
        code, lines = self.go(sid=None)
        self.assertEqual(code, 0, lines)
        self.assertNotIn("hostSession", store.get(self.db, "session", "shop-coord"))

    def test_cli_passes_guard_for_unbound_claude(self):
        env = {k: v for k, v in os.environ.items() if k != "CODEX_THREAD_ID"}
        env["CLAUDE_CODE_SESSION_ID"] = "sid-cli"
        out = self.run_cli("coordinator", "rehost", "--check", "--json", env=env)
        code = json.loads(out.stdout)["code"]
        out = self.run_cli("coordinator", "rehost", "--to", "claude", "--code", code, "--original", self.words(code), env=env)
        self.assertEqual(out.returncode, 0, out.stderr + out.stdout)
        self.assertEqual(store.get(self.db, "session", "shop-coord")["hostSession"]["sessionId"], "sid-cli")


class AfterTest(ToClaudeCase):
    """Task 4 (acceptance 5 not-applied, 6): recovery kits and the guide."""

    def test_kits_and_guide(self):
        (self.wt["b"] / "wip.py").write_text("x", encoding="utf-8")
        code, lines = self.go()
        self.assertEqual(code, 0, lines)
        text = "\n".join(lines)
        self.assertIn("没有 permissions apply 过", text)
        guides = sorted(p for p in (self.db.path / "rehost-guide").glob("*.md"))
        self.assertEqual(len(guides), 1)
        guide = guides[0].read_text(encoding="utf-8")
        for phrase in ("去哪个会话", "做什么", "做完的样子", "shop-b", "shop-c", "归档", "rehost release", "--undo"):
            self.assertIn(phrase, guide)
        bodies = [int(n) for n in re.findall(r"正文 #(\d+)", guide)]
        self.assertEqual(len(bodies), 2)
        kit_b = next(store.read_body(self.db, n) for n in bodies if "shop-b" in store.read_body(self.db, n).splitlines()[0])
        for phrase in ('takeover:true, wake:"auto"', "module-crew bind shop-b", "rehost show shop-b", "?? wip.py",
                       "中途检查点", "不写代码", "rehost-shop-b"):
            self.assertIn(phrase, kit_b)
        self.assertNotIn("Codex 桌面版里", kit_b)
        self.assertNotIn("模块协调运行 `module-crew takeover", kit_b)
        original = re.search(r"原话文件 (\S+?)）", kit_b).group(1)
        self.assertIn("确认码", Path(original).read_text(encoding="utf-8"))


class RehostPermissionsTest(PermCase):
    """Task 4 (acceptance 5): Claude rules for every checkout, Codex rules left as they were."""

    def test_rules_follow(self):
        permissions.apply(self.repo, "按清单预配权限")
        to_codex(self.db)
        codex_rules = self.wt["c"] / ".codex" / "rules" / "module-crew.rules"
        before = codex_rules.read_text(encoding="utf-8")
        with as_caller(claude="sid-new"):
            code = rh.check(self.repo, self.repo, "sid-new")[1]["code"]
            res, lines = rh.rehost(self.repo, f"迁到 Claude，旧会话已停，确认码 {code}", code, "sid-new", self.repo)
        self.assertEqual(res, 0, lines)
        self.assertEqual(codex_rules.read_text(encoding="utf-8"), before)
        self.assertIn("Bash(git push *)", self.settings(self.wt["c"])["permissions"]["deny"])
        self.assertTrue(any(str(self.wt["c"]) in l and "已写权限规则" in l for l in lines), lines)


class OldSessionTest(ToClaudeCase):
    """Task 5 (acceptance 7): a moved-away Codex thread may still read but no longer write."""

    def setUp(self):
        super().setUp()
        self.assertEqual(self.go()[0], 0)

    def cli(self, *args, thread="codex-shop-b"):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}
        return self.run_cli(*args, cwd=self.wt["b"], env={**env, "CODEX_THREAD_ID": thread})

    def test_module_writes_refused(self):
        for args in (("sync",), ("check", "quick"), ("offload", "start", "b"), ("bind", "shop-b")):
            with self.subTest(args):
                out = self.cli(*args)
                self.assertEqual(out.returncode, 7, out.stdout + out.stderr)
                self.assertIn("已被迁到 Claude", out.stderr)

    def test_reads_still_work(self):
        self.assertEqual(self.cli("status").returncode, 0)
        self.assertEqual(self.cli("sessions").returncode, 0)

    def test_other_threads_unaffected(self):
        out = self.cli("bind", "shop-b", thread="claude-new")
        self.assertNotEqual(out.returncode, 7, out.stderr)


class InventoryTest(ToClaudeCase):
    """Task 6 (acceptance 8): the inventory gate."""

    def setUp(self):
        super().setUp()
        (self.wt["b"] / "wip.py").write_text("x", encoding="utf-8")
        self.assertEqual(self.go()[0], 0)

    def final(self, m="b", value=1):
        f = self.wt[m] / "src" / f"{m}.py"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"V = {value}\n", encoding="utf-8")
        git(self.wt[m], "add", "src")
        git(self.wt[m], "commit", "-q", "-m", "code")
        head = review_text(m, "最终验收", [(f"src/{m}.py", f)])
        head = head.replace("要点：\n", "要点：\n验收结果：\n1：通过\n\n", 1)
        return head + "改动统计：1 file changed\n越界检查：无越界\n"

    def test_hook_stage(self):
        text = hooks.session_start(self.wt["b"], "startup") or ""
        self.assertIn("迁来待盘点", text)
        with as_caller():
            line = hooks.prompt_line(self.wt["b"]) or ""
        self.assertIn("迁来待盘点", line)

    def test_show_reports_changes_since_snapshot(self):
        (self.wt["b"] / "late.txt").write_text("y", encoding="utf-8")
        git(self.wt["b"], "add", "late.txt")
        git(self.wt["b"], "commit", "-q", "-m", "late")
        code, lines = rh.show(self.db, "shop-b")
        text = "\n".join(lines)
        self.assertEqual(code, 0, text)
        self.assertIn("快照之后多了 1 个提交", text)
        self.assertIn("spec/b.md", text)
        self.assertIn("todo", text)
        self.assertIn("对不上", text)

    def test_show_unchanged(self):
        code, lines = rh.show(self.db, "shop-c")
        self.assertEqual(code, 0)
        self.assertIn("与迁移时的快照一致", "\n".join(lines))

    def test_final_refused_until_released(self):
        out = review.add(self.db, self.final(), "shop-b", 9001)
        self.assertEqual(out.code, 3, out.lines)
        self.assertIn("rehost release", "\n".join(out.lines))
        self.assertEqual(review.add(self.db, review_text("b", "Spec", [("spec/b.md", self.wt["b"] / "spec" / "b.md")]),
                                    "shop-b", 9002).code, 0)
        code, lines = rh.release(self.db, "shop-b", "盘点看过了，继续做")
        self.assertEqual(code, 0, lines)
        self.assertEqual(store.get(self.db, "session", "shop-b")["rehost"]["inventory"], "released")
        self.assertNotIn("迁来待盘点", hooks.session_start(self.wt["b"], "startup") or "")
        self.assertEqual(review.add(self.db, self.final(value=2), "shop-b", 9003).code, 0)

    def test_release_refusals(self):
        self.assertEqual(rh.release(self.db, "shop-b", " ")[0], 3)
        self.assertEqual(rh.release(self.db, "shop-coord", "x")[0], 3)
        self.assertEqual(rh.release(self.db, "shop-b", "好")[0], 0)
        self.assertEqual(rh.release(self.db, "shop-b", "好")[0], 3)

    def test_status_lists_pending(self):
        out = self.run_cli("status", "--json")
        self.assertEqual(json.loads(out.stdout)["store"]["rehostPending"], ["shop-b", "shop-c"])
        self.assertIn("迁来待盘点", self.run_cli("status").stdout)


if __name__ == "__main__":
    unittest.main()
