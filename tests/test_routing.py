"""crew-routing-fixes: messages and injected roles only reach the session that has to act on them."""

import json
import os
import subprocess
import unittest

from helpers import PLUGIN_ROOT, ReviewCase
from test_changes import request

from module_crew import changes, failure, hooks, protocol, review, sources, start, store


def set_identity(db, name, session_id):
    """Write a session's bound identity directly (independent of the test runner's own environment)."""
    with db.transaction(actor="test") as tx:
        rec = dict(tx.get("session", name))
        if session_id is None:
            rec.pop("hostSession", None)
        else:
            rec["hostSession"] = {"sessionId": session_id, "boundAt": store.now()}
        tx.put("session", name, rec, action="bound")


def hook(event, cwd, session_id=None):
    payload = {"cwd": str(cwd)}
    if session_id is not None:
        payload["session_id"] = session_id
    r = subprocess.run([str(PLUGIN_ROOT / "bin" / "module-crew"), "hook", event], cwd=cwd, input=json.dumps(payload),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""


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


class BindTest(ReviewCase):
    """Task 4: a session records its own identity; takeover clears it for the new conversation."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def test_bind_rules(self):
        self.assertIn("已登记", hooks.bind(self.db, "shop-b", "sid-b"))
        self.assertEqual(store.get(self.db, "session", "shop-b")["hostSession"]["sessionId"], "sid-b")
        self.assertIn("已是本会话", hooks.bind(self.db, "shop-b", "sid-b"))
        with self.assertRaises(hooks.BindRefused) as ctx:
            hooks.bind(self.db, "shop-b", "sid-other")
        self.assertIn("takeover", str(ctx.exception))
        for name, sid in (("shop-x", "sid"), ("shop-c", " ")):
            with self.assertRaises(hooks.BindRefused):
                hooks.bind(self.db, name, sid)
        hooks.takeover(self.db, "shop-b", "让新会话接管 b")
        self.assertNotIn("hostSession", store.get(self.db, "session", "shop-b"))
        hooks.bind(self.db, "shop-b", "sid-new")
        self.assertEqual(store.get(self.db, "session", "shop-b")["hostSession"]["sessionId"], "sid-new")

    def test_invalid_identity_rejected_by_store(self):
        with self.assertRaises(store.StoreError):
            with self.db.transaction(actor="t") as tx:
                tx.put("session", "shop-c", {**tx.get("session", "shop-c"), "hostSession": {"sessionId": ""}},
                       action="bound")

    def test_cli_reads_own_environment(self):
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")}
        none = self.run_cli("bind", "shop-c", cwd=self.repo, env=env)
        self.assertEqual(none.returncode, 3)
        ok = self.run_cli("bind", "shop-c", cwd=self.repo, env={**env, "CLAUDE_CODE_SESSION_ID": "sid-c"})
        self.assertEqual(ok.returncode, 0, ok.stderr)
        codex = self.run_cli("bind", "shop-b", cwd=self.repo, env={**env, "CODEX_THREAD_ID": "thread-b"})
        self.assertEqual(codex.returncode, 0, codex.stderr)
        self.assertEqual(store.get(self.db, "session", "shop-b")["hostSession"]["sessionId"], "thread-b")
        other = self.run_cli("bind", "shop-c", cwd=self.repo, env={**env, "CLAUDE_CODE_SESSION_ID": "sid-x"})
        self.assertEqual(other.returncode, 3)

    def test_kickoff_recovery_and_status_mention_bind(self):
        kickoff = store.read_body(self.db, start.prepare(self.repo, ["d"], "开 d", short="shop").prepared[0]["kickoff"])
        self.assertIn("module-crew bind shop-d", kickoff)
        kit = store.read_body(self.db, failure.resume_kit(self.db, "b").body)
        self.assertIn("module-crew bind shop-b", kit)
        set_identity(self.db, "shop-c", "sid-c")
        out = self.run_cli("status", cwd=self.repo).stdout
        line_b = next(l for l in out.splitlines() if l.strip().startswith("shop-b"))
        line_c = next(l for l in out.splitlines() if l.strip().startswith("shop-c"))
        self.assertIn("未登记身份", line_b)
        self.assertNotIn("未登记身份", line_c)


class HookIdentityTest(ReviewCase):
    """Task 5: only the registered session gets the role; any other session in the directory gets one line, once."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        set_identity(self.db, "shop-b", "sid-b")
        set_identity(self.db, "shop-coord", "sid-coord")

    def test_registered_session_unchanged(self):
        text = hook("session-start", self.wt["b"], "sid-b")
        self.assertIn("你是模块 b 的模块会话", text)
        self.assertIn("你是 b 的模块会话", hook("prompt", self.wt["b"], "sid-b"))
        self.assertIn("本会话是模块协调", hook("session-start", self.repo, "sid-coord"))
        self.assertIn("模块协调", hook("prompt", self.repo, "sid-coord"))

    def test_other_session_in_worktree(self):
        # Replays cd5cd580／697ccda9／996bf975: permission tests in the alpha worktree were told they were alpha.
        for sid in ("sid-probe", None):
            text = hook("session-start", self.wt["b"], sid)
            self.assertNotIn("你是模块", text)
            self.assertIn("本目录属于模块 b（登记会话 shop-b）；你不是它的登记会话", text)
            self.assertEqual(hook("prompt", self.wt["b"], sid), "")

    def test_other_session_in_integration_checkout(self):
        # Replays 38932d81／cb182a33: two parallel coordinators were both told 「本会话是模块协调」.
        text = hook("session-start", self.repo, "sid-parallel-3")
        self.assertNotIn("本会话是模块协调", text)
        self.assertIn("集成 checkout（模块协调 shop-coord）；你不是它的登记会话", text)
        self.assertEqual(hook("prompt", self.repo, "sid-parallel-4"), "")

    def test_unbound_registration(self):
        text = hook("session-start", self.wt["c"], "sid-c")
        self.assertIn("本目录属于模块 c（登记会话 shop-c）", text)
        self.assertIn("module-crew bind shop-c", text)
        self.assertEqual(hook("prompt", self.wt["c"], "sid-c"), "")


if __name__ == "__main__":
    unittest.main()
