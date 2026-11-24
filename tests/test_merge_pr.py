"""merge pr-merge / pr-check (crew-merge decisions 12, 13; acceptance 26-29): a fake gh answers by scenario."""
import json
import os
import sys
import unittest

from helpers import MergeCase, git

from module_crew import merge, store

PR = "https://github.com/acme/shop/pull/7"

FAKE_GH = """#!{python}
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
with open(os.environ["FAKE_GH_SCENARIO"]) as f:
    s = json.load(f)
def out(v):
    print(v if isinstance(v, str) else json.dumps(v))
    sys.exit(0)
if args[:2] == ["pr", "view"]:
    views = s["views"]
    n = int(s.get("_viewed", 0))
    s["_viewed"] = n + 1
    with open(os.environ["FAKE_GH_SCENARIO"], "w") as f:
        json.dump(s, f)
    out(views[min(n, len(views) - 1)])
if args[:2] == ["pr", "merge"]:
    if s.get("mergeFails"):
        print("GraphQL: Auto merge is not allowed for this repository", file=sys.stderr)
        sys.exit(1)
    # what GitHub does once auto-merge is on: later views come from afterMerge
    s["views"] = s.get("afterMerge", s["views"])
    s["_viewed"] = 0
    with open(os.environ["FAKE_GH_SCENARIO"], "w") as f:
        json.dump(s, f)
    sys.exit(0)
if args[0] == "api":
    path = args[1]
    if path.endswith("/protection/required_status_checks"):
        if s.get("classic") is None:
            print('{{"message":"Branch not protected"}}')
            print("gh: Branch not protected (HTTP 404)", file=sys.stderr)
            sys.exit(1)
        out(s["classic"])
    if "/rules/branches/" in path:
        out(s.get("rules", []))
    out({{"allow_auto_merge": s.get("autoMerge", True)}})
sys.exit(2)
"""


def view(state="OPEN", head=None, base="main", auto=None, merge_commit=None, merge_state=None):
    return {"state": state, "baseRefName": base, "headRefOid": head, "autoMergeRequest": auto,
            "mergeStateStatus": merge_state,
            "mergeCommit": {"oid": merge_commit} if merge_commit else None,
            "mergedAt": "2026-11-24T10:00:00Z" if merge_commit else None}


class PrCase(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        self.head = git(self.repo, "rev-parse", "main").strip()
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(FAKE_GH.format(python=sys.executable))
        gh.chmod(0o755)
        self.log = self.tmp / "gh-log.jsonl"
        self.scenario = self.tmp / "gh-scenario.json"
        for k, v in (("MODULE_CREW_GH", str(gh)), ("FAKE_GH_LOG", str(self.log)),
                     ("FAKE_GH_SCENARIO", str(self.scenario)), (merge.PR_POLL_ENV, "0.01")):
            os.environ[k] = v
            self.addCleanup(os.environ.pop, k, None)
        with self.db.transaction(actor="coordinator") as tx:
            self.n = tx.allocate_number()
            tx.put("item", str(self.n), {"state": "closed", "kind": "push", "closedReason": "pushed",
                                         "remoteBranch": f"crew/batch-{self.n}", "base": "main", "head": self.head,
                                         "commits": [f"{self.head[:7]} 合并"], "mergeCommits": [], "pr": PR,
                                         "answer": {"original": "推吧"}}, action="pushed")

    def scene(self, **kw):
        kw.setdefault("views", [view(head=self.head)])
        kw.setdefault("classic", {"contexts": ["CI required"], "checks": [{"context": "CI required"}]})
        self.scenario.write_text(json.dumps(kw))

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def merge_calls(self):
        return [c for c in self.calls() if c[:2] == ["pr", "merge"]]

    def rec(self):
        return store.get(self.db, "item", str(self.n))


class PrMergeTest(PrCase):
    def test_orders_auto_merge_and_records_request(self):       # acceptance 26
        self.scene(afterMerge=[view(head=self.head, auto={"enabledAt": "x"})])
        res = merge.pr_merge(self.repo, self.n, "合并")
        self.assertEqual(res.code, 6, res.lines)
        [call] = self.merge_calls()
        self.assertEqual(call, ["pr", "merge", PR, "--auto", "--merge", "--match-head-commit", self.head])
        for bad in ("--admin", "--squash", "--rebase", "--delete-branch"):
            self.assertNotIn(bad, call)
        self.assertEqual(self.rec()["mergeRequest"]["original"], "合并")
        self.assertEqual(self.rec()["mergeRequest"]["headCommit"], self.head)
        self.assertIn("CI required", "\n".join(res.lines))

    def test_clean_merges_directly(self):                      # standard v1.5.1
        self.scene(views=[view(head=self.head, merge_state="CLEAN")],
                   afterMerge=[view(state="MERGED", head=self.head, merge_commit="abc1234def")])
        res = merge.pr_merge(self.repo, self.n, "合并")
        self.assertEqual(res.code, 0, res.lines)
        [call] = self.merge_calls()
        self.assertEqual(call, ["pr", "merge", PR, "--merge", "--match-head-commit", self.head])
        self.assertEqual(self.rec()["mergeRequest"]["mode"], "direct")
        self.assertEqual(self.rec()["merged"]["mergeCommit"], "abc1234def")
        self.assertIn("已直接合并", "\n".join(res.lines))

    def test_checks_not_done_still_auto(self):                 # standard v1.5.1
        for state in ("BLOCKED", "UNKNOWN"):
            with self.subTest(state=state):
                self.log.unlink(missing_ok=True)
                self.scene(views=[view(head=self.head, merge_state=state)],
                           afterMerge=[view(head=self.head, auto={"enabledAt": "x"}, merge_state=state)])
                res = merge.pr_merge(self.repo, self.n, "合并")
                self.assertEqual(res.code, 6, res.lines)
                [call] = self.merge_calls()
                self.assertEqual(call, ["pr", "merge", PR, "--auto", "--merge", "--match-head-commit", self.head])
                self.assertEqual(self.rec()["mergeRequest"]["mode"], "auto")

    def test_merged_right_away(self):                          # acceptance 26
        self.scene(afterMerge=[view(state="MERGED", head=self.head, merge_commit="abc1234def")])
        res = merge.pr_merge(self.repo, self.n, "合并")
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(self.rec()["merged"]["mergeCommit"], "abc1234def")

    def assert_refused(self, original="合并"):
        before = self.rec()
        res = merge.pr_merge(self.repo, self.n, original)
        self.assertEqual(res.code, 3, res.lines)
        self.assertEqual(self.merge_calls(), [])
        self.assertEqual(self.rec(), before)
        return "\n".join(res.lines)

    def test_refusals(self):                                   # acceptance 27
        self.scene()
        self.assert_refused("  ")
        self.scene(autoMerge=False)
        self.assertIn("Allow auto-merge", self.assert_refused())
        self.scene(classic=None, rules=[{"type": "deletion"}])
        self.assertIn("必需检查", self.assert_refused())
        self.scene(views=[view(head="f" * 40)])
        self.assertIn("头提交", self.assert_refused())
        self.scene(views=[view(head=self.head, base="release")])
        self.assert_refused()
        self.scene(views=[view(state="CLOSED", head=self.head)])
        self.assert_refused()

    def test_no_gh_or_not_github(self):                        # acceptance 27
        self.scene()
        os.environ["MODULE_CREW_GH"] = ""
        self.assert_refused()
        os.environ["MODULE_CREW_GH"] = str(self.tmp / "bin" / "gh")
        with self.db.transaction(actor="coordinator") as tx:
            tx.put("item", str(self.n), dict(self.rec(), pr="https://gitlab.example/acme/shop/-/merge_requests/7"),
                   action="pr-opened")
        self.assertIn("GitHub", self.assert_refused())
        self.assertEqual(self.calls(), [])

    def test_not_a_push_record(self):
        self.scene()
        self.assertEqual(merge.pr_merge(self.repo, 9999, "合并").code, 3)
        with self.db.transaction(actor="coordinator") as tx:
            tx.put("item", str(self.n), dict(self.rec(), pr=None), action="pr-opened")
        self.assert_refused()

    def test_already_merged_records_without_ordering(self):    # acceptance 27
        self.scene(views=[view(state="MERGED", head=self.head, merge_commit="0417770ad7")])
        res = merge.pr_merge(self.repo, self.n, "合并")
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(self.merge_calls(), [])
        self.assertEqual(self.rec()["merged"]["mergeCommit"], "0417770ad7")

    def test_required_checks_from_either_place(self):          # acceptance 28
        self.scene(classic=None, rules=[{"type": "required_status_checks", "parameters": {
            "required_status_checks": [{"context": "CI required", "integration_id": 1}]}}],
            afterMerge=[view(head=self.head, auto={"enabledAt": "x"})])
        res = merge.pr_merge(self.repo, self.n, "合并")
        self.assertEqual(res.code, 6, res.lines)
        self.assertIn("CI required", "\n".join(res.lines))
        self.log.unlink()
        self.scene(classic={"contexts": ["test (3.9)"], "checks": []}, rules=[],
                   afterMerge=[view(head=self.head, auto={"enabledAt": "x"})])
        res = merge.pr_merge(self.repo, self.n, "合并")
        self.assertEqual(res.code, 6, res.lines)
        self.assertIn("test (3.9)", "\n".join(res.lines))

    def test_gh_merge_fails(self):
        self.scene(mergeFails=True)
        res = merge.pr_merge(self.repo, self.n, "合并")
        self.assertEqual(res.code, 4, res.lines)
        self.assertIn("Auto merge is not allowed", self.rec()["mergeRequest"]["error"])

    def test_old_record_without_head_uses_first_commit(self):
        with self.db.transaction(actor="coordinator") as tx:
            rec = dict(self.rec())
            rec.pop("head")
            tx.put("item", str(self.n), rec, action="pushed")
        self.scene(afterMerge=[view(head=self.head, auto={"enabledAt": "x"})])
        self.assertEqual(merge.pr_merge(self.repo, self.n, "合并").code, 6)


class PrCheckTest(PrCase):                                    # acceptance 29
    def test_merged(self):
        self.scene(views=[view(state="MERGED", head=self.head, merge_commit="0417770ad7")])
        res = merge.pr_check(self.repo, self.n)
        self.assertEqual(res.code, 0, res.lines)
        self.assertIn("0417770ad7", "\n".join(res.lines))
        self.assertIn("快进", "\n".join(res.lines))
        self.assertEqual(self.rec()["merged"]["mergeCommit"], "0417770ad7")
        self.assertEqual(self.merge_calls(), [])

    def test_queued_withdrawn_closed(self):
        self.scene(views=[view(head=self.head, auto={"enabledAt": "x"})])
        self.assertEqual(merge.pr_check(self.repo, self.n).code, 6)
        self.scene(views=[view(head=self.head)])
        self.assertEqual(merge.pr_check(self.repo, self.n).code, 4)
        self.scene(views=[view(state="CLOSED", head=self.head)])
        self.assertEqual(merge.pr_check(self.repo, self.n).code, 4)
        self.assertNotIn("merged", self.rec())

    def test_wait_returns_when_merged(self):
        queued = view(head=self.head, auto={"enabledAt": "x"})
        self.scene(views=[queued, queued, view(state="MERGED", head=self.head, merge_commit="abc1234")])
        res = merge.pr_check(self.repo, self.n, wait=30)
        self.assertEqual(res.code, 0, res.lines)
        self.assertEqual(len([c for c in self.calls() if c[:2] == ["pr", "view"]]), 3)

    def test_wait_runs_out(self):
        self.scene(views=[view(head=self.head, auto={"enabledAt": "x"})])
        self.assertEqual(merge.pr_check(self.repo, self.n, wait=0.05).code, 6)

    def test_refused(self):
        self.scene()
        self.assertEqual(merge.pr_check(self.repo, 9999).code, 3)
        os.environ["MODULE_CREW_GH"] = ""
        self.assertEqual(merge.pr_check(self.repo, self.n).code, 3)


class PrCliTest(PrCase):
    def test_cli(self):
        self.scene(afterMerge=[view(state="MERGED", head=self.head, merge_commit="abc1234")])
        words = self.tmp / "words.txt"
        words.write_text("合并")
        done = self.run_cli("merge", "pr-merge", f"C{self.n}", "--original-file", str(words))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("abc1234", done.stdout)
        done = self.run_cli("merge", "pr-check", f"C{self.n}")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.run_cli("merge", "pr-merge", f"C{self.n}").returncode, 2)   # argparse: words required


if __name__ == "__main__":
    unittest.main()
