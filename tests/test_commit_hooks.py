"""module-crew's own commits under a project's commit hooks (frontend husky: commitlint + lint-staged)."""

import os
import re
import unittest

from helpers import MergeCase, git

from module_crew import changes, merge, review, store

CONVENTIONAL = re.compile(r"^[a-z]+(\([^)]+\))?: .+")
LINT = r"""#!/bin/sh
head -1 "$1" | grep -Eq '^[a-z]+(\([^)]+\))?: .+' || { echo "commitlint: subject may not be empty, type may not be empty" >&2; exit 1; }
"""
REJECT = """#!/bin/sh
echo "husky - commit-msg script failed (code 1)" >&2
exit 1
"""


class HookCase(MergeCase):
    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def hook(self, body):
        path = self.repo / ".git" / "hooks" / "commit-msg"
        path.write_text(body, encoding="utf-8")
        os.chmod(path, 0o755)

    def subjects(self, since):
        return git(self.repo, "log", "--format=%s", f"{since}..HEAD").strip().splitlines()


class ConventionalMessagesTest(HookCase):
    def test_all_crew_commits_pass_commitlint(self):
        start = git(self.repo, "rev-parse", "HEAD").strip()
        s = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        p = review.add(self.db, self.plan_review("b"), "shop-b", 2).number
        self.hook(LINT)
        self.assertEqual(review.approve(self.repo, [s, p], "批").code, 0)
        n = changes.add(self.db, "【公共变更请求】\n结束：无\n来自：b\n文件：\ntsconfig.base.json\n改什么：" + "很长的说明" * 20
                        + "\n为什么：模块需要\n是否完全停住：否\n", "shop-b", 3).number
        (self.repo / "tsconfig.base.json").write_text("{}\n")
        self.assertEqual(changes.land(self.repo, n).code, 0)
        git(self.wt["b"], "merge", "-q", "-X", "theirs", "-m", "chore: 同步集成基线", "main")   # hooks are shared by worktrees
        self.approve_final("b", 4)
        res = merge.run(self.repo, check_command="python3 -c pass")
        self.assertEqual(res.code, 0, res.lines)
        subjects = [x for x in self.subjects(start) if not x.startswith(("b: ", "chore: "))]
        self.assertGreaterEqual(len(subjects), 3)            # approve, land, merge (tick: test_merge_pilot)
        for line in subjects:
            self.assertRegex(line, CONVENTIONAL)
            self.assertLessEqual(len(line), 100)


class HookRejectionTest(HookCase):
    def test_merge_rejected_by_hook_is_not_a_conflict(self):
        n = self.approve_final("b", 1)
        head = git(self.repo, "rev-parse", "HEAD").strip()
        self.hook(REJECT)
        res = merge.run(self.repo, check_command="python3 -c pass")
        self.assertEqual(res.code, 4, res.lines)
        text = "\n".join(res.lines)
        self.assertIn("提交钩子拒绝", text)
        self.assertNotIn("冲突", text)
        self.assertEqual(res.sends, [])                      # the module is not sent back
        self.assertEqual(git(self.repo, "rev-parse", "HEAD").strip(), head)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        self.assertEqual(store.get(self.db, "item", str(n))["state"], "open")

    def test_approve_and_land_rejected(self):
        s = review.add(self.db, self.spec_review("b"), "shop-b", 1).number
        self.hook(REJECT)
        res = review.approve(self.repo, [s], "批")
        self.assertEqual(res.code, 4)
        self.assertIn("提交钩子拒绝", "\n".join(res.lines))
        n = changes.add(self.db, "【公共变更请求】\n结束：无\n来自：b\n文件：\nx.json\n改什么：改\n为什么：要\n"
                        "是否完全停住：否\n", "shop-b", 2).number
        git(self.repo, "reset", "-q", "--hard")
        (self.repo / "x.json").write_text("{}\n")
        out = changes.land(self.repo, n)
        self.assertEqual(out.code, 4)
        self.assertIn("提交钩子拒绝", "\n".join(out.lines))
        self.assertEqual(store.get(self.db, "request", str(n))["state"], "open")


if __name__ == "__main__":
    unittest.main()
