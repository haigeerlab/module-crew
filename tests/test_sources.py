import unittest

from helpers import MergeCase, ReviewCase, RepoCase, git, seed_sessions

from module_crew import protocol, sources, store


def hub_reply(item=120, original="批准 #4 #5", relay=6001):
    return protocol.render_user_reply(item, original, "2026-10-18T12:00:00+08:00", source_relay_id=relay)


def handoff(item=130, original="同意接口提案，先按 v2 字段做", scope="b 按 v2 字段实现"):
    return (f"【负责人转交】\n事项：#{item}（由架构审查抛出，原消息 #650）\n来自：架构审查\n用户原话：{original}\n"
            f"答复时间：2026-10-18T15:30:00+08:00\n转交范围：{scope}\n")


class SourceCase(RepoCase):
    def setUp(self):
        super().setUp()
        self.db, _ = store.init_store(self.repo)
        seed_sessions(self.db)
        with self.db.transaction(actor="t") as tx:
            tx.put("config", "main", {"projectShort": "shop", "integrationBranch": "main"}, action="set")


class WhitelistTest(SourceCase):
    def test_add_list_remove(self):
        sources.add(self.db, "live-saas-hub", "hub", "登记收件枢纽")
        rows = sources.listing(self.db)
        self.assertEqual([(r["name"], r["kind"], r["original"]) for r in rows], [("live-saas-hub", "hub", "登记收件枢纽")])
        self.assertEqual(store.get(self.db, "config", "main")["projectShort"], "shop")  # rest of the config kept
        sources.remove(self.db, "live-saas-hub", "撤掉")
        self.assertEqual(sources.listing(self.db), [])

    def test_refusals_write_nothing(self):
        sources.add(self.db, "live-saas-hub", "hub", "登记")
        before = store.events(self.db)
        for call in (lambda: sources.add(self.db, "x", "hub", " "),
                     lambda: sources.add(self.db, "live-saas-hub", "hub", "再登记"),
                     lambda: sources.add(self.db, "y", "boss", "登记"),
                     lambda: sources.remove(self.db, "nobody", "撤"),
                     lambda: sources.remove(self.db, "live-saas-hub", "")):
            with self.assertRaises(sources.SourceRefused):
                call()
        self.assertEqual(store.events(self.db), before)


class CheckTest(SourceCase):
    def setUp(self):
        super().setUp()
        sources.add(self.db, "live-saas-hub", "hub", "登记收件枢纽")
        sources.add(self.db, "live-saas-arch-review", "lead", "登记审查会话", scope=sources.ALL_SCOPE)

    def test_hub_reply_accepted(self):
        info = sources.check(self.db, "live-saas-hub", 120, 6100, hub_reply(), sender="live-saas-hub")
        self.assertEqual(info.original, "批准 #4 #5")
        self.assertEqual(info.source, {"name": "live-saas-hub", "kind": "hub", "item": 120, "relayId": 6100})

    def test_lead_handoff_accepted(self):
        info = sources.check(self.db, "live-saas-arch-review", 130, 6200, handoff(), sender="live-saas-arch-review")
        self.assertEqual(info.original, "同意接口提案，先按 v2 字段做")
        self.assertEqual((info.source["owner"], info.source["scope"]), ("架构审查", "b 按 v2 字段实现"))
        self.assertEqual(sources.relay_line(info.source), "架构审查（负责人转交），消息 #6200")

    def test_refused(self):
        cases = [("someone", 120, hub_reply()),                 # not whitelisted
                 ("live-saas-hub", 121, hub_reply()),           # item mismatch
                 ("live-saas-hub", 120, "随便写的话"),           # not a user reply
                 ("live-saas-hub", 120, ""),                    # empty
                 ("live-saas-arch-review", 120, hub_reply()),   # lead must send 【负责人转交】
                 ("live-saas-hub", 130, handoff())]             # hub must send 【用户答复】
        for name, item, text in cases:
            with self.subTest(name=name, item=item):
                with self.assertRaises(sources.SourceRefused):
                    sources.check(self.db, name, item, 1, text, sender=name)

    def test_sender_must_be_the_source(self):
        with self.assertRaises(sources.SourceRefused):
            sources.check(self.db, "live-saas-hub", 120, 6100, hub_reply(), sender="someone-else")

    def test_cli(self):
        out = self.run_cli("source", "add", "other-hub", "--kind", "hub", "--original", "登记", cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("other-hub", self.run_cli("source", "list", cwd=self.repo).stdout)
        out = self.run_cli("source", "add", "other-hub", "--kind", "hub", "--original", "登记", cwd=self.repo)
        self.assertEqual(out.returncode, 3)
        self.assertEqual(self.run_cli("source", "remove", "other-hub", "--original", "撤", cwd=self.repo).returncode, 0)



class ApproveWithSourceTest(ReviewCase):
    def setUp(self):
        super().setUp()
        from module_crew import review
        self.db = store.open_store(self.repo)
        sources.add(self.db, "live-saas-hub", "hub", "登记收件枢纽")
        self.spec = review.add(self.db, self.spec_review("b"), "shop-b", 4001).number
        self.plan = review.add(self.db, self.plan_review("b"), "shop-b", 4002).number
        self.msg = self.tmp / "hub.txt"
        self.msg.write_text(hub_reply(120, "两个都批准"), encoding="utf-8")

    def test_one_hub_item_approves_two_reviews(self):
        out = self.run_cli("review", "approve", str(self.spec), str(self.plan), "--source", "live-saas-hub",
                           "--source-item", "120", "--source-relay-id", "6100", "--source-from", "live-saas-hub", "--original-file", str(self.msg), cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        want = {"name": "live-saas-hub", "kind": "hub", "item": 120, "relayId": 6100}
        for n in (self.spec, self.plan):
            ans = store.get(self.db, "item", str(n))["answer"]
            self.assertEqual((ans["original"], ans["source"]), ("两个都批准", want))
        numbers = {r["number"] for r in sources.map_item(self.db, 120)}
        self.assertTrue({self.spec, self.plan} <= numbers)
        self.assertEqual(sources.map_crew(self.db, self.spec), want)
        self.assertIn("replyTo：4001，alsoAnswers：4002", out.stdout)
        listed = self.run_cli("source", "map", "120", cwd=self.repo).stdout
        self.assertIn(f"C{self.spec}", listed)
        self.assertIn("live-saas-hub", self.run_cli("source", "map", f"C{self.plan}", cwd=self.repo).stdout)

    def test_relayed_reply_and_closing(self):
        from module_crew import review
        with store.approval_source(sources.check(self.db, "live-saas-hub", 120, 6100, self.msg.read_text(), sender="live-saas-hub").source):
            res = review.approve(self.repo, [self.spec, self.plan], "两个都批准")
        self.assertEqual(res.code, 0, res.lines)
        replies = [x for x in res.sends if x["kind"] == "user-reply"]
        self.assertEqual(len(replies), 1)                      # one reply per recipient (v1.6)
        self.assertEqual((replies[0]["replyTo"], replies[0]["alsoAnswers"]), (4001, [4002]))   # T1: the second request too
        msg = protocol.parse(replies[0]["path"].read_text(encoding="utf-8"))
        self.assertTrue(msg.ok, msg.problems)
        origin = msg.contract()["origin"]
        self.assertEqual((msg.item, origin["originals"], origin["relayedFrom"], origin["relayMessage"]),
                         (120, [4001, 4002], "hub", 6100))
        self.assertEqual(msg.fields["用户原话"], "两个都批准")
        closing = [x for x in res.sends if x["kind"] == "resumed"]
        self.assertEqual(closing[0]["to"], "live-saas-hub")
        done = protocol.parse(closing[0]["path"].read_text(encoding="utf-8"))
        self.assertEqual((done.kind, done.ok, done.end.items), ("resumed", True, (120,)))

    def test_lead_approval_only_recorded(self):
        from module_crew import review
        sources.add(self.db, "live-saas-arch-review", "lead", "登记审查会话", scope=sources.ALL_SCOPE)
        src = sources.check(self.db, "live-saas-arch-review", 130, 6200, handoff(), sender="live-saas-arch-review").source
        head = git(self.repo, "rev-parse", "HEAD")
        with store.approval_source(src):
            res = review.approve(self.repo, [self.spec], "同意接口提案，先按 v2 字段做")
        self.assertEqual(res.code, 0, res.lines)
        self.assertIn("只记账", "\n".join(res.lines))
        self.assertEqual((res.sends, res.commit), ([], None))              # no reply, no start notice
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)         # no review mark on the baseline
        self.assertEqual(store.get(self.db, "item", str(self.spec))["state"], "open")
        rec = store.get(self.db, "item", str(res.approval))
        self.assertEqual((rec["kind"], rec["reviews"], rec["answer"]["original"], rec["answer"]["source"]["kind"]),
                         ("lead-record", [self.spec], "同意接口提案，先按 v2 字段做", "lead"))
        self.assertEqual(review.approve(self.repo, [self.spec, self.plan], "我亲手批准").code, 0)   # user can still approve

    def test_hub_approval_commit_names_hub_item(self):
        from module_crew import review
        with store.approval_source(sources.check(self.db, "live-saas-hub", 120, 6100, self.msg.read_text(), sender="live-saas-hub").source):
            self.assertEqual(review.approve(self.repo, [self.spec, self.plan], "两个都批准").code, 0)
        self.assertIn("待决事项 #120", git(self.repo, "log", "-1", "--format=%s"))

    def test_self_reply_unchanged(self):
        from module_crew import review
        res = review.approve(self.repo, [self.spec, self.plan], "批准")
        self.assertNotIn("收件枢纽", git(self.repo, "log", "-1", "--format=%s"))
        replies = [x for x in res.sends if x["kind"] == "user-reply"]
        self.assertEqual(len(replies), 2)
        self.assertEqual([x["alsoAnswers"] for x in replies], [[], []])
        self.assertNotIn("转自", replies[0]["path"].read_text(encoding="utf-8"))
        self.assertFalse([x for x in res.sends if x["kind"] == "resumed"])

    def test_bad_source_changes_nothing(self):
        before = (store.events(self.db), git(self.repo, "rev-parse", "HEAD"))
        for extra in (["--source", "nobody", "--source-item", "120", "--source-relay-id", "1", "--source-from", "nobody"],
                      ["--source", "live-saas-hub", "--source-item", "121", "--source-relay-id", "1", "--source-from", "live-saas-hub"],
                      # T16 ③: the message really came from someone else, or from a registered module session
                      ["--source", "live-saas-hub", "--source-item", "120", "--source-relay-id", "1", "--source-from", "other"],
                      ["--source", "live-saas-hub", "--source-item", "120", "--source-relay-id", "1", "--source-from", "shop-b"]):
            out = self.run_cli("review", "approve", str(self.spec), *extra, "--original-file", str(self.msg), cwd=self.repo)
            self.assertEqual(out.returncode, 3, out.stdout)
        out = self.run_cli("review", "approve", str(self.spec), "--source", "live-saas-hub", "--original-file", str(self.msg),
                           cwd=self.repo)
        self.assertEqual(out.returncode, 2)
        out = self.run_cli("review", "approve", str(self.spec), "--source", "live-saas-hub", "--source-item", "120",
                           "--source-relay-id", "1", "--original-file", str(self.msg), cwd=self.repo)   # no --source-from
        self.assertEqual(out.returncode, 2)
        self.assertIn("--source-from", out.stderr)
        self.assertEqual((store.events(self.db), git(self.repo, "rev-parse", "HEAD")), before)

    def test_module_session_is_never_a_source(self):
        sources.add(self.db, "shop-b", "hub", "误登记")          # even if registered by mistake
        with self.assertRaises(sources.SourceRefused):
            sources.check(self.db, "shop-b", 120, 6100, self.msg.read_text(), sender="shop-b")

    def test_self_approval_has_no_source(self):
        from module_crew import review
        self.assertEqual(review.approve(self.repo, [self.spec], "批准").code, 0)
        self.assertNotIn("source", store.get(self.db, "item", str(self.spec))["answer"])
        self.assertIsNone(sources.map_crew(self.db, self.spec))

    def test_other_commands_take_source(self):
        out = self.run_cli("suspend", "c", "--reason", "等设计稿", "--source", "live-saas-hub", "--source-item", "120",
                           "--source-relay-id", "6100", "--source-from", "live-saas-hub", "--original-file", str(self.msg), cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        rec = store.get(self.db, "session", "shop-c")
        self.assertEqual(rec["suspended"]["original"], "两个都批准")
        self.assertEqual(store.events(self.db, key="shop-c")[-1]["data"]["source"]["item"], 120)



class MergeApproveWithSourceTest(MergeCase):
    def test_cli_relays_and_closes(self):
        from module_crew import review
        db = store.open_store(self.repo)
        sources.add(db, "live-saas-hub", "hub", "登记收件枢纽")
        n = review.add(db, self.finish("b"), "shop-b", 4800).number
        msg = self.tmp / "hub.txt"
        msg.write_text(hub_reply(140, "b 验收通过"), encoding="utf-8")
        out = self.run_cli("merge", "approve", str(n), "--source", "live-saas-hub", "--source-item", "140",
                           "--source-relay-id", "6300", "--source-from", "live-saas-hub", "--original-file", str(msg), cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("发送 【已恢复】 → live-saas-hub", out.stdout)
        body = store.read_body(db, store.get(db, "item", str(n))["answer"]["body"])
        reply = protocol.parse(body)
        self.assertTrue(reply.ok, reply.problems)
        self.assertEqual((reply.item, reply.contract()["origin"]["originals"]), (140, [4800]))


if __name__ == "__main__":
    unittest.main()
