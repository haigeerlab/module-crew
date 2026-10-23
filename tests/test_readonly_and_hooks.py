"""S19: the commands the Codex coordinator skill runs inside the sandbox never write .git.
S21: a refused commit or merge reports the hook's exit code and last lines, not just its first line (a pnpm banner)."""

import hashlib
import json
import os
import re
import stat
import unittest
from pathlib import Path

from helpers import PLUGIN_ROOT, MergeCase, ReviewCase, git

from module_crew import changes, merge, review, store

FAKE_OVERLAP = '''import json, sys
print(json.dumps({"conflicts": [], "errors": []}))
'''

PNPM_REJECT = """#!/bin/sh
echo "Scope: all 33 workspace projects" >&2
echo "src/a.ts(3,1): error TS2304: Cannot find name 'foo'." >&2
exit 1
"""

SKILL = PLUGIN_ROOT / "codex-skills" / "crew-coordinator" / "SKILL.md"
EXTRA = {("review", "show"): ["C1"], ("task", "show"): ["T1"], ("source", "map"): ["C1"]}


def sandbox_commands() -> list[list[str]]:
    """The commands the skill's 「只读的在沙箱里跑」 line lists, expanded: `merge queue|result` → two commands."""
    line = next(x for x in SKILL.read_text(encoding="utf-8").splitlines() if "只读的在沙箱里跑" in x)
    out = []
    for token in re.findall(r"`([^`]+)`", line):
        if token.startswith("-"):
            continue
        head, _, rest = token.partition(" ")
        for sub in (rest.split("|") if rest else [""]):
            argv = [head] + ([sub] if sub else [])
            out.append(argv + EXTRA.get(tuple(argv), []))
    return out


def snapshot(root: Path) -> dict:
    return {str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "dir")
            for p in sorted(root.rglob("*")) if not p.is_symlink()}


def set_writable(root: Path, writable: bool) -> None:
    for p in [root, *root.rglob("*")]:
        if p.is_symlink():
            continue
        mode = p.stat().st_mode
        p.chmod(mode | stat.S_IWUSR if writable else mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


class ReadOnlyGitTest(ReviewCase):
    """Codex's default sandbox refuses writes under .git (LIVE-SAAS frontend, S19)."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        root = Path(self.plugins.entries["spec-guard@m"][-1]["installPath"])
        doc = json.loads((root / "interface.json").read_text())
        doc["interface"] = "1.10"
        doc["scopeOverlap"] = {"command": ["python3", "-B", "hooks/module_scope.py", "overlap", "--project",
                                           "<project-root>", "--spec", "<module-id>=<spec-file>"]}
        (root / "interface.json").write_text(json.dumps(doc))
        (root / "hooks" / "module_scope.py").write_text(FAKE_OVERLAP)
        for m, rid in (("b", 1), ("c", 2)):
            assert review.add(self.db, self.spec_review(m), f"shop-{m}", rid).code == 0
        # the two first-time writes: an older project with no remembered integration head, and a detached merge
        # that ended and was never read
        with self.db.transaction(actor="test") as tx:
            cfg = tx.get("config", "main") or {}
            cfg.pop("integrationSeen", None)
            tx.put("config", "main", cfg, action="test")
        log = self.tmp / "merge.log"
        log.write_text("合并完成\n", encoding="utf-8")
        (self.db.path / "merge-running.json").write_text(json.dumps(
            {"approval": 9, "unit": "b", "detached": True, "exitCode": 0, "log": str(log), "resultRead": False}))
        self.message = self.tmp / "msg.txt"
        self.message.write_text("【已恢复】\n结束：W1\n", encoding="utf-8")

    def test_sandbox_commands_do_not_write_git(self):
        commands = sandbox_commands()
        self.assertIn(["review", "batch"], commands)
        git_dir = self.repo / ".git"
        before = snapshot(git_dir)
        set_writable(git_dir, False)
        self.addCleanup(set_writable, git_dir, True)
        for argv in commands:
            args = argv + ([str(self.message)] if argv == ["protocol", "check"] else [])
            ran = self.run_cli(*args)
            text = ran.stdout + ran.stderr
            self.assertNotIn("Traceback", text, args)
            if argv != ["host-check"]:            # host-check probes .git on purpose and reports the refusal
                self.assertNotIn("Permission denied", text, args)
            if argv == ["review", "batch"]:
                self.assertIn("并行边界重叠：无（已按交审中的 Spec 比对）", ran.stdout)   # the comparison really ran
        set_writable(git_dir, True)
        self.assertEqual(snapshot(git_dir), before)


class HookTailTest(MergeCase):
    """A pnpm banner as the hook's first line must not hide the real error (S21)."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)

    def hook(self):
        path = self.repo / ".git" / "hooks" / "commit-msg"
        path.write_text(PNPM_REJECT, encoding="utf-8")
        os.chmod(path, 0o755)

    def assert_real_error(self, lines):
        text = "\n".join(lines)
        self.assertIn("提交钩子拒绝：Scope: all 33 workspace projects", text)
        self.assertIn("提交钩子：退出码 1", text)
        self.assertIn("error TS2304", text)

    def test_review_approve_reports_hook_tail_and_how_to_handle_new_files(self):
        p = review.add(self.db, self.plan_review("b"), "shop-b", 1).number
        self.hook()
        res = review.approve(self.repo, [p], "批准 b 的 Plan")
        self.assertEqual(res.code, 4)
        self.assert_real_error(res.lines)
        text = "\n".join(res.lines)
        self.assertIn("tasks/b/plan.md", text)
        self.assertIn("review approve", text.split("tasks/b/plan.md", 1)[1])   # says what to do with the kept files

    def test_change_land_reports_hook_tail(self):
        n = changes.add(self.db, "【公共变更请求】\n结束：无\n来自：b\n文件：\nx.json\n改什么：改\n为什么：要\n"
                        "是否完全停住：否\n", "shop-b", 2).number
        (self.repo / "x.json").write_text("{}\n")
        self.hook()
        res = changes.land(self.repo, n)
        self.assertEqual(res.code, 4)
        self.assert_real_error(res.lines)

    def test_merge_commit_refused_reports_hook_tail(self):
        self.approve_final("b", 3)
        self.hook()
        res = merge.run(self.repo, check_command="python3 -c pass")
        self.assertEqual(res.code, 4, res.lines)
        self.assert_real_error(res.lines)


if __name__ == "__main__":
    unittest.main()
