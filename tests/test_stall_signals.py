"""crew-stall-signals: read-only facts in sessions --json for the decision inbox (spec/crew-stall-signals.md)."""

import shutil
import unittest
from datetime import datetime

from helpers import MergeCase, git

from module_crew import failure, hooks, inbox, merge, review, store

from helpers import wait_user


class StallCase(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def rows(self):
        return {r["module"]: r for r in failure.sessions(self.db)}


class CommitFactsTest(StallCase):
    def test_commits_ahead_of_the_integration_branch(self):
        row = self.rows()["b"]
        self.assertEqual(row["commits"]["ahead"], 1)
        self.assertEqual(row["commits"]["last"]["commit"], git(self.wt["b"], "rev-parse", "HEAD").strip())
        self.assertEqual(row["commits"]["last"]["at"], git(self.wt["b"], "log", "-1", "--format=%cI").strip())
        datetime.fromisoformat(row["commits"]["last"]["at"])
        self.assertIsNone(row["commits"]["error"])
        (self.wt["b"] / "x.txt").write_text("x\n")
        git(self.wt["b"], "add", "x.txt")
        git(self.wt["b"], "commit", "-q", "-m", "b: more")
        self.assertEqual(self.rows()["b"]["commits"]["ahead"], 2)

    def test_no_commit_since_start(self):
        git(self.wt["b"], "reset", "-q", "--hard", "main")
        self.assertEqual(self.rows()["b"]["commits"], {"ahead": 0, "last": None, "error": None})

    def test_missing_worktree_only_affects_that_module(self):
        shutil.rmtree(self.wt["c"])
        rows = self.rows()
        self.assertEqual((rows["c"]["commits"]["ahead"], rows["c"]["commits"]["last"]), (None, None))
        self.assertIn("worktree", rows["c"]["commits"]["error"])
        self.assertEqual(rows["b"]["commits"]["ahead"], 1)
        out = self.run_cli("sessions", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_missing_integration_branch(self):
        with self.db.transaction(actor="test") as tx:
            tx.put("config", "main", dict(tx.get("config", "main"), integrationBranch="nope"), action="set")
        commits = self.rows()["b"]["commits"]
        self.assertEqual((commits["ahead"], commits["last"]), (None, None))
        self.assertTrue(commits["error"])


class StartedAtTest(StallCase):
    def test_started_at_is_the_registration_time_and_survives_takeover(self):
        reg = [e for e in store.events(self.db, key="shop-b") if e["type"] == "session.registered"][-1]
        self.assertEqual(self.rows()["b"]["startedAt"], reg["at"])
        hooks.takeover(self.db, "shop-b", "让新会话接管 b")
        self.assertEqual(self.rows()["b"]["startedAt"], reg["at"])


class AsksTest(StallCase):
    def test_only_reviews_that_reached_the_user_count(self):
        never = review.add(self.db, self.spec_review("b"), "shop-b", 7001).number
        hub = review.add(self.db, self.spec_review("b"), "shop-b", 7002).number      # supersedes `never`
        self.assertEqual(store.get(self.db, "item", str(never))["closedReason"], "superseded")
        review.for_hub(self.repo)
        review.answer(self.db, hub, "Spec 再改一下")                               # same review: still one ask
        direct = review.add(self.db, self.spec_review("b"), "shop-b", 7003).number
        review.answer(self.db, direct, "Spec 还要改")                              # no decision inbox: answered counts
        asks = self.rows()["b"]["asks"]
        self.assertEqual([(a["node"], a["count"], a["refs"]) for a in asks], [("spec", 2, [f"C{hub}", f"C{direct}"])])
        answered = store.get(self.db, "item", str(direct))["answer"]["answeredAt"]
        self.assertEqual(asks[0]["lastAt"], answered)
        hub_at = store.get(self.db, "item", str(hub))["answer"]["answeredAt"]   # answered after its hub batch
        self.assertEqual(asks[0]["ats"], [hub_at, answered])
        self.assertEqual(self.rows()["c"]["asks"], [])

    def test_node_order(self):
        plan = review.add(self.db, self.plan_review("b"), "shop-b", 7101).number
        review.answer(self.db, plan, "Plan 改")
        spec = review.add(self.db, self.spec_review("b"), "shop-b", 7102).number
        review.answer(self.db, spec, "Spec 改")
        self.assertEqual([a["node"] for a in self.rows()["b"]["asks"]], ["spec", "plan"])

    def test_ats_is_the_hub_batch_time_when_not_answered(self):
        n = review.add(self.db, self.spec_review("b"), "shop-b", 7401).number
        review.for_hub(self.repo)
        batch = [k for k, v in store.records(self.db, "item").items() if v.get("kind") == "hub-batch"][-1]
        at = [e["at"] for e in store.events(self.db, key=batch) if e["type"] == "item.hub-batch"][0]
        ask = self.rows()["b"]["asks"][0]
        self.assertEqual((ask["refs"], ask["ats"], ask["lastAt"]), ([f"C{n}"], [at], at))


class ReturnsTest(StallCase):
    def test_merge_returns_and_the_resubmission_counts_again(self):
        first = self.approve_final("b", 8001)
        res = merge.run(self.repo, self.check_script(fail_if="src/b.py"))
        self.assertEqual(store.get(self.db, "item", str(first))["closedReason"], "returned")
        row = self.rows()["b"]
        self.assertEqual([(r["ref"], r["returnKind"]) for r in row["returns"]], [(f"C{first}", "module")])
        datetime.fromisoformat(row["returns"][0]["at"])
        self.approve_final("b", 8002, path="src/b2.py")
        final = [a for a in self.rows()["b"]["asks"] if a["node"] == "final"][0]
        self.assertEqual(final["count"], 2)
        self.assertIsNotNone(res)


class WaitUserTest(StallCase):
    def test_lists_every_wait_user_with_its_first_line(self):
        old = inbox.add(self.db, wait_user(decide="要不要再试一次\n第二行", sender="shop-b"), "shop-b", 900).number
        new = inbox.add(self.db, wait_user(decide="换个做法", sender="shop-b"), "shop-b", 901).number
        rows = self.rows()
        got = [(w["ref"], w["state"], w["closedReason"], w["decide"]) for w in rows["b"]["waitUser"]]
        self.assertEqual(got, [(f"C{old}", "closed", "superseded", "要不要再试一次"), (f"C{new}", "open", None, "换个做法")])
        datetime.fromisoformat(rows["b"]["waitUser"][0]["at"])
        self.assertEqual(rows["c"]["waitUser"], [])
        self.assertEqual(rows["c"]["returns"], [])


class HumanTextTest(StallCase):
    def test_sessions_text(self):
        plan = review.add(self.db, self.plan_review("b"), "shop-b", 7201).number
        review.answer(self.db, plan, "Plan 改")
        git(self.wt["c"], "reset", "-q", "--hard", "main")
        text = "\n".join(failure.render_sessions(failure.sessions(self.db)))
        at = datetime.fromisoformat(git(self.wt["b"], "log", "-1", "--format=%cI").strip()).strftime("%Y-%m-%d %H:%M")
        self.assertIn(f"  最近提交：{at}（0 分钟前），开工以来 1 个提交", text)
        self.assertIn(f"  问过你：Plan 1 次（C{plan}）", text)
        self.assertIn("  最近提交：开工以来没有提交（开工 0 分钟前）", text)
        self.assertIn("  问过你：无", text)
        for word in ("停下", "卡住", "超时", "异常"):
            self.assertNotIn(word, text)

    def test_sessions_text_when_git_is_unreadable_and_after_a_return(self):
        first = self.approve_final("b", 8101)
        merge.run(self.repo, self.check_script(fail_if="src/b.py"))
        shutil.rmtree(self.wt["c"])
        text = "\n".join(failure.render_sessions(failure.sessions(self.db)))
        self.assertIn(f"  问过你：最终验收 1 次（C{store.get(self.db, 'item', str(first))['review']}）；合并退回 1 次", text)
        self.assertIn("  最近提交读不到：worktree 不存在", text)

    def test_status_module_lines(self):
        plan = review.add(self.db, self.plan_review("b"), "shop-b", 7301).number
        review.answer(self.db, plan, "Plan 改")
        out = self.run_cli("status").stdout
        line_b = next(l for l in out.splitlines() if l.startswith("  shop-b"))
        line_c = next(l for l in out.splitlines() if l.startswith("  shop-c"))
        self.assertIn("最近提交 0 分钟前", line_b)
        self.assertIn("同一节点最多问过你 1 次", line_b)
        self.assertIn("最近提交 0 分钟前", line_c)
        self.assertNotIn("问过你", line_c)


if __name__ == "__main__":
    unittest.main()
