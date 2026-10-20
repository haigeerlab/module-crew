"""crew-routing-fixes: messages and injected roles only reach the session that has to act on them."""

import unittest

from helpers import ReviewCase
from test_changes import request

from module_crew import changes, failure, protocol, review, sources, store


class ReviewerScopeTest(ReviewCase):
    """Task 2: a 【交审】 goes only to the reviewers whose registered scope covers its module and node."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def test_forward_by_scope(self):
        sources.add(self.db, "arch-b", "lead", "登记审查会话", scope=sources.parse_scope("b", "spec,plan"))
        sources.add(self.db, "arch-final", "lead", "登记验收审查", scope=sources.parse_scope("全部", "final"))
        b_spec = review.add(self.db, self.spec_review("b"), "shop-b", 4001)
        self.assertEqual([s["to"] for s in b_spec.sends], ["arch-b"])
        self.assertEqual(store.get(self.db, "item", str(b_spec.number))["sentTo"], ["arch-b"])
        c_spec = review.add(self.db, self.spec_review("c"), "shop-c", 4002)
        self.assertEqual(c_spec.sends, [])
        self.assertIn("没有审查者负责 c 的 spec，未送审：照常等用户批", c_spec.lines)

    def test_overlapping_scopes_both_receive(self):
        sources.add(self.db, "arch", "lead", "登记", scope=sources.ALL_SCOPE)
        notes = sources.add(self.db, "arch-b", "lead", "登记", scope=sources.parse_scope("b", "spec"))
        self.assertEqual(len(notes), 1)
        self.assertIn("重叠", notes[0])
        out = review.add(self.db, self.spec_review("b"), "shop-b", 4001)
        self.assertEqual(sorted(s["to"] for s in out.sends), ["arch", "arch-b"])

    def test_lead_needs_scope(self):
        for call in (lambda: sources.add(self.db, "arch", "lead", "登记"),
                     lambda: sources.parse_scope(None, "spec"),
                     lambda: sources.parse_scope("b", " "),
                     lambda: sources.parse_scope("b", "spec,review"),
                     lambda: sources.add(self.db, "hub", "hub", "登记", scope=sources.ALL_SCOPE)):
            with self.assertRaises(sources.SourceRefused):
                call()
        self.assertEqual(sources.listing(self.db), [])
        self.assertEqual(sources.parse_scope("all", "全部"), sources.ALL_SCOPE)
        self.assertEqual(sources.parse_scope("c，b", "plan, spec"), {"modules": ["b", "c"], "nodes": ["plan", "spec"]})

    def test_legacy_lead_without_scope(self):
        # A pre-0.9.0 registration has no scope: it receives nothing until the user records one.
        with self.db.transaction(actor="coordinator") as tx:
            cfg = tx.get("config", "main") or {}
            tx.put("config", "main", {**cfg, "sources": [{"name": "arch", "kind": "lead", "addedAt": store.now(),
                                                          "original": "旧登记"}]}, action="source-added")
        out = review.add(self.db, self.spec_review("b"), "shop-b", 4001)
        self.assertEqual(out.sends, [])
        self.assertTrue(any(line.startswith("审查者 arch 没登记负责范围，没有送审") for line in out.lines), out.lines)
        sources.set_scope(self.db, "arch", sources.parse_scope("b", "全部"), "arch 负责 b")
        out = review.add(self.db, self.plan_review("b"), "shop-b", 4002)
        self.assertEqual([s["to"] for s in out.sends], ["arch"])
        with self.assertRaises(sources.SourceRefused):
            sources.set_scope(self.db, "nobody", sources.ALL_SCOPE, "x")

    def test_cli(self):
        bad = self.run_cli("source", "add", "arch", "--kind", "lead", "--original", "登记", cwd=self.repo)
        self.assertEqual(bad.returncode, 3)
        self.assertIn("负责", bad.stderr)
        ok = self.run_cli("source", "add", "arch", "--kind", "lead", "--modules", "b", "--nodes", "spec,plan",
                          "--original", "登记", cwd=self.repo)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("模块 b × 节点 plan、spec", ok.stdout)
        hub = self.run_cli("source", "add", "hub", "--kind", "hub", "--nodes", "spec", "--original", "登记", cwd=self.repo)
        self.assertEqual(hub.returncode, 3)
        scoped = self.run_cli("source", "scope", "arch", "--modules", "全部", "--nodes", "final", "--original", "改范围",
                              cwd=self.repo)
        self.assertEqual(scoped.returncode, 0, scoped.stderr)
        listed = self.run_cli("source", "list", cwd=self.repo)
        self.assertIn("arch（lead，模块 全部 × 节点 final）", listed.stdout)


class SuspendedSyncTest(ReviewCase):
    """Task 3: change land skips a suspended module (the requester still gets its reply); resume says what landed."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def land(self, sender, rid, path):
        n = changes.add(self.db, request([path]), sender, rid).number
        (self.repo / path).write_text(f"{path}\n", encoding="utf-8")
        res = changes.land(self.repo, n)
        self.assertEqual(res.code, 0, res.lines)
        return n, res

    def test_suspended_module_skipped_then_told_on_resume(self):
        failure.suspend(self.db, "c", "等设计稿", "先挂起 c")
        n, res = self.land("shop-b", 4700, "tsconfig.base.json")
        self.assertEqual([x["to"] for x in res.sends], ["shop-b"])
        [note] = failure.resume(self.db, "c", "恢复 c").sends
        todo = protocol.parse(store.read_body(self.db, note["body"])).fields["要你做什么"]
        self.assertIn(f"落地了公共变更 C{n}（{res.commit[:7]}）", todo)
        self.assertIn("`module-crew sync`", todo)

    def test_suspended_requester_still_gets_its_reply(self):
        failure.suspend(self.db, "b", "等设计稿", "先挂起 b")
        _, res = self.land("shop-b", 4701, "tsconfig.base.json")
        by_to = {x["to"]: x for x in res.sends}
        self.assertEqual(sorted(by_to), ["shop-b", "shop-c"])
        self.assertEqual(by_to["shop-b"]["replyTo"], 4701)

    def test_resume_without_changes_unchanged(self):
        failure.suspend(self.db, "c", "等设计稿", "先挂起 c")
        [note] = failure.resume(self.db, "c", "恢复 c").sends
        todo = protocol.parse(store.read_body(self.db, note["body"])).fields["要你做什么"]
        self.assertEqual(todo, failure.RESUME_TODO)


if __name__ == "__main__":
    unittest.main()
