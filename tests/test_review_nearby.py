"""crew-review-nearby: review close to the coordinator, decisions for the user (spec/crew-review-nearby.md)."""

import unittest
from pathlib import Path
from datetime import datetime, timedelta

from helpers import MergeCase, ReviewCase, git, review_text

from module_crew import protocol, review, sources, store


def conclusion(verdict="通过", extra="", ref="R-7", node="Spec", module="b"):
    return (f"【审查结论】\n审查编号：{ref}\n节点：{node}\n模块：{module}\n送审方：shop-b\n结论：{verdict}\n"
            f"来自：arch\n要点：接口清楚。\n{extra}")


CHANGES = "须修改：\n1. 错误码表缺两项\n2. 超时没写\n"
DECISIONS = ("待用户决定：\nD1：alpha 首字母要不要大写？\n  A. 大写\n  B. 保持小写\n  倾向：B（与现有命名一致）\n"
             "D2：要不要支持空字符串？\n  A. 支持\n  B. 报错\n  倾向：A\n")


class ConclusionParseTest(unittest.TestCase):
    """Task 1: 【审查结论】 is judged now (contract v1.9 forms plus the v2.0 draft fields)."""

    def test_forms(self):
        for verdict, code, advice in (("通过", "passed", None), ("通过，附建议2条", "passed-with-advice", 2)):
            with self.subTest(verdict):
                msg = protocol.parse(conclusion(verdict))
                self.assertTrue(msg.ok, msg.problems)
                c = msg.contract()["conclusion"]
                self.assertEqual((c["ref"], c["node"], c["verdict"], c["adviceCount"], c["module"]),
                                 ("R-7", "spec", code, advice, "b"))

    def test_changes_required_with_count(self):
        msg = protocol.parse(conclusion("有须修改项2条", CHANGES))
        self.assertTrue(msg.ok, msg.problems)
        c = msg.contract()["conclusion"]
        self.assertEqual((c["verdict"], c["changeCount"], c["changes"]),
                         ("changes-required", 2, ["错误码表缺两项", "超时没写"]))

    def test_changes_problems(self):
        self.assertIn("missing-field:须修改", protocol.parse(conclusion("有须修改项2条")).problems)
        self.assertIn("change-count-mismatch", protocol.parse(conclusion("有须修改项3条", CHANGES)).problems)
        bare = protocol.parse(conclusion("有须修改项", CHANGES))   # v1.9 wording still valid
        self.assertTrue(bare.ok, bare.problems)
        self.assertIn("change-count-missing", bare.hints)

    def test_bad_verdict_and_node(self):
        self.assertIn("bad-verdict", protocol.parse(conclusion("差不多")).problems)
        self.assertIn("bad-node", protocol.parse(conclusion(node="需求")).problems)
        self.assertIsNone(protocol.parse(conclusion("差不多")).contract()["conclusion"])

    def test_decisions(self):
        msg = protocol.parse(conclusion("通过", DECISIONS))
        self.assertTrue(msg.ok, msg.problems)
        d = msg.contract()["decisions"]
        self.assertEqual([x["id"] for x in d], ["D1", "D2"])
        self.assertEqual(d[0]["question"], "alpha 首字母要不要大写？")
        self.assertEqual(d[0]["options"], [{"letter": "A", "text": "大写"}, {"letter": "B", "text": "保持小写"}])
        self.assertEqual(d[0]["lean"], "B")
        bad = "待用户决定：\nD1：要不要？\n  A. 要\n  倾向：A\n"           # only one option
        self.assertIn("bad-decision-item:D1", protocol.parse(conclusion("通过", bad)).problems)
        no_lean = "待用户决定：\nD1：要不要？\n  A. 要\n  B. 不要\n"
        self.assertIn("bad-decision-item:D1", protocol.parse(conclusion("通过", no_lean)).problems)


class SplitTest(unittest.TestCase):
    def test_sections(self):
        two = conclusion("通过") + "\n" + conclusion("有须修改项2条", CHANGES, ref="R-8", node="Plan")
        parts = protocol.split_sections(two)
        self.assertEqual(len(parts), 2)
        self.assertEqual([protocol.parse(p).contract()["conclusion"]["ref"] for p in parts], ["R-7", "R-8"])
        self.assertEqual(protocol.split_sections(conclusion()), [conclusion()])


class DisagreeTest(unittest.TestCase):
    def review(self, extra=""):
        return ("【交审】\n结束：无\n模块：b\n节点：Spec\n文件：\nspec/b.md sha256:0123456789abcdef\n"
                f"要点：\n- 做：页面\n- 不做：后台\n{extra}")

    def test_disagree_field(self):
        msg = protocol.parse(self.review("不同意：R-7：错误码表已在接口提案里定，不该在 Spec 里重复\n"))
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual(msg.contract()["submission"]["disputes"],
                         [{"review": "R-7", "reason": "错误码表已在接口提案里定，不该在 Spec 里重复"}])
        self.assertIn("bad-dispute-line", protocol.parse(self.review("不同意：就是不同意\n")).problems)
        self.assertNotIn("disputes", protocol.parse(self.review()).contract()["submission"])


class NoticeTest(unittest.TestCase):
    def test_rework(self):
        text = protocol.render_coordination_notice("rework", "审查 R-7（交审 C15）", "1. 补错误码\n2. 写超时", round=2)
        msg = protocol.parse(text)
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual((msg.contract()["notice"]["kind"], msg.contract()["notice"]["round"]), ("rework", 2))
        self.assertIn("missing-review-ref",
                      protocol.parse("【协调通知】\n类型：返工\n依据：交审 C15\n轮次：1\n要你做什么：改\n").problems)
        self.assertIn("bad-round",
                      protocol.parse("【协调通知】\n类型：返工\n依据：审查 R-7\n轮次：零\n要你做什么：改\n").problems)
        with self.assertRaises(ValueError):
            protocol.render_coordination_notice("rework", "审查 R-7", "改")          # round is required

    def test_revoke_and_crew_refs(self):
        msg = protocol.parse(protocol.render_coordination_notice(
            "approval-revoked", "C40（用户撤回答复 C52）", "停在当前停点，等新的答复"))
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual(msg.contract()["notice"]["kind"], "approval-revoked")
        # single use: the start notice cites the coordinator's local approval C40
        start = protocol.parse("【协调通知】\n类型：开工\n依据：C40（用户在协调会话批准；交审 C15）\n要你做什么：开始构建\n")
        self.assertTrue(start.ok, start.problems)
        self.assertEqual(start.contract()["notice"]["refs"], [])     # refs keeps hub numbers only
        self.assertIn("missing-approval-ref",
                      protocol.parse("【协调通知】\n类型：开工\n依据：交审\n要你做什么：开始\n").problems)

    def test_user_reply_crew_item(self):
        msg = protocol.parse("【用户答复】\n事项：C20（你的原消息 #4001）\n用户原话：A\n答复时间：2026-10-19T10:00:00+08:00\n")
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual((msg.item, msg.contract()["localItem"]), (None, "C20"))


class NearbyCase(ReviewCase):
    """b and c opened; a reviewer `arch` registered as a lead source (registration_lead=False skips it)."""
    with_lead = True

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        if self.with_lead:
            sources.add(self.db, "arch", "lead", "登记审查会话", scope=sources.ALL_SCOPE)

    def state(self, n, minutes=0):
        rec = store.get(self.db, "item", str(n))
        now = datetime.fromisoformat(rec["sentAt"]) + timedelta(minutes=minutes) if rec.get("sentAt") else None
        return review.review_state(self.db, n, now=now)


class ForwardTest(NearbyCase):
    """Task 3: 送审 and the review state of a submission."""

    def test_forward_to_reviewer(self):
        text = self.spec_review("b")
        out = review.add(self.db, text, "shop-b", 4001)
        self.assertEqual(out.code, 0, out.lines)
        [send] = out.sends
        self.assertEqual((send["kind"], send["to"], send["replyTo"]), ("review-forward", "arch", None))
        self.assertEqual(send["path"].read_text(encoding="utf-8"), text)         # the 【交审】 unchanged
        self.assertTrue(store.get(self.db, "item", str(out.number))["sentAt"])
        self.assertEqual(self.state(out.number), "reviewing")
        self.assertEqual(self.state(out.number, minutes=16), "timeout")          # 15 minutes without a conclusion
        cli = self.run_cli("review", "add", str(self.write(self.plan_review("b"))), "--from", "shop-b", "--relay-id", "4002",
                           cwd=self.repo)
        self.assertIn("发送 【交审】 → arch（送审），正文文件：", cli.stdout)

    def write(self, text):
        f = self.tmp / f"msg-{len(list(self.tmp.iterdir()))}.txt"
        f.write_text(text, encoding="utf-8")
        return f

    def test_disagree(self):
        first = review.add(self.db, self.spec_review("b"), "shop-b", 4001).number
        same = self.spec_review("b").replace("要点：", "不同意：R-7：错误码已在接口提案里定\n要点：")
        out = review.add(self.db, same, "shop-b", 4002)
        self.assertEqual(out.code, 0, out.lines)
        self.assertEqual(out.closed, [first])
        self.assertEqual(out.sends, [])                                            # not sent back to the reviewer
        self.assertEqual(self.state(out.number), "decide")
        self.assertEqual(store.get(self.db, "item", str(out.number))["disputes"][0]["review"], "R-7")
        spec = self.wt["b"] / "spec" / "b.md"
        spec.write_text(spec.read_text() + "改了\n")
        git(self.wt["b"], "commit", "-qam", "change")
        changed = self.spec_review("b").replace("要点：", "不同意：R-7：理由\n要点：")
        bad = review.add(self.db, changed, "shop-b", 4003)
        self.assertEqual(bad.code, 3)
        self.assertIn("上一版", " ".join(bad.lines))

    def test_disagree_needs_previous(self):
        text = self.spec_review("b").replace("要点：", "不同意：R-7：理由\n要点：")
        self.assertEqual(review.add(self.db, text, "shop-b", 4001).code, 3)


class NoteTest(NearbyCase):
    """Task 4: conclusions drive rework close to the coordinator; several sections in one message."""

    def submit(self, node="Spec", relay=None):
        text = self.spec_review("b") if node == "Spec" else self.plan_review("b")
        self.relay = getattr(self, "relay", 5000) + 1
        return review.add(self.db, text, "shop-b", relay or self.relay).number

    def test_rework_loop(self):
        head = git(self.repo, "rev-parse", "HEAD")
        n = self.submit()
        res = review.note(self.db, n, "arch", conclusion("有须修改项2条", CHANGES))
        [send] = res.sends
        self.assertEqual((send["kind"], send["to"]), ("rework", "shop-b"))
        msg = protocol.parse(send["path"].read_text(encoding="utf-8"))
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual(msg.contract()["notice"]["round"], 1)
        self.assertIn("R-7", msg.fields["依据"])
        self.assertIn(f"C{n}", msg.fields["依据"])
        self.assertIn("错误码表缺两项", msg.fields["要你做什么"])
        self.assertIn("超时没写", msg.fields["要你做什么"])
        self.assertEqual(self.state(n), "rework")
        self.assertEqual(store.get(self.db, "item", str(n))["state"], "open")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)               # nothing pushed forward
        again = self.submit()
        self.assertEqual(self.state(again), "reviewing")
        self.assertEqual(review._rounds(self.db, "b", "spec"), 1)
        self.assertFalse(review.note(self.db, again, "arch", conclusion("通过")).sends)
        self.assertEqual(self.state(again), "passed")

    def test_limit_three(self):
        n = self.submit()
        for i in range(3):
            self.assertEqual(len(review.note(self.db, n, "arch", conclusion("有须修改项2条", CHANGES)).sends), 1)
            n = self.submit()
        res = review.note(self.db, n, "arch", conclusion("有须修改项2条", CHANGES))
        self.assertEqual(res.sends, [])
        self.assertTrue(store.get(self.db, "item", str(n))["overLimit"])
        self.assertEqual(self.state(n), "decide")
        self.assertIn("已满 3 次", " ".join(res.lines))

    def test_decisions_recorded(self):
        n = self.submit()
        review.note(self.db, n, "arch", conclusion("通过", DECISIONS))
        self.assertEqual(self.state(n), "decide")
        self.assertEqual([d["id"] for d in store.get(self.db, "item", str(n))["reviews"][-1]["decisions"]], ["D1", "D2"])

    def test_multi_sections(self):
        spec, plan = self.submit(), self.submit("Plan")
        two = conclusion("通过") + "\n" + conclusion("有须修改项2条", CHANGES, ref="R-8", node="Plan")
        res = review.note(self.db, None, "arch", two)
        self.assertEqual([r["ref"] for r in res.rows], ["R-7", "R-8"])
        self.assertEqual((self.state(spec), self.state(plan)), ("passed", "rework"))
        before = store.events(self.db)
        bad = conclusion("通过") + "\n" + conclusion("差不多", ref="R-9", node="Plan")
        with self.assertRaises(review.NoteRefused) as ctx:
            review.note(self.db, None, "arch", bad)
        self.assertIn("第 2 段", str(ctx.exception))
        self.assertEqual(store.events(self.db), before)

    def test_then_batch(self):
        spec, plan = self.submit(), self.submit("Plan")
        f = self.tmp / "c1.txt"
        f.write_text(conclusion("通过"), encoding="utf-8")
        out = self.run_cli("review", "note", f"C{spec}", "--from", "arch", "--file", str(f), "--then-batch", "--for-hub",
                           cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn(f"还在等：C{plan}", out.stdout)
        self.assertNotIn("正文文件", out.stdout)
        f.write_text(conclusion("通过", node="Plan", ref="R-8"), encoding="utf-8")
        out = self.run_cli("review", "note", f"C{plan}", "--from", "arch", "--file", str(f), "--then-batch", "--for-hub",
                           cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("提请批准正文", out.stdout)


class BatchTest(NearbyCase):
    """Task 7: one item per module for the user, shown as it is (spec key decisions 5, 6)."""
    submit = NoteTest.submit

    def bodies(self):
        made = review.for_hub(self.repo)
        out = []
        for n, path, text in made:
            msg = protocol.parse(text)
            self.assertTrue(msg.ok, msg.problems)
            self.assertEqual(path.read_text(encoding="utf-8"), text)
            out.append((text, msg))
        return out

    def test_only_ready_reviews(self):
        spec, plan = self.submit(), self.submit("Plan")
        review.note(self.db, spec, "arch", conclusion("通过"))
        [(text, msg)] = self.bodies()
        self.assertIn(f"C{spec}", msg.fields["要你决定"])
        self.assertNotIn(f"C{plan}", msg.fields["要你决定"])                       # still under review
        review.note(self.db, plan, "arch", conclusion("有须修改项2条", CHANGES, node="Plan", ref="R-8"))
        self.assertNotIn(f"C{plan}", self.bodies()[0][1].fields["要你决定"])     # in rework

    def test_one_item_per_module(self):
        b = self.submit()
        c = review.add(self.db, self.spec_review("c"), "shop-c", 9001).number
        review.note(self.db, b, "arch", conclusion("通过"))
        review.note(self.db, c, "arch", conclusion("通过", module="c"))
        (tb, mb), (tc, mc) = self.bodies()
        self.assertIn(f"C{b}", mb.fields["要你决定"])
        self.assertNotIn(f"C{c}", mb.fields["要你决定"])
        self.assertIn(f"C{c}", mc.fields["要你决定"])
        self.assertEqual([r["module"] for _, r in sorted(store.records(self.db, "item").items(), key=lambda kv: int(kv[0]))
                          if r.get("kind") == "hub-batch"], ["b", "c"])

    def test_as_is_with_artifacts_and_originals(self):
        long = self.plan_review("b").replace("要点：\n- 做：页面与接口\n- 不做：后台",
                                              "要点：\n假设：\n1. 一\n2. 二\n3. 三\n4. 四\n5. 五")
        n = review.add(self.db, long, "shop-b", 7001).number
        verdict = conclusion("通过", node="Plan")
        review.note(self.db, n, "arch", verdict)
        [(text, msg)] = self.bodies()
        for line in ("1. 一", "5. 五"):
            self.assertIn(line, msg.fields["要点"])                                 # nothing cut
        self.assertNotIn("共 5 条", text)
        self.assertIn("在集成分支记批准标记", msg.fields["批了会怎样"])             # 0.9.5: the v2.3 field, not 批准会发生什么
        rec = store.get(self.db, "item", str(n))
        self.assertEqual({a["path"] for a in msg.contract()["artifacts"]},
                         {str(self.wt["b"] / "tasks" / "b" / "plan.md"), str(self.wt["b"] / "tasks" / "b" / "todo.md")})
        self.assertEqual({a["commit"] for a in msg.contract()["artifacts"]}, {rec["commit"]})
        import hashlib
        for row, original in ((msg.contract()["originals"]["submission"][0], long),
                              (msg.contract()["originals"]["conclusion"][0], verdict)):
            data = Path(row["path"]).read_bytes()
            self.assertEqual(data.decode("utf-8"), original)                       # word for word
            self.assertEqual(row["fingerprint"], "sha256:" + hashlib.sha256(data).hexdigest())

    def test_resubmit_shows_previous_version(self):
        n = self.submit()
        old = store.get(self.db, "item", str(n))["commit"]
        review.note(self.db, n, "arch", conclusion("有须修改项2条", CHANGES))
        spec = self.wt["b"] / "spec" / "b.md"
        spec.write_text(spec.read_text() + "补上错误码\n")
        git(self.wt["b"], "commit", "-qam", "fix")
        n = self.submit()
        review.note(self.db, n, "arch", conclusion("通过"))
        [(text, msg)] = self.bodies()
        [art] = msg.contract()["artifacts"]
        self.assertEqual(art["previousCommit"], old)
        self.assertIn("错误码表缺两项", msg.fields["要点"])                           # last round's changes, as written

    def test_decisions_field(self):
        n = self.submit()
        review.note(self.db, n, "arch", conclusion("通过", DECISIONS))
        [(text, msg)] = self.bodies()            # no inbox registered: C<交审号>-<序号> (crew-contract-v26)
        self.assertEqual([d["id"] for d in msg.contract()["decisions"]], [f"C{n}-1", f"C{n}-2"])
        self.assertEqual(msg.contract()["decisions"][0]["lean"], "B")
        self.assertEqual(msg.fields["你该回"].strip(), f"A；C{n}-1 B；C{n}-2 A")
        rec = [v for v in store.records(self.db, "item").values() if v.get("kind") == "hub-batch"][-1]
        self.assertEqual(rec["decisions"][f"C{n}-2"]["review"], n)

    def test_timeout_and_disagree_questions(self):
        n = self.submit()
        with self.db.transaction(actor="t") as tx:
            rec = tx.get("item", str(n))
            tx.put("item", str(n), dict(rec, sentAt="2026-01-01T00:00:00+08:00"), action="aged")
        [(text, msg)] = self.bodies()
        self.assertIn("未审查（审查者无响应）", text)
        self.assertIn("不等审查直接批", msg.fields["待用户决定"])
        # 0.9.5 (boundary review 6): each coordinator lean says why B is the cautious side, on the card too
        self.assertIn(f"倾向：B（{review.WHY_B['timeout']}）", msg.fields["待用户决定"])
        self.assertIn(review.WHY_B["timeout"], msg.fields["推荐理由"])
        self.assertNotIn("模块协调不替你判断", text)
        review.note(self.db, n, "arch", conclusion("有须修改项2条", CHANGES))
        same = self.spec_review("b").replace("要点：", "不同意：\nR-7：错误码已在接口提案里定\n要点：")
        review.add(self.db, same, "shop-b", 6001)
        [(text, msg)] = self.bodies()
        self.assertIn("按模块现版本批准", msg.fields["待用户决定"])
        self.assertIn("错误码已在接口提案里定", msg.fields["待用户决定"])
        self.assertIn(review.WHY_B["disagree"], msg.fields["待用户决定"])
        self.assertIn(review.WHY_B["disagree"], msg.fields["推荐理由"])

    def test_cadence_combined_puts_spec_and_plan_together(self):
        spec, plan = self.submit(), self.submit("Plan")
        review.note(self.db, spec, "arch", conclusion("通过"))
        review.note(self.db, plan, "arch", conclusion("通过", node="Plan", ref="R-8"))
        self.assertEqual(len(self.bodies()), 2)                                     # separate (the default): one node each
        cfg = self.repo / ".agent" / "config.json"
        cfg.parent.mkdir(exist_ok=True)
        cfg.write_text('{"version": 1, "reviewCadence": "combined"}', encoding="utf-8")
        [(text, msg)] = self.bodies()
        self.assertIn(f"C{spec}", msg.fields["要你决定"])
        self.assertIn(f"C{plan}", msg.fields["要你决定"])


class DecisionTest(NearbyCase):
    """Task 9: every D answered before anything happens; coordinator questions decide approve / return / hold."""
    submit = NoteTest.submit

    def age(self, n):
        with self.db.transaction(actor="t") as tx:
            rec = tx.get("item", str(n))
            tx.put("item", str(n), dict(rec, sentAt="2026-01-01T00:00:00+08:00"), action="aged")

    def test_missing_answer_refused_nothing_changes(self):
        n = self.submit()
        review.note(self.db, n, "arch", conclusion("通过", DECISIONS))
        before = (store.events(self.db), git(self.repo, "rev-parse", "HEAD"))
        res = review.approve(self.repo, [n], "A；D1 B")
        self.assertEqual(res.code, 3, res.lines)
        self.assertIn(f"C{n}-2", " ".join(res.lines))            # asked again in the numbering in use (no inbox: C)
        self.assertIn("要不要支持空字符串", " ".join(res.lines))                     # the question to chase
        self.assertEqual((store.events(self.db), git(self.repo, "rev-parse", "HEAD")), before)

    def test_all_answered_words_go_to_the_module(self):
        n = self.submit()
        review.note(self.db, n, "arch", conclusion("通过", DECISIONS))
        res = review.approve(self.repo, [n], "A；D1 B；D2：A")
        self.assertEqual(res.code, 0, res.lines)
        reply = [x for x in res.sends if x["kind"] == "user-reply"][0]["path"].read_text(encoding="utf-8")
        self.assertEqual(protocol.parse(reply).fields["用户原话"], "A；D1 B；D2：A")

    def disputed(self):
        n = self.submit()
        review.note(self.db, n, "arch", conclusion("有须修改项2条", CHANGES))
        same = self.spec_review("b").replace("要点：", "不同意：\nR-7：错误码已在接口提案里定\n要点：")
        self.relay += 1
        return review.add(self.db, same, "shop-b", self.relay).number

    def test_disagree_back_or_current(self):
        n = self.disputed()
        head = git(self.repo, "rev-parse", "HEAD")
        res = review.approve(self.repo, [n], "A；D1 选 B")                         # B: return, change as reviewed
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)                  # nothing approved
        self.assertEqual(store.get(self.db, "item", str(n))["closedReason"], "answered")
        self.assertTrue(any(x["kind"] == "user-reply" and x["to"] == "shop-b" for x in res.sends))
        self.assertIn("退回", " ".join(res.lines))
        n = self.disputed()
        self.assertEqual(review.approve(self.repo, [n], "A；D1 A").code, 0)
        self.assertNotEqual(git(self.repo, "rev-parse", "HEAD"), head)                # approved as it is

    def test_batch_text_lists_questions_for_the_coordinator(self):
        n = self.submit()
        review.note(self.db, n, "arch", conclusion("通过", DECISIONS))
        out = self.run_cli("review", "batch", cwd=self.repo).stdout
        self.assertIn("待你决定（没有决策收件箱时直接问你；批准时每个待定问题都要答到）", out)
        self.assertIn(f"C{n}-1：alpha 首字母要不要大写？", out)
        self.assertIn("- 不做：后台", out)                                        # points in full

    def test_timeout_hold(self):
        n = self.submit()
        self.age(n)
        res = review.approve(self.repo, [n], "A；D1 B")                             # B: wait for the review
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(store.get(self.db, "item", str(n))["state"], "open")
        self.assertIn("等审查", " ".join(res.lines))


class MergeDecisionTest(MergeCase):
    def test_merge_approve_checks_answers(self):
        db = store.open_store(self.repo)
        sources.add(db, "arch", "lead", "登记审查会话", scope=sources.ALL_SCOPE)
        n = review.add(db, self.finish("b"), "shop-b", 8101).number
        with db.transaction(actor="t") as tx:
            rec = tx.get("item", str(n))
            tx.put("item", str(n), dict(rec, sentAt="2026-01-01T00:00:00+08:00"), action="aged")
        out = self.run_cli("merge", "approve", f"C{n}", "--original", "A", cwd=self.repo)
        self.assertEqual(out.returncode, 3, out.stdout)
        self.assertIn(f"C{n}-1", out.stdout + out.stderr)
        out = self.run_cli("merge", "approve", f"C{n}", "--original", f"A；C{n}-1 A", cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)


class FinalOptionsTest(MergeCase):
    def test_evidence_required_and_shown_first(self):
        db = store.open_store(self.repo)
        text = self.finish("b")
        bare = text.replace("验收标准与证据：\n1：test_value 通过\n2：无\n\n", "")
        out = review.add(db, bare, "shop-b", 8000)
        self.assertEqual(out.code, 3)
        self.assertIn("验收结果", " ".join(out.lines))            # v2.6 name in the refusal
        self.assertEqual(review.add(db, text, "shop-b", 8001).code, 0)
        msg = protocol.parse(review.for_hub(self.repo)[0][2])
        lines = msg.fields["要点"].splitlines()
        self.assertTrue(lines[0].startswith("验收标准与证据"), lines[:3])
        self.assertEqual(lines[1:3], ["1：test_value 通过", "2：无"])

    def test_final_consequence_and_chinese_node(self):
        db = store.open_store(self.repo)
        review.add(db, self.finish("b"), "shop-b", 8001)
        text = review.for_hub(self.repo)[0][2]
        self.assertIn("合并进集成分支", text)
        self.assertIn("b 的 最终验收", text)
        self.assertNotIn("final", text)


class NoReviewerTest(NearbyCase):
    with_lead = False

    def test_no_forward_state_none(self):
        out = review.add(self.db, self.spec_review("b"), "shop-b", 4001)
        self.assertEqual((out.sends, review.review_state(self.db, out.number)), ([], "none"))


if __name__ == "__main__":
    unittest.main()


from helpers import StartCase  # noqa: E402
from module_crew import start  # noqa: E402


class CadenceTest(StartCase):
    """Task 10: the module follows the project's review cadence (R13)."""

    def kickoff(self, res, m):
        db = store.open_store(self.repo)
        return store.read_body(db, next(p for p in res.prepared if p["id"] == m)["kickoff"])

    def test_cadence_from_map_wins_when_present(self):
        """Task 15 (0.4.1): spec-guard 0.73.0+ /map --json carries the effective reviewCadence with its source."""
        from helpers import START_MAP
        self.set_map({**START_MAP, "reviewCadence": {"value": "combined", "source": ".agent/config.json"}})
        res = start.prepare(self.repo, ["b"], "开 b", short="shop")
        self.assertIn("Spec、Plan 各一条", self.kickoff(res, "b"))
        self.assertIn("评审节奏：combined（来源：.agent/config.json，读自 spec-guard /map）",
                      self.run_cli("status", cwd=self.repo).stdout)
        self.set_map({**START_MAP, "reviewCadence": {"value": "separate", "source": "default (config invalid)"}})
        self.assertIn("评审节奏：separate（来源：default (config invalid)，读自 spec-guard /map）",
                      self.run_cli("status", cwd=self.repo).stdout)

    def test_separate_by_default_then_combined(self):
        res = start.prepare(self.repo, ["b"], "开 b", short="shop")
        text = self.kickoff(res, "b")
        self.assertIn("只写 spec/b.md", text)
        self.assertIn("Spec 批准的【用户答复】到了再写 tasks/b/plan.md", text)
        self.assertIn("评审节奏：separate", text)
        self.assertIn("评审节奏：separate（项目没有设置 reviewCadence，按默认）", self.run_cli("status", cwd=self.repo).stdout)
        cfg = self.repo / ".agent" / "config.json"
        cfg.parent.mkdir(exist_ok=True)
        cfg.write_text('{"version": 1, "reviewCadence": "combined"}\n', encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "combined cadence")
        res = start.prepare(self.repo, ["c"], "开 c")
        text = self.kickoff(res, "c")
        self.assertIn("Spec、Plan 各一条", text)
        self.assertIn("评审节奏：combined", text)
        self.assertIn("仍先只交 Spec", text)
        self.assertIn("评审节奏：combined", self.run_cli("status", cwd=self.repo).stdout)


class RevokeTest(MergeCase):
    """Task 11: a merge approval can be taken back before the merge (R5)."""

    def test_revoke_before_merge(self):
        from module_crew import merge
        db = store.open_store(self.repo)
        n = self.approve_final("b", 1)
        review_no = store.get(db, "item", str(n))["review"]
        res = merge.revoke(db, n, "撤回 b 的验收批准，我答错了")
        self.assertEqual(store.get(db, "item", str(n))["closedReason"], "revoked")
        self.assertEqual(store.get(db, "item", str(review_no))["state"], "open")      # the user can answer again
        msg = protocol.parse(res.path.read_text(encoding="utf-8"))
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual((msg.contract()["notice"]["kind"], res.to), ("approval-revoked", "shop-b"))
        self.assertIn(f"C{n}", msg.fields["依据"])
        self.assertEqual(merge.run(self.repo, check_command=self.check_script()).code, 3)   # nothing queued any more
        cli = self.run_cli("merge", "revoke", f"C{n}", "--original", "再撤", cwd=self.repo)
        self.assertEqual(cli.returncode, 3)                                           # already revoked

    def test_merged_cannot_be_revoked(self):
        from module_crew import merge
        db = store.open_store(self.repo)
        n = self.approve_final("b", 1)
        self.assertEqual(merge.run(self.repo, check_command=self.check_script()).code, 0)
        with self.assertRaises(merge.AnswerRefused) as ctx:
            merge.revoke(db, n, "撤回")
        self.assertIn("已合并", str(ctx.exception))


class ProgressTest(NearbyCase):
    """Task 12: rework rounds visible in status and the read-only sessions export."""
    submit = NoteTest.submit

    def test_review_field(self):
        import json
        from module_crew import failure
        row = lambda: {r["module"]: r for r in failure.sessions(self.db)}["b"]
        self.assertIsNone(row()["review"])
        n = self.submit()
        self.assertEqual(row()["review"], {"state": "reviewing", "round": 0})
        review.note(self.db, n, "arch", conclusion("有须修改项2条", CHANGES))
        self.assertEqual(row()["review"], {"state": "rework", "round": 1})
        doc = json.loads(self.run_cli("sessions", "--json", cwd=self.repo).stdout)
        self.assertEqual(doc["schemaVersion"], 1)
        self.assertEqual({r["module"]: r["review"] for r in doc["sessions"]}["b"], {"state": "rework", "round": 1})
        self.assertIn("b 返工中（审查第 1 轮）", self.run_cli("status", cwd=self.repo).stdout)
        review.note(self.db, self.submit(), "arch", conclusion("通过"))
        self.assertIsNone(row()["review"])


class ReturnKindTest(MergeCase):
    """Task 14 (R20⑤): a returned module is told whether it has to change anything."""

    def test_env_failure_and_renotice(self):
        from module_crew import merge
        db = store.open_store(self.repo)
        n = self.approve_final("b", 1)
        res = merge.run(self.repo, check_command="no-such-check-command-xyz")
        self.assertEqual(res.code, 5, res.lines)
        self.assertEqual(store.get(db, "item", str(n))["returnKind"], "env")
        [note] = [x for x in res.sends if x["to"] == "shop-b"]
        msg = protocol.parse(store.read_body(db, note["body"]))
        self.assertTrue(msg.ok, msg.problems)
        self.assertEqual(msg.contract()["notice"]["kind"], "returned")
        self.assertIn("与你的代码无关", msg.fields["要你做什么"])
        self.assertIn("用原提交重新发最终验收【交审】", msg.fields["要你做什么"])
        head = git(self.repo, "rev-parse", "HEAD")
        again = merge.renotice(db, n, "module")
        self.assertIn("修好后重新发最终验收【交审】", protocol.parse(again.path.read_text(encoding="utf-8")).fields["要你做什么"])
        self.assertEqual(store.get(db, "item", str(n))["returnKind"], "module")
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)                   # integration branch untouched
        out = self.run_cli("merge", "renotice", f"C{n}", "--env", cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(store.get(db, "item", str(n))["returnKind"], "env")

    def test_check_failure_is_module(self):
        from module_crew import merge
        db = store.open_store(self.repo)
        n = self.approve_final("b", 1)
        res = merge.run(self.repo, check_command=self.check_script(fail_if="src/b.py"))
        self.assertEqual(res.code, 5, res.lines)
        self.assertEqual(store.get(db, "item", str(n))["returnKind"], "module")
        with self.assertRaises(merge.AnswerRefused):
            merge.renotice(db, self.approve_final("c", 2), "env")                     # not returned


class HookOutputTest(MergeCase):
    """Task 14 (R20⑥): merge run shows that the commit hooks ran and what they said."""

    def hook(self, code):
        path = self.repo / ".git" / "hooks" / "commit-msg"
        path.write_text(f"#!/bin/sh\necho hook-line-1\necho hook-line-2 >&2\nexit {code}\n")
        path.chmod(0o755)

    def test_passing_and_refusing_hooks_are_shown(self):
        from module_crew import merge
        self.hook(0)
        self.approve_final("b", 1)
        res = merge.run(self.repo, check_command=self.check_script())
        self.assertEqual(res.code, 0, res.lines)
        text = "\n".join(res.lines)
        self.assertIn("提交钩子：退出码 0", text)
        self.assertIn("hook-line-2", text)
        self.approve_final("c", 2)              # worktrees share the hooks: commit c's code while the hook still passes
        self.hook(1)
        res = merge.run(self.repo, check_command=self.check_script())
        self.assertEqual(res.code, 4, res.lines)
        self.assertIn("提交钩子：退出码 1", "\n".join(res.lines))
