"""crew-hub-bridge outputs: review lines, the 【等待用户】 for the hub, the read-only sessions export."""

import unittest

from helpers import ReviewCase

from module_crew import protocol, review, sources, store


def conclusion(module="b", node="Spec", verdict="通过", ref="R-1"):
    return (f"【审查结论】\n审查编号：{ref}\n节点：{node}\n模块：{module}\n送审方：前端\n结论：{verdict}\n"
            "来自：live-saas-arch-review\n要点：接口清楚。\n")


class HubCase(ReviewCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        sources.add(self.db, "live-saas-arch-review", "lead", "登记审查会话")
        self.spec = review.add(self.db, self.spec_review("b"), "shop-b", 4001).number
        self.plan = review.add(self.db, self.plan_review("b"), "shop-b", 4002).number


class NoteTest(HubCase):
    def test_note_shows_in_batch(self):
        review.note(self.db, self.spec, "live-saas-arch-review", conclusion())
        items = {i["number"]: i for i in review.batch(self.repo)["items"]}
        self.assertEqual(review._review_text(items[self.spec]), "live-saas-arch-review 通过")
        self.assertEqual(review._review_text(items[self.plan]), "未审查")
        out = self.run_cli("review", "batch", cwd=self.repo).stdout
        self.assertIn("审查：live-saas-arch-review 通过", out)
        self.assertIn("审查：未审查", out)

    def test_note_refused(self):
        before = store.events(self.db)
        for args in ((self.spec, "someone", conclusion()),                       # not a registered reviewer
                     (self.spec, "live-saas-arch-review", "随便写写"),            # not a conclusion
                     (self.spec, "live-saas-arch-review", conclusion(module="c")),  # other module
                     (self.spec, "live-saas-arch-review", conclusion(node="Plan")),  # other node
                     (999, "live-saas-arch-review", conclusion())):
            with self.assertRaises(review.NoteRefused):
                review.note(self.db, *args)
        self.assertEqual(store.events(self.db), before)

    def test_approval_not_blocked_without_review(self):
        self.assertEqual(review.approve(self.repo, [self.spec, self.plan], "批准").code, 0)


class ForHubTest(HubCase):
    def test_wait_user_for_hub(self):
        review.note(self.db, self.spec, "live-saas-arch-review", conclusion())
        [(n, path, text)] = review.for_hub(self.repo)
        msg = protocol.parse(path.read_text(encoding="utf-8"))
        self.assertEqual((msg.kind, msg.ok), ("wait-user", True), msg.problems)
        for want in (f"C{self.spec}", "b 的 Spec", "审查：live-saas-arch-review 通过", "架构审查：通过",
                     "推荐 A：批准", "B：退回修改"):
            self.assertIn(want, text)
        # crew-review-nearby: with a reviewer registered, a review still under review stays out
        self.assertNotIn(f"C{self.plan}", msg.fields["要你决定"])
        self.assertEqual(store.read_body(self.db, n), text)
        # rehearsal T1: project line, the review's points as written, full suggested reply
        self.assertEqual(msg.fields["项目"].strip(), self.repo.name)
        self.assertIn("- 不做：后台", msg.fields["要点"])
        self.assertEqual(msg.fields["你该回"].strip(), "A")

    def test_all_reviewed_and_parallel(self):
        review.note(self.db, self.spec, "live-saas-arch-review", conclusion(verdict="通过，附建议2条"))
        review.note(self.db, self.plan, "live-saas-arch-review", conclusion(node="Plan"))
        made = review.for_hub(self.repo, parallel_with=118)
        self.assertEqual(len(made), 2)                       # separate cadence: Spec and Plan are two items
        text = made[0][2]
        msg = protocol.parse(text)
        self.assertTrue(msg.ok, msg.problems)
        self.assertIn(("parallel", 118), msg.markers)
        self.assertIn("架构审查：通过，附建议2条（接口清楚。）", text)
        self.assertIn("审查：live-saas-arch-review 通过，附建议2条：接口清楚。", text)   # advice text, not just the count
        line = protocol._review_line(msg.fields["架构审查"].strip())
        self.assertEqual((line["status"], line["adviceCount"]), ("passed-with-advice", 2))

    def test_cli(self):
        review.note(self.db, self.spec, "live-saas-arch-review", conclusion())
        out = self.run_cli("review", "batch", "--for-hub", "--parallel-with", "7", cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("【与 #7 并行】", out.stdout)
        self.assertIn("正文文件", out.stdout)



class SessionsExportTest(HubCase):
    CONTRACT = ("module", "relayName", "worktree", "stage", "stageText", "suspended", "lastActivity")

    def export(self):
        import json
        out = self.run_cli("sessions", "--json", cwd=self.repo)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_contract_fields(self):
        import time
        from module_crew import failure
        failure.suspend(self.db, "c", "等设计稿", "先挂起 c")
        start = time.monotonic()
        doc = self.export()
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 1.0)
        self.assertEqual(doc["schemaVersion"], 1)
        rows = {r["module"]: r for r in doc["sessions"]}
        for r in rows.values():
            self.assertTrue(set(self.CONTRACT) <= set(r))
            self.assertEqual(r["relayName"], f"shop-{r['module']}")
        self.assertEqual(rows["b"]["stage"], "spec-plan")
        self.assertEqual(rows["c"]["suspended"], "等设计稿")

    def test_stage_codes(self):
        from module_crew import failure, hooks
        cases = {hooks.STAGE_WRITE: "spec-plan", hooks.STAGE_BUILD: "build",
                 hooks.STAGE_BUILD + "（上次最终验收被退回：检查失败）": "returned",
                 hooks.STAGE_WAIT_MERGE: "wait-merge", hooks.STAGE_MERGED: "merged"}
        for text, code in cases.items():
            self.assertEqual(failure.stage_code(text), code)

    def test_unreadable_exits_2_with_reason(self):
        outside = self.tmp / "plain"
        outside.mkdir()
        out = self.run_cli("sessions", "--json", cwd=outside)
        self.assertEqual(out.returncode, 2)
        self.assertEqual(out.stdout, "")
        self.assertTrue(out.stderr.strip())

    def test_interface_json(self):
        import json
        from helpers import PLUGIN_ROOT
        from module_crew import failure
        doc = json.loads((PLUGIN_ROOT / "interface.json").read_text(encoding="utf-8"))
        plugin = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["version"], plugin["version"])
        self.assertEqual(doc["contract"], protocol.CONTRACT_VERSION)
        self.assertEqual(doc["sessions"]["schemaVersion"], failure.SESSIONS_SCHEMA)
        self.assertEqual(doc["sessions"]["command"][1:], ["sessions", "--json"])
        self.assertTrue((PLUGIN_ROOT / doc["sessions"]["command"][0]).exists())


if __name__ == "__main__":
    unittest.main()
