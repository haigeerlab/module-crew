import json
import unittest

from helpers import RepoCase

from module_crew import store


class RebuildTest(RepoCase):
    def setUp(self):
        super().setUp()
        self.db, _ = store.init_store(self.repo)
        with self.db.transaction(actor="a") as tx:
            for n in (1, 2, 3):
                tx.put("item", str(n), {"n": n}, action="created")
            tx.put("item", "2", {"n": 2, "closed": True}, action="closed")
        self.snap = self.db.path / "state" / "item.json"
        self.expected = store.records(self.db, "item")

    def last_seq(self):
        return json.loads(self.snap.read_text())["lastSeq"]

    def append_raw(self, text):
        with open(self.db.path / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(text)

    def test_missing_snapshot_rebuilt_from_log(self):
        self.snap.rename(self.snap.with_name("moved-away"))
        self.assertEqual(store.records(self.db, "item"), self.expected)
        self.assertEqual(store.get(self.db, "item", "2"), {"n": 2, "closed": True})
        self.assertFalse(self.snap.exists())  # readers never write
        with self.db.transaction(actor="a") as tx:
            tx.put("ticket", "4", {}, action="opened")
        self.assertTrue(self.snap.exists())
        self.assertEqual(self.last_seq(), 4)
        self.assertEqual(json.loads(self.snap.read_text())["records"], self.expected)

    def test_lagging_snapshot_read_with_warning(self):
        doc = json.loads(self.snap.read_text())
        event = {"v": 1, "seq": 5, "at": "2026-10-18T10:00:00+08:00", "type": "item.created",
                 "key": "5", "actor": "a", "data": {"record": {"n": 5}}}
        self.append_raw(json.dumps(event, ensure_ascii=False) + "\n")
        self.assertEqual(doc["lastSeq"], 4)
        self.assertEqual(store.get(self.db, "item", "5"), {"n": 5})
        self.assertIn("快照落后于日志 1 条：item", self.db.warnings)
        self.assertEqual(json.loads(self.snap.read_text()), doc)
        with self.db.transaction(actor="a") as tx:
            self.assertIn("快照落后于日志 1 条：item", tx.warnings)
            tx.put("ticket", "6", {}, action="opened")
        self.assertEqual(self.last_seq(), 5)

    def test_corrupt_snapshot_kept_as_evidence(self):
        self.snap.write_text("{not json")
        self.assertEqual(store.records(self.db, "item"), self.expected)
        self.assertIn("快照损坏，已从日志重算：state/item.json", self.db.warnings)
        with self.db.transaction(actor="a") as tx:
            tx.put("ticket", "5", {}, action="opened")
        kept = list(self.snap.parent.glob("item.json.corrupt-*"))
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_text(), "{not json")
        self.assertEqual(json.loads(self.snap.read_text())["records"], self.expected)

    def test_half_line_skipped_then_next_append_is_clean(self):
        self.append_raw('{"v": 1, "seq": 5, "ty')
        self.assertEqual(store.records(self.db, "item"), self.expected)
        self.assertTrue(any("末尾半行" in w for w in self.db.warnings))
        with self.db.transaction(actor="a") as tx:
            n = tx.allocate_number()
            tx.put("item", str(n), {"n": n}, action="created")
        self.assertEqual(n, 4)
        raw = (self.db.path / "events.jsonl").read_text()
        self.assertIn('{"v": 1, "seq": 5, "ty\n', raw)  # half line stays where it was
        self.assertEqual(json.loads(raw.splitlines()[-1])["key"], "4")
        self.assertEqual(store.get(self.db, "item", "4"), {"n": 4})
        self.assertTrue(any("无法解析" in w for w in self.db.warnings))


if __name__ == "__main__":
    unittest.main()
