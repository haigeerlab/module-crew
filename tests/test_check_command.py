"""T139 (S30): the full-check command runs without a shell, so shell operators are refused when it is written,
a check that cannot run is not a failure of the module, and a failing check shows the argv that was run."""
import unittest

from helpers import MergeCase, git

from module_crew import merge, protocol, store


class OperatorRefusedTest(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def test_operators_refused_on_write(self):
        for command in ("make lint && make test", "make lint || true", "make lint; make test", "make test | tee out",
                        "make test > out.log", "make test < in", "echo `date`", "echo $(date)", "make test;",
                        "make lint &&make test"):
            with self.subTest(command=command):
                cfg, reasons, pending = merge._check_config(self.db, command, replace=False)
                self.assertFalse(pending)
                self.assertEqual(len(reasons), 1, reasons)
                self.assertIn("shell 运算符", reasons[0])
                self.assertIn("项目脚本", reasons[0])
                self.assertIn("/bin/sh -c", reasons[0])
        self.approve_final("b", 1)
        res = merge.run(self.repo, check_command="python3 -c pass && python3 -c pass")
        self.assertEqual(res.code, 2, res.lines)
        self.assertNotIn("checkCommand", store.get(self.db, "config", "main") or {})

    def test_replace_check_also_refused(self):
        merge._write_config(self.db, {"checkCommand": "python3 -c pass"})
        _, reasons, pending = merge._check_config(self.db, "python3 -c pass; true", replace=True)
        self.assertFalse(pending)
        self.assertIn("shell 运算符", reasons[0])

    def test_quoted_sh_c_accepted(self):
        # LIVE-SAAS: five steps joined with && inside /bin/sh -c '…' must keep working
        command = "/bin/sh -c 'pnpm lint && pnpm typecheck && pnpm test && pnpm build && pnpm e2e'"
        cfg, reasons, pending = merge._check_config(self.db, command, replace=False)
        self.assertEqual(reasons, [])
        self.assertTrue(pending)
        self.assertEqual(cfg["checkCommand"], command)

    def test_stored_command_not_refused_retroactively(self):
        merge._write_config(self.db, {"checkCommand": "python3 -c pass && true"})
        self.assertEqual(merge._check_config(self.db, None, replace=False)[1], [])
        self.assertEqual(merge._check_config(self.db, "python3 -c pass && true", replace=False)[1], [])


class CannotRunTest(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def assert_kept_open(self, command):
        n = self.approve_final("b", 1)
        head = git(self.repo, "rev-parse", "HEAD")
        res = merge.run(self.repo, check_command=command)
        self.assertEqual(res.code, 4, res.lines)
        text = "\n".join(res.lines)
        self.assertIn("跑不起来", text)
        self.assertIn("合并批准仍开着", text)
        self.assertEqual(res.sends, [])                                    # nothing sent back to the module
        self.assertEqual(store.get(self.db, "item", str(n))["state"], "open")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)        # merge undone
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        return n

    def test_missing_program_not_returned(self):
        self.assert_kept_open("no-such-check-command-xyz")

    def test_exit_127_not_returned(self):
        self.assert_kept_open("/bin/sh -c 'no-such-check-command-xyz'")

    def test_exit_126_not_returned(self):
        script = self.tmp / "not-executable.sh"
        script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        script.chmod(0o644)
        self.assert_kept_open(f"/bin/sh -c '{script}'")


class FailedArgvTest(MergeCase):
    def test_returned_notice_shows_argv(self):
        db = store.open_store(self.repo)
        self.approve_final("b", 1)
        command = self.check_script(fail_if="src/b.py")
        res = merge.run(self.repo, check_command=command)
        self.assertEqual(res.code, 5, res.lines)
        [note] = [x for x in res.sends if x["to"] == "shop-b"]
        msg = protocol.parse(store.read_body(db, note["body"]))
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual(msg.contract()["notice"]["kind"], "returned")
        script = command.split(" ", 1)[1]
        self.assertIn(f'实际执行的参数：["python3", "{script}"]', msg.fields["依据"])


if __name__ == "__main__":
    unittest.main()
