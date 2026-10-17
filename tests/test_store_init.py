import json
import stat
import unittest

from helpers import RepoCase, git, make_worktree

from module_crew import store


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


class InitTest(RepoCase):
    def test_init_creates_private_store(self):
        db, created = store.init_store(self.repo)
        self.assertTrue(created)
        self.assertEqual(db.path, self.repo / ".git" / "module-crew")
        self.assertEqual(mode(db.path), 0o700)
        for name in ("meta.json", "events.jsonl"):
            self.assertEqual(mode(db.path / name), 0o600, name)
        self.assertEqual(json.loads((db.path / "meta.json").read_text())["version"], 1)

    def test_second_init_changes_nothing(self):
        db, _ = store.init_store(self.repo)
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in db.path.iterdir() if p.is_file()}
        result = self.run_cli("store", "init")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("已存在", result.stdout)
        after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in db.path.iterdir() if p.is_file()}
        self.assertEqual(before, after)

    def test_cli_init_creates(self):
        result = self.run_cli("store", "init")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.repo / ".git" / "module-crew" / "meta.json").exists())

    def test_worktree_sees_same_store_and_git_ignores_it(self):
        db, _ = store.init_store(self.repo)
        wt = make_worktree(self.repo, "wt1")
        self.assertEqual(store.open_store(wt).path, db.path)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        self.assertEqual(git(wt, "status", "--porcelain"), "")


class NotReadyTest(RepoCase):
    def test_outside_git_exit_2_no_dirs(self):
        outside = self.tmp / "plain"
        outside.mkdir()
        result = self.run_cli("store", "check", cwd=outside)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(list(outside.iterdir()), [])
        with self.assertRaises(store.NotInRepo):
            store.open_store(outside)

    def test_not_initialised_exit_2_no_dirs(self):
        result = self.run_cli("store", "check")
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.repo / ".git" / "module-crew").exists())
        with self.assertRaises(store.StoreNotFound):
            store.open_store(self.repo)


class MetaVersionTest(RepoCase):
    def test_unknown_meta_version_refuses_read_and_write(self):
        db, _ = store.init_store(self.repo)
        meta = db.path / "meta.json"
        meta.write_text(json.dumps({"version": 2, "createdAt": "x"}))
        before = meta.read_bytes()
        with self.assertRaises(store.StoreCorrupt):
            store.open_store(self.repo)
        with self.assertRaises(store.StoreCorrupt):
            with db.transaction(actor="system") as tx:
                tx.put("config", "main", {"a": 1}, action="set")
        self.assertEqual(meta.read_bytes(), before)
        self.assertEqual((db.path / "events.jsonl").read_bytes(), b"")


if __name__ == "__main__":
    unittest.main()
