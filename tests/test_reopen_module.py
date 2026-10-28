"""crew-reopen-module: reopen a finished module that spec-guard reopened in place (spec/crew-reopen-module.md)."""

import copy
import json
import unittest

from helpers import START_MAP, MergeCase, RepoCase, StartCase, git, review_text

from module_crew import hooks, merge, review, stall, start, store


def dev(module, worktree="/tmp/w", status="active", **kw):
    return {"role": "dev", "host": "claude-desktop", "status": status, "module": module, "worktree": worktree, **kw}


class StoreReopenTest(RepoCase):
    def setUp(self):
        super().setUp()
        self.db, _ = store.init_store(self.repo)

    def put(self, key, rec):
        with self.db.transaction(actor="t") as tx:
            tx.put("session", key, rec, action="registered")

    def test_reopen_field_accepted(self):
        self.put("shop-x-r2", dev("x", reopen={"round": 2, "since": 7, "review": {"spec": "approved", "plan": "pending"}}))
        self.assertEqual(store.get(self.db, "session", "shop-x-r2")["reopen"]["since"], 7)

    def test_reopen_field_shape_checked(self):
        bad = [{"round": 1, "since": 7, "review": {"spec": "a", "plan": "b"}},
               {"round": 2, "since": 0, "review": {"spec": "a", "plan": "b"}},
               {"round": 2, "since": 7, "review": {"spec": "a"}},
               {"round": True, "since": 7, "review": {"spec": "a", "plan": "b"}},
               "r2"]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(store.InvalidSession):
                self.put("shop-x-r2", dev("x", reopen=value))

    def test_reopen_only_for_dev(self):
        with self.assertRaises(store.InvalidSession):
            self.put("shop-coord", {"role": "coordinator", "host": "claude-desktop", "status": "active",
                                    "reopen": {"round": 2, "since": 7, "review": {"spec": "a", "plan": "b"}}})

    def test_round_since(self):
        self.put("shop-x", dev("x", status="retired"))
        self.put("shop-y", dev("y"))
        sessions = store.records(self.db, "session")
        self.assertEqual(store.round_since(sessions, "x"), 0)
        self.assertEqual(store.round_since(sessions, "y"), 0)
        self.put("shop-x-r2", dev("x", reopen={"round": 2, "since": 9, "review": {"spec": "approved", "plan": "approved"}}))
        sessions = store.records(self.db, "session")
        self.assertEqual(store.round_since(sessions, "x"), 9)
        self.assertEqual(store.round_since(sessions, "y"), 0)
        self.assertEqual(store.round_since(sessions, "z"), 0)


def reopened_map(review=("approved", "approved"), **over):
    """START_MAP where the finished module `a` was reopened in place by spec-guard."""
    doc = copy.deepcopy(START_MAP)
    a = doc["modules"][0]
    a.update({"status": "in_progress", "worktree": None, "progress": {"done": 3, "total": 4},
              "firstTickAt": "2026-10-01T10:00:00+08:00", "review": {"spec": review[0], "plan": review[1]}})
    a.update(over)
    return doc


class ReopenCase(StartCase):
    """`a` was built and merged by an earlier round: retired session shop-a, a merged merge approval, branch a."""

    def setUp(self):
        super().setUp()
        self.set_map(reopened_map())
        git(self.repo, "branch", "a")
        (self.repo / "more.txt").write_text("y\n")
        git(self.repo, "add", "more.txt")
        git(self.repo, "commit", "-q", "-m", "later")
        self.db, _ = store.init_store(self.repo)
        with self.db.transaction(actor="t") as tx:
            tx.put("session", "shop-a", dev("a", str(self.tmp / "repo-crew" / "a"), status="retired"), action="registered")
            n = tx.allocate_number()
            tx.put("item", str(n), {"state": "closed", "kind": "merge-approval", "module": "a", "closedReason": "merged",
                                    "from": "shop-a", "relayId": None}, action="merged")

    def snapshot(self):
        files = {str(p): p.read_bytes() for p in self.repo.rglob("*") if p.is_file() and ".git/index" not in str(p)}
        return (files, git(self.repo, "branch", "--list", "-v"), git(self.repo, "worktree", "list"),
                sorted(str(p) for p in self.tmp.iterdir()))

    def refused(self, words, modules=("a",)):
        before = self.snapshot()
        res = start.prepare(self.repo, list(modules), "重开 a", short="shop")
        self.assertEqual(res.code, 3, res.lines)
        self.assertIn(words, " ".join(res.lines))
        self.assertEqual(self.snapshot(), before)
        return res


class ValidateReopenTest(ReopenCase):
    def test_old_branch_not_ancestor(self):
        sha = git(self.repo, "commit-tree", "HEAD^{tree}", "-p", "a", "-m", "side").strip()
        git(self.repo, "update-ref", "refs/heads/a", sha)
        self.refused("1 个提交没合进集成分支")

    def test_old_branch_checked_out(self):
        git(self.repo, "worktree", "add", "-q", str(self.tmp / "elsewhere"), "a")
        self.refused("正被别的 worktree 检出")

    def test_criteria(self):
        cases = [({"status": "done"}, "不是 in_progress"), ({"worktree": "/x/a"}, "已被 checkout"),
                 ({"progress": {"done": 4, "total": 4}}, "没有未勾的项"), ({"firstTickAt": None}, "以前没勾过")]
        for over, words in cases:
            with self.subTest(words):
                self.set_map(reopened_map(**over))
                self.refused(words)

    def test_old_session_still_in_use(self):
        with self.db.transaction(actor="t") as tx:
            tx.put("session", "shop-a", dev("a", str(self.tmp / "repo-crew" / "a")), action="registered")
        self.refused("旧会话 shop-a 还在用，先 merge cleanup a")


class PrepareReopenTest(ReopenCase):
    def test_fast_forward_and_register(self):
        res = start.prepare(self.repo, ["a"], "重开 a", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        main = git(self.repo, "rev-parse", "main").strip()
        self.assertEqual(git(self.repo, "rev-parse", "a").strip(), main)
        wt = self.tmp / "repo-crew" / "a"
        self.assertEqual(git(wt, "rev-parse", "--abbrev-ref", "HEAD").strip(), "a")
        rec = store.get(self.db, "session", "shop-a-r2")
        self.assertEqual(rec["reopen"], {"round": 2, "since": res.approval, "review": {"spec": "approved", "plan": "approved"}})
        self.assertEqual(rec["worktree"], str(wt))
        self.assertEqual(store.get(self.db, "item", str(res.approval))["reopened"], ["a"])
        text = " ".join(res.lines)
        self.assertIn("按重开处理（第 2 轮）", text)
        self.assertIn("旧分支已快进", text)
        self.assertEqual(res.prepared[0]["reopen"], {"round": 2, "branch": "fast-forward"})

    def test_no_old_branch_created(self):
        git(self.repo, "branch", "-D", "a")
        res = start.prepare(self.repo, ["a"], "重开 a", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        self.assertIn("从集成分支新切", " ".join(res.lines))
        self.assertEqual(res.prepared[0]["reopen"]["branch"], "created")

    def test_third_round_and_first_without_records(self):
        with self.db.transaction(actor="t") as tx:
            tx.put("session", "shop-a-r2", dev("a", "/tmp/r2", status="retired"), action="registered")
        res = start.prepare(self.repo, ["a"], "重开 a", short="shop")
        self.assertEqual(res.prepared[0]["relayName"], "shop-a-r3")

    def test_new_and_reopened_together(self):
        res = start.prepare(self.repo, ["a", "b"], "重开 a，开 b", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        b = store.get(self.db, "session", "shop-b")
        self.assertNotIn("reopen", b)
        self.assertNotIn("reopen", res.prepared[1])
        self.assertEqual(store.get(self.db, "item", str(res.approval))["reopened"], ["a"])
        self.assertNotIn("重开修订", store.read_body(self.db, res.prepared[1]["kickoff"]))

    def test_json_output(self):
        out = self.run_cli("start", "prepare", "a", "--original", "重开 a", "--project-short", "shop", "--json")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        doc = json.loads(out.stdout)
        self.assertEqual(doc["prepared"][0]["reopen"], {"round": 2, "branch": "fast-forward"})


class KickoffReopenTest(ReopenCase):
    def kickoff(self, review):
        self.set_map(reopened_map(review=review))
        res = start.prepare(self.repo, ["a"], "重开 a", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        return store.read_body(self.db, res.prepared[0]["kickoff"]).splitlines()

    def test_both_approved(self):
        lines = self.kickoff(("approved", "approved"))
        self.assertIn("这是重开修订（第 2 轮）：模块 a 已经做完过，spec-guard 已把它原地重开。只做 tasks/a/todo.md 里新加的未勾项，"
                      "已勾的不要重做；", lines)
        self.assertIn("plan.md 里新补的一节说明这次为什么返工。旧的模块分支已快进到集成分支 main，旧一轮的邮箱名已退役，不要用。", lines)
        self.assertIn("Spec 与 Plan 仍是批准状态（范围内返工）。先 module-crew sync，再从 tasks/a/todo.md 第一个未勾项开始构建，"
                      "不用等开工通知；做完发最终验收【交审】。", lines)
        self.assertNotIn("收到开工类【协调通知】之前不要开始构建。", lines)
        self.assertIn("邮箱名：shop-a-r2，用 agent-relay bridge_register 注册，wake: \"auto\"", lines)
        self.assertLess(lines.index(next(l for l in lines if l.startswith("这是重开修订"))),
                        lines.index(next(l for l in lines if l.startswith("Spec 与 Plan 仍是批准状态"))))

    def test_plan_pending(self):
        lines = self.kickoff(("approved", "pending"))
        self.assertIn("这一步只做：把 tasks/a/plan.md、todo.md 发【交审】（节点 Plan）；Plan 批准后收到开工类【协调通知】再构建。", lines)
        self.assertIn("收到开工类【协调通知】之前不要开始构建。", lines)
        self.assertTrue(any(l.startswith("这是重开修订") for l in lines))

    def test_spec_revised(self):
        lines = self.kickoff(("revised", "pending"))
        self.assertIn(start._first_step("a", "separate"), lines)
        self.assertIn("收到开工类【协调通知】之前不要开始构建。", lines)
        self.assertTrue(any(l.startswith("这是重开修订") for l in lines))

    def write_todo(self, *items):
        (self.repo / "tasks" / "a").mkdir(parents=True, exist_ok=True)
        (self.repo / "tasks" / "a" / "todo.md").write_text("# a\n\n- [x] T1：旧的一项\n" + "".join(f"{i}\n" for i in items),
                                                           encoding="utf-8")
        git(self.repo, "add", "tasks")
        git(self.repo, "commit", "-q", "-m", "reopen a")

    def test_first_new_item_revises_spec(self):
        # S45 (LIVE-SAAS backoffice-auth r2): Spec still approved, but the first new item is a Spec revision
        self.write_todo("- [ ] REV-SPEC：Spec 补登录失败锁定", "- [ ] T5：实现锁定")
        for review in (("approved", "pending"), ("approved", "approved")):
            lines = self.kickoff(review)
            self.assertNotIn("这一步只做：把 tasks/a/plan.md、todo.md 发【交审】（节点 Plan）；Plan 批准后收到开工类【协调通知】再构建。",
                             lines, review)
            self.assertFalse(any(l.startswith("Spec 与 Plan 仍是批准状态") for l in lines), review)
            self.assertIn("tasks/a/todo.md 新加的第一个未勾项是 Spec 修订（REV-SPEC：Spec 补登录失败锁定）："
                          "先改 spec/a.md，交 Spec 节点。", lines)
            self.assertIn(start._first_step("a", "separate"), lines)
            self.assertIn("收到开工类【协调通知】之前不要开始构建。", lines)
            git(self.repo, "worktree", "remove", "--force", str(self.tmp / "repo-crew" / "a"))
            with self.db.transaction(actor="t") as tx:
                tx.put("session", "shop-a-r2", dev("a", str(self.tmp / "repo-crew" / "a"), status="retired"),
                       action="retired")

    def test_first_new_item_not_spec(self):
        self.write_todo("- [ ] T5：实现锁定", "- [ ] REV-SPEC：之后再补 Spec")
        lines = self.kickoff(("approved", "pending"))
        self.assertIn("这一步只做：把 tasks/a/plan.md、todo.md 发【交审】（节点 Plan）；Plan 批准后收到开工类【协调通知】再构建。", lines)

    def test_created_branch_wording(self):
        git(self.repo, "branch", "-D", "a")
        lines = self.kickoff(("approved", "approved"))
        self.assertIn("plan.md 里新补的一节说明这次为什么返工。旧的模块分支不在了，已从集成分支 main 新切，旧一轮的邮箱名已退役，不要用。", lines)


class PlanReopenTest(ReopenCase):
    def test_not_proposed_reason_names_it(self):
        doc = reopened_map()
        doc["startable"] = {"modules": [], "conflicts": []}
        self.set_map(doc)
        p = start.plan(self.repo)
        self.assertEqual(p.modules, [])
        self.assertIn({"module": "a", "reason": "已重开（第 2 轮待开），要用户点名：start prepare a"}, p.reasons)

    def test_not_proposed_while_others_are(self):
        p = start.plan(self.repo)
        self.assertNotIn("a", [m["id"] for m in p.modules])


class CurrentRoundTest(ReopenCase):
    """Decision 4: after the reopen only items numbered above reopen.since count for module a."""

    def setUp(self):
        super().setUp()
        with self.db.transaction(actor="t") as tx:     # an earlier round: approved Spec, a returned final, a rework
            r = tx.allocate_number()
            tx.put("item", str(r), {"state": "closed", "kind": "review", "module": "a", "node": "spec",
                                    "from": "shop-a", "relayId": None}, action="added")
            tx.put("item", str(tx.allocate_number()), {"state": "closed", "kind": "review-approval", "reviews": [r],
                                                       "from": "coordinator", "relayId": None}, action="review-approved")
            tx.put("item", str(tx.allocate_number()), {"state": "closed", "kind": "merge-approval", "module": "a",
                                                       "closedReason": "returned", "from": "shop-a", "relayId": None},
                   action="returned")
            tx.put("item", str(r), {"state": "closed", "kind": "review", "module": "a", "node": "spec",
                                    "from": "shop-a", "relayId": None}, action="rework-sent",
                   data={"module": "a", "node": "spec"})

    def reopen(self, review=("approved", "approved")):
        self.set_map(reopened_map(review=review))
        res = start.prepare(self.repo, ["a"], "重开 a", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        return res

    def test_before_reopen_old_round_counts(self):
        self.assertIn("spec", review._approved_nodes(self.db).get("a", set()))
        self.assertEqual(len(stall.returns(store.events(self.db), store.records(self.db, "item"), "a")), 1)

    def test_slot_taken_and_not_merged(self):
        self.reopen()
        self.assertEqual(start.plan(self.repo).slots, start.DEFAULT_MAX - 1)
        self.assertNotIn("a", start._merged_modules(self.db))

    def test_stage_build_when_both_approved(self):
        self.reopen()
        items, sessions = store.records(self.db, "item"), store.records(self.db, "session")
        self.assertEqual(hooks._stage(items, "a", sessions), hooks.STAGE_BUILD)
        self.assertEqual(hooks._stage(items, "a"), hooks.STAGE_MERGED)      # without sessions: unchanged behaviour

    def test_stage_write_when_plan_pending(self):
        self.reopen(("approved", "pending"))
        items, sessions = store.records(self.db, "item"), store.records(self.db, "session")
        self.assertEqual(hooks._stage(items, "a", sessions), hooks.STAGE_WRITE)

    def test_sync_and_cleanup(self):
        self.reopen()
        with self.db.transaction(actor="t") as tx:
            self.assertNotIn("a", merge.no_sync(tx))
            self.assertIn(("shop-a-r2", None), merge.sync_targets(tx))
        res = merge.cleanup(self.repo, "a", "收回 a")
        self.assertEqual(res.code, 3, res.lines)
        self.assertIn("还没有合入", " ".join(res.lines))

    def test_review_history_only_this_round(self):
        self.reopen(("approved", "pending"))
        self.assertEqual(review._approved_nodes(self.db).get("a", set()), set())
        self.assertEqual(review._rounds(self.db, "a", "spec"), 0)
        sessions = store.records(self.db, "session")
        self.assertEqual(stall.returns(store.events(self.db), store.records(self.db, "item"), "a", sessions), [])


class EndToEndTest(MergeCase):
    """Acceptance 6: round 1 of b merged and cleaned up, then reopened, worked, approved, merged and cleaned up again."""

    def test_reopen_round_trip(self):
        db = store.open_store(self.repo)
        self.approve_final("b", 1)
        self.assertEqual(merge.run(self.repo, check_command="python3 -c pass").code, 0)
        self.assertEqual(merge.cleanup(self.repo, "b", "b 可以收回").code, 0)

        doc = copy.deepcopy(START_MAP)
        doc["modules"][1].update({"status": "in_progress", "worktree": None, "progress": {"done": 1, "total": 2},
                                  "firstTickAt": "2026-10-01T10:00:00+08:00",
                                  "review": {"spec": "approved", "plan": "approved"}})
        doc["startable"] = {"modules": [], "conflicts": []}
        self.set_map(doc)
        res = start.prepare(self.repo, ["b"], "重开 b", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        wt = res.prepared[0]["worktree"]
        self.assertEqual(git(wt, "rev-parse", "HEAD").strip(), git(self.repo, "rev-parse", "main").strip())
        hooks.bind(db, "shop-b-r2", "sid-b-r2", wt)
        self.assertEqual(store.get(db, "session", "shop-b-r2")["hostSession"]["sessionId"], "sid-b-r2")

        stage = lambda: hooks._stage(store.records(db, "item"), "b", store.records(db, "session"))
        self.assertEqual(stage(), hooks.STAGE_BUILD)
        refused = merge.cleanup(self.repo, "b", "收回 b")
        self.assertEqual(refused.code, 3, refused.lines)

        f = wt / "src" / "b2.py"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("VALUE = 'b2'\n", encoding="utf-8")
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", "b: revision")
        text = review_text("b", "最终验收", [("src/b2.py", f)]).replace(
            "要点：\n", "要点：\n验收结果：\n1：test_value 通过\n\n", 1) + "改动统计：1 file changed\n越界检查：无越界\n"
        out = review.add(db, text, "shop-b-r2", 2)
        self.assertEqual(out.code, 0, out.lines)
        self.assertTrue(stage().startswith("最终验收已交审"))
        merge.approve(db, out.number, "b 修订通过")
        self.assertEqual(stage(), hooks.STAGE_WAIT_MERGE)
        ran = merge.run(self.repo, check_command="python3 -c pass")
        self.assertEqual(ran.code, 0, ran.lines)
        self.assertTrue((self.repo / "src" / "b2.py").exists())
        self.assertEqual(stage(), hooks.STAGE_MERGED)

        done = merge.cleanup(self.repo, "b", "b 可以收回")
        self.assertEqual(done.code, 0, done.lines)
        self.assertEqual(store.get(db, "session", "shop-b-r2")["status"], "retired")
        self.assertIn("待退役的邮箱名：shop-b-r2", " ".join(done.lines))


class DocsTest(unittest.TestCase):
    """Acceptance 9: the coordinator skills (Claude and Codex), crew-dev and README describe the reopen."""

    def read(self, rel):
        from helpers import PLUGIN_ROOT
        return (PLUGIN_ROOT / rel).read_text(encoding="utf-8")

    def test_coordinator_skills(self):
        for rel in ("skills/crew-coordinator/SKILL.md", "codex-skills/crew-coordinator/SKILL.md"):
            with self.subTest(rel):
                text = self.read(rel)
                for words in ("重开已完成的模块", "返工与小模块", "merge cleanup <id>", "start prepare <id>",
                              "<简称>-<id>-r<轮次>", "不要 `reactivate`", "合进集成分支、换名保留、确认丢弃",
                              "点名重开就是开工批准"):
                    self.assertIn(words, text)

    def test_crew_dev(self):
        text = self.read("skills/crew-dev/SKILL.md")
        self.assertIn("只做 `tasks/<模块>/todo.md` 里新加的未勾项", text)

    def test_readme(self):
        text = self.read("docs/guide.md")   # crew-docs: moved to the guide, which carries no version labels
        self.assertIn("## 修订已完成的模块", text)
        self.assertIn("start prepare <模块 id>", text)


class FreshStoreRoundTest(StartCase):
    def test_round_two_without_records(self):
        self.set_map(reopened_map())
        res = start.prepare(self.repo, ["a"], "重开 a", short="shop")
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(res.prepared[0]["relayName"], "shop-a-r2")


if __name__ == "__main__":
    unittest.main()
