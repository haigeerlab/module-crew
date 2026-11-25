"""T800: ReviewCase builds its two worktrees once per class and hands each later test a fresh copy of them.
These tests run in name order: the first one dirties everything, the second must see none of it."""

from __future__ import annotations

from pathlib import Path

from helpers import ReviewCase, git

from module_crew import store

SEEN: list[Path] = []


class SnapshotIsolationCase(ReviewCase):

    def check_clean_copy(self) -> None:
        for earlier in SEEN:
            self.assertNotEqual(earlier, self.tmp)
            self.assertFalse(str(earlier) in (self.tmp / "claude" / "plugins" / "installed_plugins.json").read_text())
        SEEN.append(self.tmp)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        for m, wt in self.wt.items():
            self.assertTrue(wt.is_relative_to(self.tmp), wt)
            self.assertEqual(git(wt, "status", "--porcelain"), "")
            common = Path(git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()).resolve()
            self.assertEqual(common, (self.repo / ".git").resolve())
            self.assertEqual(git(wt, "rev-parse", "--abbrev-ref", "HEAD").strip(), m)
            self.assertFalse((wt / "dirty.txt").exists())
        listed = git(self.repo, "worktree", "list", "--porcelain")
        self.assertNotIn("prunable", listed)
        for wt in self.wt.values():
            self.assertIn(f"worktree {wt}", listed)
        self.assertFalse((self.repo / "dirty.txt").exists())
        db = store.open_store(self.repo)
        self.assertIsNone(store.get(db, "item", "9800"))
        state = self.repo / ".git" / "module-crew"
        texts = [p.read_text(encoding="utf-8") for p in state.rglob("*.json*") if p.is_file()]
        self.assertTrue(any(str(self.tmp) in t for t in texts))        # session records name the worktrees
        for t in texts:
            self.assertNotIn("crew-test-", t.replace(str(self.tmp), ""))

    def test_1_dirty_everything(self) -> None:
        self.check_clean_copy()
        (self.repo / "dirty.txt").write_text("x\n", encoding="utf-8")
        git(self.repo, "add", "dirty.txt")
        git(self.repo, "commit", "-q", "-m", "dirty")
        for wt in self.wt.values():
            (wt / "dirty.txt").write_text("x\n", encoding="utf-8")
        db = store.open_store(self.repo)
        with db.transaction(actor="test") as tx:
            tx.put("item", "9800", {"t800": "dirty"}, action="created")
        self.plugins.install("extra", {"interface": "1.0"})

    def test_2_sees_a_clean_copy(self) -> None:
        self.check_clean_copy()
        self.assertNotIn("extra@m", self.plugins.entries)
        self.plugins.install("extra", {"interface": "1.0"})      # the restored install count leaves no clash

    def test_3_sees_a_clean_copy_again(self) -> None:
        self.check_clean_copy()
        self.assertEqual(len(SEEN), 3)
