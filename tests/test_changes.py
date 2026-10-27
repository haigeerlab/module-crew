import unittest

from helpers import ReviewCase, git

from module_crew import changes, protocol, store


def request(files, what="改配置", why="模块需要", stopped="否", end="无"):
    lines = "\n".join(files)
    return (f"【公共变更请求】\n结束：{end}\n来自：b\n文件：\n{lines}\n改什么：{what}\n为什么：{why}\n"
            f"是否完全停住：{stopped}\n")


def files(db):
    return {str(p): p.read_bytes() for p in db.path.rglob("*") if p.is_file() and p.name != ".lock"}


class AddTest(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def test_recorded_with_ticket_when_stopped(self):
        out = changes.add(self.db, request(["tsconfig.base.json"], stopped="是"), "shop-b", 4700)
        self.assertEqual(out.code, 0, out.lines)
        rec = store.get(self.db, "request", str(out.number))
        self.assertEqual((rec["state"], rec["files"], rec["fullyStopped"]), ("open", ["tsconfig.base.json"], True))
        ticket = store.get(self.db, "ticket", str(rec["ticket"]))
        self.assertEqual((ticket["from"], ticket["waitingFor"], ticket["state"]), ("shop-b", "shop-coord", "open"))

    def test_not_stopped_no_ticket(self):
        out = changes.add(self.db, request(["a.txt"]), "shop-b", 1)
        self.assertIsNone(store.get(self.db, "request", str(out.number))["ticket"])
        self.assertEqual(store.records(self.db, "ticket"), {})

    def test_rejections_and_repeat(self):
        before = files(self.db)
        for text, sender in ((request(["a"]), "shop-x"), (request(["a"]).replace("为什么：模块需要\n", ""), "shop-b")):
            with self.subTest(sender=sender):
                self.assertEqual(changes.add(self.db, text, sender, 5).code, 3)
        self.assertEqual(files(self.db), before)
        changes.add(self.db, request(["a"]), "shop-b", 6)
        before = files(self.db)
        again = changes.add(self.db, request(["a"]), "shop-b", 6)
        self.assertIn("已记过", " ".join(again.lines))
        self.assertEqual(files(self.db), before)

    def test_hints(self):
        cases = {"package.json": ["dependency"], ".github/workflows/ci.yml": ["ci"],
                 "db/Migrations/001.sql": ["migration"], "README.md": []}
        for path, hints in cases.items():
            with self.subTest(path):
                self.assertEqual(changes.hints_for([path], {}), hints)
        a = changes.add(self.db, request(["tsconfig.base.json"]), "shop-b", 10).number
        out = changes.add(self.db, request(["tsconfig.base.json", "x.txt"]), "shop-c", 11)
        self.assertIn(f"conflict:{a}", store.get(self.db, "request", str(out.number))["hints"])
        self.assertIn(f"conflict:{out.number}", store.get(self.db, "request", str(a))["hints"])
        self.assertIn("要问用户", " ".join(out.lines))

    def test_pending_in_order(self):
        self.assertEqual(changes.pending(self.db), [])
        a = changes.add(self.db, request(["a"]), "shop-b", 1).number
        b = changes.add(self.db, request(["b"]), "shop-c", 2).number
        self.assertEqual([n for n, _ in changes.pending(self.db)], [a, b])


class AnswerTest(ReviewCase):
    def test_declined(self):
        db = store.open_store(self.repo)
        n = changes.add(db, request(["package.json"], stopped="是"), "shop-b", 4700).number
        head = git(self.repo, "rev-parse", "HEAD")
        reply = changes.answer(db, n, "不加这个依赖")
        msg = protocol.parse(store.read_body(db, reply.body))
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual((reply.to, reply.reply_to), ("shop-b", 4700))
        rec = store.get(db, "request", str(n))
        self.assertEqual((rec["state"], rec["closedReason"]), ("closed", "declined"))
        ticket = store.get(db, "ticket", str(rec["ticket"]))
        self.assertEqual((ticket["state"], ticket["closedReason"]), ("closed", 3))
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)
        with self.assertRaises(changes.AnswerRefused):
            changes.answer(db, n, "再答")


if __name__ == "__main__":
    unittest.main()


class LandTest(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def snapshot(self):
        return (git(self.repo, "rev-parse", "HEAD"), files(self.db))

    def test_land(self):
        n = changes.add(self.db, request(["tsconfig.base.json"], stopped="是"), "shop-b", 4700).number
        with self.db.transaction(actor="t") as tx:   # a retired session must not be notified
            tx.put("session", "shop-z", {"role": "dev", "host": "claude-desktop", "status": "retired",
                                         "module": "z", "worktree": "/tmp/z"}, action="registered")
        before = git(self.repo, "rev-parse", "HEAD").strip()
        (self.repo / "tsconfig.base.json").write_text('{"strict": true}\n')
        res = changes.land(self.repo, n)
        self.assertEqual(res.code, 0, res.lines)
        log = git(self.repo, "log", "--format=%s", f"{before}..HEAD").strip().splitlines()
        self.assertEqual(len(log), 1)
        self.assertIn(f"C{n}", log[0])
        self.assertEqual(git(self.repo, "diff", "--name-only", before, "HEAD").split(), ["tsconfig.base.json"])
        rec = store.get(self.db, "request", str(n))
        self.assertEqual((rec["state"], rec["closedReason"], rec["commit"]), ("closed", "landed", res.commit))
        self.assertEqual(store.get(self.db, "ticket", str(rec["ticket"]))["closedReason"], 3)
        by_to = {x["to"]: x for x in res.sends}
        self.assertEqual(sorted(by_to), ["shop-b", "shop-c"])
        mine = protocol.parse(store.read_body(self.db, by_to["shop-b"]["body"]))
        self.assertTrue(mine.ok, mine.problems)
        self.assertEqual(mine.reply_to, 4700)
        self.assertEqual(mine.contract()["notice"]["kind"], "sync-baseline")
        self.assertIn(f"公共变更请求 C{n}", mine.fields["依据"])
        self.assertIn("`module-crew sync`", mine.fields["要你做什么"])
        self.assertNotIn("git merge", mine.fields["要你做什么"])
        other = protocol.parse(store.read_body(self.db, by_to["shop-c"]["body"]))
        self.assertTrue(other.ok)
        self.assertIsNone(other.reply_to)

    def test_refusals(self):
        n = changes.add(self.db, request(["tsconfig.base.json"]), "shop-b", 1).number
        before = self.snapshot()
        self.assertEqual(changes.land(self.repo, n).code, 3)          # nothing changed
        (self.repo / "tsconfig.base.json").write_text("{}\n")
        (self.repo / "other file.txt").write_text("x")              # outside the list, with a space
        res = changes.land(self.repo, n)
        self.assertEqual(res.code, 3)
        self.assertIn("other file.txt", " ".join(res.lines))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(changes.land(self.repo, 999).code, 3)

    def test_rename_inside_and_outside_list(self):
        (self.repo / "old.txt").write_text("x")
        git(self.repo, "add", "old.txt")
        git(self.repo, "commit", "-q", "-m", "old")
        n = changes.add(self.db, request(["old.txt"]), "shop-b", 2).number
        git(self.repo, "mv", "old.txt", "new.txt")
        self.assertEqual(changes.land(self.repo, n).code, 3)       # new.txt is not in the list
        m = changes.add(self.db, request(["old.txt", "new.txt"]), "shop-c", 3).number
        self.assertEqual(changes.land(self.repo, m).code, 0)

    def test_ask_user_hint_without_original_reminds(self):
        n = changes.add(self.db, request(["package.json"]), "shop-b", 4).number
        (self.repo / "package.json").write_text("{}\n")
        res = changes.land(self.repo, n)
        self.assertEqual(res.code, 0, res.lines)
        self.assertIn("没有记下用户原话", " ".join(res.lines))
        k = changes.add(self.db, request(["package.json"]), "shop-c", 5).number
        (self.repo / "package.json").write_text('{"a": 1}\n')
        changes.land(self.repo, k, original="可以加")
        self.assertEqual(store.get(self.db, "request", str(k))["answer"]["original"], "可以加")


class CliTest(ReviewCase):
    def test_add_list_land(self):
        f = self.tmp / "r.txt"
        f.write_text(request(["package.json"]), encoding="utf-8")
        self.assertEqual(self.run_cli("inbox", "add", str(f), "--from", "shop-b", "--relay-id", "1").returncode, 4)
        r = self.run_cli("change", "add", str(f), "--from", "shop-b", "--relay-id", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("要问用户", r.stdout)
        r = self.run_cli("change", "list")
        self.assertIn("package.json", r.stdout)
        n = __import__("json").loads(self.run_cli("change", "list", "--json").stdout)[0]["number"]
        (self.repo / "package.json").write_text("{}\n")
        r = self.run_cli("change", "land", str(n), "--original", "可以加")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.count("发送 【协调通知】"), 2)
        self.assertEqual(self.run_cli("change", "list").returncode, 3)


class BatchLandTest(ReviewCase):
    """0.17.0 (S43, Spec AC 10-13): several approved requests in one commit, checked first, all or nothing."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        self.a = changes.add(self.db, request(["upstream-policy.json"], stopped="是"), "shop-b", 96).number
        self.b = changes.add(self.db, request(["foundation-approval.sha256"]), "shop-c", 99).number
        self.head = git(self.repo, "rev-parse", "HEAD").strip()
        self.calls = self.tmp / "calls"

    def config(self, **kv):
        with self.db.transaction(actor="t") as tx:
            cfg = dict(tx.get("config", "main") or {})
            for k, v in kv.items():
                if v is None:
                    cfg.pop(k, None)
                else:
                    cfg[k] = v
            tx.put("config", "main", cfg, action="set")

    def script(self, fail_if=None):
        """A check command that counts its runs and fails while `fail_if` exists in the checkout."""
        path = self.tmp / "check.py"
        path.write_text("import os, sys\n"
                        f"open({str(self.calls)!r}, 'a').write('x')\n"
                        f"sys.exit(1 if {fail_if!r} and os.path.exists({fail_if!r}) else 0)\n", encoding="utf-8")
        return f"python3 {path}"

    def ran(self):
        return len(self.calls.read_text()) if self.calls.exists() else 0

    def edit(self, *names):
        for name in names or ("upstream-policy.json", "foundation-approval.sha256"):
            (self.repo / name).write_text("v2\n", encoding="utf-8")

    def snapshot(self):
        return (git(self.repo, "rev-parse", "HEAD"), git(self.repo, "diff", "--cached", "--name-only"), files(self.db))

    def test_one_commit_two_requests(self):
        self.config(checkCommand=self.script())
        self.edit()
        res = changes.land_batch(self.repo, [self.a, self.b])
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(self.ran(), 1)
        log = git(self.repo, "log", "--format=%s", f"{self.head}..HEAD").strip().splitlines()
        self.assertEqual(len(log), 1)
        self.assertIn(f"C{self.a}、C{self.b}", log[0])
        self.assertEqual(sorted(git(self.repo, "diff", "--name-only", self.head, "HEAD").split()),
                         ["foundation-approval.sha256", "upstream-policy.json"])
        for n in (self.a, self.b):
            rec = store.get(self.db, "request", str(n))
            self.assertEqual((rec["state"], rec["closedReason"], rec["commit"], rec["batch"]),
                             ("closed", "landed", res.commit, [self.a, self.b]))
        ticket = store.get(self.db, "request", str(self.a))["ticket"]
        self.assertEqual(store.get(self.db, "ticket", str(ticket))["closedReason"], 3)
        by_to = {x["to"]: x for x in res.sends}
        self.assertEqual(sorted(by_to), ["shop-b", "shop-c"])
        for name, relay in (("shop-b", 96), ("shop-c", 99)):
            msg = protocol.parse(store.read_body(self.db, by_to[name]["body"]))
            self.assertTrue(msg.ok, msg.problems)
            self.assertEqual((msg.reply_to, by_to[name]["replyTo"], by_to[name]["alsoAnswers"]), (relay, relay, []))
            self.assertIn(f"公共变更请求 C{self.a}、C{self.b}", msg.fields["依据"])
        self.assertEqual(store.records(self.db, "check"), {})          # ledger off: the full check is not recorded

    def test_same_requester_one_notice(self):
        c = changes.add(self.db, request(["tsconfig.base.json"]), "shop-b", 101).number
        self.config(checkCommand=self.script())
        self.edit("upstream-policy.json", "tsconfig.base.json")
        res = changes.land_batch(self.repo, [c, self.a])
        self.assertEqual(res.code, 0, res.lines)
        mine = [x for x in res.sends if x["to"] == "shop-b"]
        self.assertEqual(len(mine), 1)
        self.assertEqual((mine[0]["replyTo"], mine[0]["alsoAnswers"]), (96, [101]))
        other = next(x for x in res.sends if x["to"] == "shop-c")
        self.assertIsNone(other["replyTo"])
        self.assertIsNone(protocol.parse(store.read_body(self.db, other["body"])).reply_to)

    def test_refused_whole_batch(self):
        self.config(checkCommand=self.script())
        self.edit("upstream-policy.json")
        before = self.snapshot()
        cases = {"清单文件没改": [self.a, self.b], "不存在": [self.a, 999], "重复": [self.a, self.a]}
        for why, numbers in cases.items():
            with self.subTest(why):
                self.assertEqual(changes.land_batch(self.repo, numbers).code, 3)
                self.assertEqual(self.snapshot(), before)
        self.edit()
        (self.repo / "stray.txt").write_text("x")
        res = changes.land_batch(self.repo, [self.a, self.b])
        self.assertEqual(res.code, 3)
        self.assertIn("stray.txt", " ".join(res.lines))
        (self.repo / "stray.txt").unlink()
        for kw in ({"partial": True}, {"from_module": True}):
            with self.subTest(kw):
                self.assertEqual(changes.land_batch(self.repo, [self.a, self.b], "好", **kw).code, 3)
        changes.answer(self.db, self.b, "不改")
        self.assertEqual(changes.land_batch(self.repo, [self.a, self.b]).code, 3)    # closed
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), self.head)
        self.assertEqual(self.ran(), 0)

    def test_full_check_fails(self):
        self.config(checkCommand=self.script(fail_if=str(self.repo / "foundation-approval.sha256")))
        self.edit()
        res = changes.land_batch(self.repo, [self.a, self.b])
        self.assertEqual(res.code, 5, res.lines)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), self.head)
        self.assertEqual(sorted(git(self.repo, "diff", "--cached", "--name-only").split()),
                         ["foundation-approval.sha256", "upstream-policy.json"])
        self.assertEqual({store.get(self.db, "request", str(n))["state"] for n in (self.a, self.b)}, {"open"})
        self.assertEqual((res.sends, store.records(self.db, "check")), ([], {}))

    def test_quick_check_with_ledger(self):
        self.config(checkLedger="on", checkCommand=self.script(), quickCheckCommand=self.script())
        self.edit()
        res = changes.land_batch(self.repo, [self.a, self.b])
        self.assertEqual(res.code, 0, res.lines)
        tree = git(self.repo, "rev-parse", "HEAD^{tree}").strip()
        self.assertEqual(store.get(self.db, "check", f"{tree}.quick")["by"], "change-land")
        self.assertEqual(self.ran(), 1)

    def test_quick_check_fails_with_ledger(self):
        failing = self.script(fail_if=str(self.repo / "upstream-policy.json"))
        self.config(checkLedger="on", checkCommand=failing, quickCheckCommand=failing)
        self.edit()
        res = changes.land_batch(self.repo, [self.a, self.b])
        self.assertEqual(res.code, 5, res.lines)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), self.head)

    def test_no_check_command(self):
        self.config(checkCommand=None, checkLedger=None)
        self.edit()
        before = self.snapshot()
        self.assertEqual(changes.land_batch(self.repo, [self.a, self.b]).code, 3)
        self.assertEqual(changes.land_batch(self.repo, [self.a, self.b], skip_check=True).code, 3)
        self.assertEqual(self.snapshot(), before)
        res = changes.land_batch(self.repo, [self.a, self.b], "这批先不检查", skip_check=True)
        self.assertEqual(res.code, 0, res.lines)
        for n in (self.a, self.b):
            rec = store.get(self.db, "request", str(n))
            self.assertEqual(rec["checkSkipped"]["original"], "这批先不检查")
            self.assertEqual(rec["answer"]["original"], "这批先不检查")
