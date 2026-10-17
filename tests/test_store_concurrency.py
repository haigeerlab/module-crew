import json
import multiprocessing
import sys
import time
import unittest

from helpers import RepoCase, allocate_worker, make_worktree

from module_crew import store


class ConcurrencyTest(RepoCase):
    def test_twenty_processes_across_checkouts(self):
        store.init_store(self.repo)
        wt = make_worktree(self.repo, "wt1")
        cwds = [str(self.repo if i % 2 else wt) for i in range(20)]
        ctx = multiprocessing.get_context("spawn")
        with ctx.Pool(20) as pool:
            results = pool.starmap(allocate_worker, [(c, 50) for c in cwds])
        numbers = sorted(n for r in results for n in r)
        self.assertEqual(numbers, list(range(1, 1001)))
        db = store.open_store(self.repo)
        lines = (db.path / "events.jsonl").read_text().splitlines()
        self.assertEqual([json.loads(x)["seq"] for x in lines], list(range(1, 1001)))
        self.assertEqual(len(store.records(db, "item")), 1000)
        self.assertEqual(db.warnings, [])

        start = time.perf_counter()
        with db.transaction(actor="timing") as tx:
            tx.put("item", str(tx.allocate_number()), {}, action="created")
        elapsed = (time.perf_counter() - start) * 1000
        print(f"\n  single transaction with 1000 events in log: {elapsed:.1f} ms", file=sys.stderr)


if __name__ == "__main__":
    unittest.main()
