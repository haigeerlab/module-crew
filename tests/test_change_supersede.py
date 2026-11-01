"""S27 (T133): the 「文件」 field of a 【公共变更请求】 is checked, and a module's newer request supersedes its older one."""

import unittest

from helpers import ReviewCase

from module_crew import changes, protocol, store


def request(files, what="改配置", why="模块需要", stopped="否"):
    lines = "\n".join(files)
    return (f"【公共变更请求】\n结束：无\n来自：b\n文件：\n{lines}\n改什么：{what}\n为什么：{why}\n"
            f"是否完全停住：{stopped}\n")


class FileLineTest(unittest.TestCase):
    def test_non_path_lines_rejected(self):
        for line in ("把 eslint 规则放宽一点", "- package.json：加 better-sqlite3", "两个 文件 都要改",
                     "- 说明：这是因为测试要跑"):
            with self.subTest(line):
                self.assertIn("bad-file-line", protocol.parse(request(["package.json", line])).problems)

    def test_path_like_lines_pass(self):
        for line in ("package.json", "- .github/workflows/ci.yml", "src/", "packages/*/tsconfig.json",
                     "docs/My Notes.md", "requirements-dev.txt", ".gitignore", "Makefile"):
            with self.subTest(line):
                self.assertNotIn("bad-file-line", protocol.parse(request([line])).problems)


class SupersedeTest(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def test_bad_file_line_refused_by_change_add(self):
        out = changes.add(self.db, request(["package.json", "顺便把 lint 也放宽"]), "shop-b", 1)
        self.assertEqual(out.code, 3)
        self.assertIn("bad-file-line", " ".join(out.lines))
        self.assertEqual(store.records(self.db, "request"), {})

    def test_newer_overlapping_request_supersedes_older(self):
        old = changes.add(self.db, request(["package.json", "a.txt"], stopped="是"), "shop-b", 10).number
        ticket = store.get(self.db, "request", str(old))["ticket"]
        out = changes.add(self.db, request(["package.json", "a.txt", "b.txt"]), "shop-b", 11)
        self.assertEqual(out.code, 0, out.lines)
        rec = store.get(self.db, "request", str(old))
        self.assertEqual((rec["state"], rec["closedReason"], rec["supersededBy"]), ("closed", "superseded", out.number))
        self.assertEqual(store.get(self.db, "ticket", str(ticket))["state"], "closed")
        self.assertIn(old, out.closed)
        self.assertIn(f"C{old}", " ".join(out.lines))
        new = store.get(self.db, "request", str(out.number))
        self.assertNotIn(f"conflict:{old}", new["hints"])
        self.assertEqual([n for n, _ in changes.pending(self.db)], [out.number])

    def test_partial_overlap_not_superseded(self):
        """S59 (T447): sharing one file with an older request of three is not a replacement."""
        old = changes.add(self.db, request(["package.json", "a.txt", "b.txt"], stopped="是"), "shop-b", 40).number
        ticket = store.get(self.db, "request", str(old))["ticket"]
        out = changes.add(self.db, request(["a.txt", "c.txt"]), "shop-b", 41)
        self.assertEqual(out.code, 0, out.lines)
        self.assertEqual(out.closed, [])
        rec = store.get(self.db, "request", str(old))
        self.assertEqual(rec["state"], "open")
        self.assertEqual(store.get(self.db, "ticket", str(ticket))["state"], "open")
        self.assertIn(f"conflict:{out.number}", rec["hints"])
        self.assertIn(f"conflict:{old}", store.get(self.db, "request", str(out.number))["hints"])
        self.assertIn(f"与 C{old} 部分重叠，没有取代", " ".join(out.lines))
        self.assertEqual([n for n, _ in changes.pending(self.db)], [old, out.number])

    def test_covering_by_directory_or_glob_supersedes(self):
        old = changes.add(self.db, request(["src/a.ts", "packages/x/tsconfig.json"]), "shop-b", 50).number
        out = changes.add(self.db, request(["src/", "packages/*/tsconfig.json"]), "shop-b", 51)
        self.assertEqual(out.code, 0, out.lines)
        self.assertEqual(out.closed, [old])
        self.assertEqual(store.get(self.db, "request", str(old))["closedReason"], "superseded")

    def test_disjoint_or_other_module_kept(self):
        a = changes.add(self.db, request(["a.txt"]), "shop-b", 20).number
        b = changes.add(self.db, request(["b.txt"]), "shop-b", 21).number
        c = changes.add(self.db, request(["b.txt"]), "shop-c", 22).number
        self.assertEqual(store.get(self.db, "request", str(a))["state"], "open")
        self.assertEqual(store.get(self.db, "request", str(b))["state"], "open")
        self.assertIn(f"conflict:{c}", store.get(self.db, "request", str(b))["hints"])
        self.assertEqual([n for n, _ in changes.pending(self.db)], [a, b, c])

    def test_answer_reason_superseded(self):
        old = changes.add(self.db, request(["a.txt"], stopped="是"), "shop-b", 30).number
        new = changes.add(self.db, request(["b.txt"]), "shop-b", 31).number
        r = self.run_cli("change", "answer", f"C{old}", "--reason", "superseded", "--by", f"C{new}")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rec = store.get(self.db, "request", str(old))
        self.assertEqual((rec["state"], rec["closedReason"], rec["supersededBy"]), ("closed", "superseded", new))
        self.assertEqual(store.get(self.db, "ticket", str(rec["ticket"]))["state"], "closed")
        self.assertIsNone(rec["answer"])
        again = self.run_cli("change", "answer", f"C{old}", "--reason", "superseded")
        self.assertEqual(again.returncode, 3)
        plain = self.run_cli("change", "answer", f"C{new}")
        self.assertEqual(plain.returncode, 2, "declining still needs the user's words")


if __name__ == "__main__":
    unittest.main()
