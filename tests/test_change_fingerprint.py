"""T402 (S54): a 「文件」 line of 【公共变更请求】 ending in a fingerprint lists the path, not the whole string."""

import json
import unittest

from helpers import ReviewCase
from test_changes import request

from module_crew import protocol, store

HASH12 = "0123456789ab"
HASH64 = "0123456789abcdef" * 4


def parsed(*lines):
    return protocol.parse(request(list(lines)))


class StripTest(unittest.TestCase):
    def test_fingerprint_is_stripped_from_path(self):
        msg = parsed(f"- scripts/a.sh sha256:{HASH12}", f"- package.json sha256:{HASH64}", "- pnpm-lock.yaml")
        self.assertEqual(msg.problems, ())
        self.assertEqual(msg.contract()["changeRequest"]["files"], ["scripts/a.sh", "package.json", "pnpm-lock.yaml"])
        self.assertEqual(msg.hints, ("file-fingerprint-stripped",))

    def test_hint_also_on_bad_message(self):
        msg = parsed("- package.json", f"说明：见 a.ts sha256:{HASH12}")
        self.assertEqual(msg.problems, ("bad-file-line",))
        self.assertEqual(msg.contract()["changeRequest"]["files"], ["package.json", "说明：见 a.ts"])
        self.assertEqual(msg.hints, ("file-fingerprint-stripped",))

    def test_not_stripped(self):
        for line in (f"scripts/a.sh sha256:{HASH12.upper()}", "scripts/b.sh sha256:0123abc",
                     f"scripts/c.sh  sha256:{HASH12}", f"scripts/d.sh sha256:{HASH64}0"):
            with self.subTest(line):
                msg = parsed("- " + line)
                self.assertEqual(msg.contract()["changeRequest"]["files"], [line])
                self.assertEqual(msg.hints, ())


class ChangeAddTest(ReviewCase):
    def test_files_recorded_without_fingerprint(self):
        f = self.tmp / "r.txt"
        f.write_text(request([f"- scripts/a.sh sha256:{HASH12}"]), encoding="utf-8")
        r = self.run_cli("change", "add", str(f), "--from", "shop-b", "--relay-id", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("file-fingerprint-stripped", r.stdout)
        self.assertIn("转告发件人：公共变更请求的文件行只写路径", r.stdout)
        n = json.loads(self.run_cli("change", "list", "--json").stdout)[0]["number"]
        self.assertEqual(store.get(store.open_store(self.repo), "request", str(n))["files"], ["scripts/a.sh"])

    def test_no_reminder_without_fingerprint(self):
        f = self.tmp / "r.txt"
        f.write_text(request(["- scripts/a.sh"]), encoding="utf-8")
        r = self.run_cli("change", "add", str(f), "--from", "shop-b", "--relay-id", "1")
        self.assertNotIn("转告发件人", r.stdout)


if __name__ == "__main__":
    unittest.main()
