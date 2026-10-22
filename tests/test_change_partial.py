"""0.10.2: `change land` must not close a request when some listed files are still untouched (spec-guard trial, C42)."""

import unittest

from helpers import ReviewCase, git

from module_crew import changes, store
from test_changes import request


class PartialLandTest(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        self.n = changes.add(self.db, request(["a.json", "b.json"], stopped="是"), "shop-b", 4700).number

    def test_refused_when_listed_files_untouched(self):
        before = git(self.repo, "rev-parse", "HEAD")
        (self.repo / "a.json").write_text("{}\n")
        res = changes.land(self.repo, self.n)
        self.assertEqual(res.code, 3, res.lines)
        self.assertIn("b.json", "\n".join(res.lines))
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)
        self.assertEqual(store.get(self.db, "request", str(self.n))["state"], "open")

    def test_partial_with_users_words_keeps_request_open(self):
        (self.repo / "a.json").write_text("{}\n")
        self.assertEqual(changes.land(self.repo, self.n, partial=True).code, 3)       # no words: refused
        res = changes.land(self.repo, self.n, "先落地 a.json", partial=True)
        self.assertEqual(res.code, 0, res.lines)
        rec = store.get(self.db, "request", str(self.n))
        self.assertEqual(rec["state"], "open")
        self.assertEqual(rec["partial"][-1]["files"], ["a.json"])
        self.assertIn("还剩 b.json", "\n".join(res.lines))
        (self.repo / "b.json").write_text("{}\n")
        done = changes.land(self.repo, self.n)
        self.assertEqual(done.code, 0, done.lines)
        self.assertEqual(store.get(self.db, "request", str(self.n))["state"], "closed")

    def test_cli_partial_flag(self):
        (self.repo / "a.json").write_text("{}\n")
        out = self.run_cli("change", "land", str(self.n))
        self.assertEqual(out.returncode, 3)
        ok = self.run_cli("change", "land", str(self.n), "--partial", "--original", "先落地 a.json")
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)


if __name__ == "__main__":
    unittest.main()
