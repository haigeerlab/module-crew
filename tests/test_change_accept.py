"""S52 (T388): a 【公共变更请求】 whose scope the user approved lands with the requester module's merge."""

import unittest

from helpers import MergeCase, git

from module_crew import changes, merge, protocol, store


def request(files, what="退役旧前端", why="模块要删旧文件", stopped="否"):
    lines = "\n".join(files)
    return (f"【公共变更请求】\n结束：无\n来自：b\n文件：\n{lines}\n改什么：{what}\n为什么：{why}\n"
            f"是否完全停住：{stopped}\n")


class AcceptCase(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        # files on the integration branch the module may change or delete
        for rel in ("old/a.vue", "old/b.vue", "old/c.vue", "shared.json", "lock.json"):
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text("x\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base files")
        for wt in self.wt.values():
            git(wt, "merge", "-q", "main")

    def scoped(self, files, rid=100, stopped="否") -> int:
        n = changes.add(self.db, request(files, stopped=stopped), "shop-b", rid).number
        changes.accept(self.db, n, "范围批准，随模块合并")
        return n

    def module_edit(self, delete=(), modify=()):
        for rel in delete:
            git(self.wt["b"], "rm", "-q", rel)
        for rel in modify:
            (self.wt["b"] / rel).write_text("changed\n", encoding="utf-8")
        git(self.wt["b"], "add", "-A")
        git(self.wt["b"], "commit", "-q", "-m", "b: retire old frontend")

    def merge_b(self, rid=900):
        self.approve_final("b", rid)
        return merge.run(self.repo, check_command="python3 -c pass")


class AcceptTest(AcceptCase):
    def test_accept_keeps_request_open_and_replies(self):
        n = changes.add(self.db, request(["old/a.vue"], stopped="是"), "shop-b", 10).number
        reply = changes.accept(self.db, n, "范围批准，随模块合并")
        rec = store.get(self.db, "request", str(n))
        self.assertEqual(rec["state"], "open")
        self.assertEqual(rec["accepted"]["original"], "范围批准，随模块合并")
        self.assertEqual(store.get(self.db, "ticket", str(rec["ticket"]))["state"], "open")
        self.assertEqual((reply.to, reply.reply_to), ("shop-b", 10))
        self.assertTrue(protocol.parse(store.read_body(self.db, reply.body)).ok)
        self.assertEqual([k for k, _ in changes.pending(self.db)], [n])
        with self.assertRaises(changes.AnswerRefused):
            changes.accept(self.db, n, "再批一次")

    def test_land_refused_answer_still_declines(self):
        n = self.scoped(["old/a.vue"])
        res = changes.land(self.repo, n)
        self.assertEqual(res.code, 3)
        self.assertIn("随模块合并", res.lines[0])
        self.assertEqual(changes.land_batch(self.repo, [n, n + 100]).code, 3)
        changes.answer(self.db, n, "算了，不改")
        rec = store.get(self.db, "request", str(n))
        self.assertEqual((rec["state"], rec["closedReason"]), ("closed", "declined"))

    def test_same_module_overlap_does_not_supersede(self):
        n = self.scoped(["old/a.vue", "old/b.vue"])
        out = changes.add(self.db, request(["old/a.vue"]), "shop-b", 101)
        self.assertEqual(store.get(self.db, "request", str(n))["state"], "open")
        self.assertNotIn(n, out.closed)
        self.assertIn(f"conflict:{n}", store.get(self.db, "request", str(out.number))["hints"])

    def test_cli_accept_and_list(self):
        n = changes.add(self.db, request(["old/a.vue"]), "shop-b", 10).number
        words = self.tmp / "words.txt"
        words.write_text("范围批准\n", encoding="utf-8")
        r = self.run_cli("change", "accept", f"C{n}", "--original-file", str(words))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("待随模块合并", r.stdout)
        listed = self.run_cli("change", "list")
        self.assertIn("已批准范围、待随模块合并", listed.stdout)
        land = self.run_cli("change", "land", f"C{n}")
        self.assertEqual(land.returncode, 3)


class MergeLandTest(AcceptCase):
    def test_merge_closes_request_with_counts(self):
        n = self.scoped(["old/a.vue", "old/b.vue", "old/c.vue", "shared.json"], stopped="是")
        ticket = store.get(self.db, "request", str(n))["ticket"]
        self.module_edit(delete=["old/a.vue", "old/b.vue"], modify=["shared.json"])
        res = self.merge_b()
        self.assertEqual(res.code, 0, res.lines)
        rec = store.get(self.db, "request", str(n))
        self.assertEqual((rec["state"], rec["closedReason"], rec["commit"]),
                         ("closed", "merged-with-module", res.merge_commit))
        self.assertEqual(rec["landing"], {"changed": 1, "deleted": 2, "untouched": ["old/c.vue"]})
        self.assertEqual(store.get(self.db, "ticket", str(ticket))["state"], "closed")
        line = next(x for x in res.lines if f"C{n}" in x and "随模块合并落地" in x)
        self.assertIn("改了 1 个、删了 2 个", line)
        self.assertIn("old/c.vue", line)
        self.assertFalse((self.repo / "old/a.vue").exists())

    def test_protected_file_outside_list_refuses_merge(self):
        with self.db.transaction(actor="test") as tx:
            tx.put("config", "main", dict(tx.get("config", "main") or {}, protectedFiles=["lock.json"]), action="set")
        n = self.scoped(["old/a.vue"])
        self.module_edit(delete=["old/a.vue"], modify=["lock.json"])
        before = git(self.repo, "rev-parse", "HEAD")
        res = self.merge_b()
        self.assertEqual(res.code, 3)
        self.assertIn("lock.json（保护文件）", "\n".join(res.lines))
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)
        self.assertEqual(store.get(self.db, "request", str(n))["state"], "open")

    def test_other_request_file_outside_list_refuses_merge(self):
        other = changes.add(self.db, request(["shared.json"]), "shop-c", 300).number
        self.scoped(["old/a.vue"])
        self.module_edit(modify=["shared.json"])
        res = self.merge_b()
        self.assertEqual(res.code, 3)
        self.assertIn(f"shared.json（C{other} 的清单）", "\n".join(res.lines))

    def test_listed_protected_file_passes(self):
        with self.db.transaction(actor="test") as tx:
            tx.put("config", "main", dict(tx.get("config", "main") or {}, protectedFiles=["lock.json"]), action="set")
        n = self.scoped(["old/", "lock.json"])
        self.module_edit(delete=["old/a.vue"], modify=["lock.json"])
        res = self.merge_b()
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(store.get(self.db, "request", str(n))["landing"],
                         {"changed": 1, "deleted": 1, "untouched": []})

    def test_module_without_accepted_request_unaffected(self):
        n = changes.add(self.db, request(["shared.json"]), "shop-b", 400).number
        res = self.merge_b()
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(store.get(self.db, "request", str(n))["state"], "open")


if __name__ == "__main__":
    unittest.main()
