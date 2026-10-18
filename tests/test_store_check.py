import json
import unittest

from helpers import RepoCase

from module_crew import store


class CheckTest(RepoCase):
    def setUp(self):
        super().setUp()
        self.db, _ = store.init_store(self.repo)
        with self.db.transaction(actor="coord") as tx:
            tx.put("item", "1", {"n": 1}, action="created")
            tx.write_body(2, "正文")

    def check(self):
        result = self.run_cli("store", "check")
        return result.returncode, result.stdout

    def test_clean(self):
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("✅ 一致", out)
        self.assertIn("下一个编号：C3", out)
        self.assertIn(str(self.db.path), out)

    def test_lag_is_warning_only(self):
        event = {"v": 1, "seq": 3, "at": "2026-10-18T10:00:00+08:00", "type": "item.created",
                 "key": "3", "actor": "a", "data": {"record": {}}}
        with open(self.db.path / "events.jsonl", "a") as f:
            f.write(json.dumps(event) + "\n")
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("快照落后于日志 1 条：item", out)

    def test_half_line_exit_3(self):
        with open(self.db.path / "events.jsonl", "a") as f:
            f.write('{"v": 1')
        before = (self.db.path / "events.jsonl").read_bytes()
        code, out = self.check()
        self.assertEqual(code, 3, out)
        self.assertIn("末尾半行", out)
        self.assertEqual((self.db.path / "events.jsonl").read_bytes(), before)

    def test_corrupt_snapshot_exit_3_names_file(self):
        (self.db.path / "state" / "item.json").write_text("nope")
        code, out = self.check()
        self.assertEqual(code, 3, out)
        self.assertIn("state/item.json", out)
        self.assertEqual((self.db.path / "state" / "item.json").read_text(), "nope")

    def test_body_mismatch_exit_3(self):
        (self.db.path / "bodies" / "2.txt").write_text("被改过")
        code, out = self.check()
        self.assertEqual(code, 3, out)
        self.assertIn("正文指纹不符：bodies/2.txt", out)

    def test_orphan_body_is_warning(self):
        (self.db.path / "bodies" / "7.txt").write_text("孤立")
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("孤立正文", out)

    def test_check_never_writes(self):
        (self.db.path / "state" / "item.json").rename(self.db.path / "elsewhere")
        files = lambda: sorted(str(p) for p in self.db.path.rglob("*"))
        before = files()
        self.check()
        self.assertEqual(files(), before)


if __name__ == "__main__":
    unittest.main()
