import hashlib
import unittest

from helpers import RepoCase

from module_crew import store

TEXT = "【交审】\n结束：无\n模块：crew-store\n"


class BodyTest(RepoCase):
    def setUp(self):
        super().setUp()
        self.db, _ = store.init_store(self.repo)

    def write(self, text=TEXT):
        with self.db.transaction(actor="coord") as tx:
            n = tx.allocate_number()
            rec = tx.write_body(n, text)
        return n, rec

    def test_round_trip_and_fingerprint(self):
        n, rec = self.write()
        path = self.db.path / rec["path"]
        self.assertEqual(path.read_bytes(), TEXT.encode())
        self.assertEqual(rec["sha256"], hashlib.sha256(TEXT.encode()).hexdigest())
        self.assertEqual(rec["bytes"], len(TEXT.encode()))
        self.assertEqual(store.get(self.db, "body", str(n)), rec)
        self.assertEqual(store.read_body(self.db, n), TEXT)
        self.assertIsNone(store.read_body(self.db, 99))

    def test_tampered_body_detected(self):
        n, rec = self.write()
        path = self.db.path / rec["path"]
        path.write_bytes(path.read_bytes().replace(b"store", b"stork"))
        with self.assertRaises(store.StoreCorrupt):
            store.read_body(self.db, n)

    def test_body_is_immutable(self):
        n, _ = self.write()
        with self.assertRaises(store.InvalidRecord):
            with self.db.transaction(actor="coord") as tx:
                tx.write_body(n, "改过的正文")
        self.assertEqual(store.read_body(self.db, n), TEXT)

    def test_rollback_leaves_no_body(self):
        with self.assertRaises(RuntimeError):
            with self.db.transaction(actor="coord") as tx:
                tx.write_body(tx.allocate_number(), TEXT)
                raise RuntimeError("boom")
        self.assertEqual(list((self.db.path / "bodies").iterdir()), [])

    def test_existing_orphan_file_set_aside(self):
        orphan = self.db.path / "bodies" / "1.txt"
        orphan.write_text("崩溃前写下的正文")
        n, _ = self.write()
        self.assertEqual(n, 1)
        kept = list(orphan.parent.glob("1.txt.orphan-*"))
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_text(), "崩溃前写下的正文")
        self.assertEqual(store.read_body(self.db, 1), TEXT)


if __name__ == "__main__":
    unittest.main()
