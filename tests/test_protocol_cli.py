import unittest

from helpers import RepoCase

from test_protocol_conformance import FIXTURES


class ProtocolCheckTest(RepoCase):
    def check(self, path):
        return self.run_cli("protocol", "check", str(path))

    def test_valid_message_exit_0(self):
        r = self.check(FIXTURES / "review-request" / "final.txt")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("review-request", r.stdout)
        self.assertIn("合格", r.stdout)

    def test_invalid_message_exit_3_lists_codes(self):
        r = self.check(FIXTURES / "review-request" / "bad-file-line.txt")
        self.assertEqual(r.returncode, 3)
        self.assertIn("bad-file-line", r.stdout)

    def test_hints_are_printed_but_do_not_fail(self):
        r = self.check(FIXTURES / "wait-user" / "brief-thin.txt")
        self.assertEqual(r.returncode, 0)
        self.assertIn("brief-thin", r.stdout)

    def test_unknown_exit_3(self):
        bad = self.tmp / "x.txt"
        bad.write_text("【催办】\n快点\n", encoding="utf-8")
        r = self.check(bad)
        self.assertEqual(r.returncode, 3)
        self.assertIn("unknown-kind", r.stdout)

    def test_unsupported_kind_exit_3(self):
        r = self.check(FIXTURES / "answer-notice" / "basic.txt")
        self.assertEqual(r.returncode, 3)
        self.assertIn("第一版不处理", r.stdout)

    def test_missing_file_exit_2(self):
        r = self.check(self.tmp / "nope.txt")
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
