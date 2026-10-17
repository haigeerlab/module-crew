import json
import unittest

from helpers import RepoCase

from module_crew import store


def snapshot_bytes(db):
    files = [p for p in db.path.rglob("*") if p.is_file() and p.name != ".lock"]
    return {str(p.relative_to(db.path)): p.read_bytes() for p in files}


class TransactionTest(RepoCase):
    def setUp(self):
        super().setUp()
        self.db, _ = store.init_store(self.repo)

    def test_numbers_and_seq_come_from_log(self):
        with self.db.transaction(actor="shop-coord") as tx:
            a = tx.allocate_number()
            tx.put("item", str(a), {"title": "批 Spec"}, action="created")
            b = tx.allocate_number()
            tx.put("request", str(b), {"files": ["package.json"]}, action="created")
        self.assertEqual((a, b), (1, 2))
        with self.db.transaction(actor="shop-coord") as tx:
            self.assertEqual(tx.allocate_number(), 3)
        lines = [json.loads(x) for x in (self.db.path / "events.jsonl").read_text().splitlines()]
        self.assertEqual([e["seq"] for e in lines], [1, 2])
        self.assertEqual(lines[0]["type"], "item.created")
        self.assertEqual(lines[0]["actor"], "shop-coord")
        self.assertEqual(lines[0]["data"]["record"], {"title": "批 Spec"})

    def test_unused_number_is_not_consumed(self):
        with self.db.transaction(actor="a") as tx:
            tx.allocate_number()
        with self.db.transaction(actor="a") as tx:
            self.assertEqual(tx.allocate_number(), 1)

    def test_each_put_appends_one_event_and_reads_see_pending(self):
        with self.db.transaction(actor="a") as tx:
            tx.put("item", "1", {"state": "open"}, action="created")
            self.assertEqual(tx.get("item", "1"), {"state": "open"})
            tx.put("item", "1", {"state": "closed"}, action="closed", data={"reason": 3})
        evs = store.events(self.db, key="1", kind="item")
        self.assertEqual([e["type"] for e in evs], ["item.created", "item.closed"])
        self.assertEqual(evs[1]["data"], {"reason": 3, "record": {"state": "closed"}})
        self.assertEqual(store.get(self.db, "item", "1"), {"state": "closed"})

    def test_exception_rolls_back_byte_for_byte(self):
        with self.db.transaction(actor="a") as tx:
            tx.put("item", "1", {"x": 1}, action="created")
        before = snapshot_bytes(self.db)
        with self.assertRaises(RuntimeError):
            with self.db.transaction(actor="a") as tx:
                n = tx.allocate_number()
                tx.put("item", str(n), {"x": 2}, action="created")
                tx.write_body(n, "正文")
                raise RuntimeError("boom")
        self.assertEqual(snapshot_bytes(self.db), before)
        with self.db.transaction(actor="a") as tx:
            self.assertEqual(tx.allocate_number(), 2)

    def test_no_writes_changes_nothing(self):
        before = snapshot_bytes(self.db)
        with self.db.transaction(actor="a") as tx:
            tx.records("item")
        self.assertEqual(snapshot_bytes(self.db), before)

    def test_invalid_writes_rejected_and_nothing_written(self):
        cases = [
            ("note", "1", {}, "created"),           # unknown kind
            ("item", "1", {}, "Created"),           # bad action
            ("item", "1", {}, "made new"),          # bad action
            ("item", "1", ["x"], "created"),        # record not an object
            ("item", "x", {}, "created"),           # numbered kind needs a number
            ("item", "0", {}, "created"),
            ("config", "other", {}, "set"),         # config key fixed
        ]
        before = snapshot_bytes(self.db)
        for kind, key, rec, action in cases:
            with self.subTest(kind=kind, key=key, action=action):
                with self.assertRaises(store.InvalidRecord):
                    with self.db.transaction(actor="a") as tx:
                        tx.put(kind, key, rec, action=action)
        self.assertEqual(snapshot_bytes(self.db), before)

    def test_config_round_trip(self):
        with self.db.transaction(actor="a") as tx:
            tx.put("config", "main", {"projectShort": "shop", "maxModules": 3}, action="set")
        self.assertEqual(store.get(self.db, "config", "main")["maxModules"], 3)
        self.assertIsNone(store.get(self.db, "item", "9"))


if __name__ == "__main__":
    unittest.main()
