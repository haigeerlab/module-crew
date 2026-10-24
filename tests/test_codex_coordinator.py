"""crew-codex-coordinator: the module coordinator running in Codex desktop (see the Spec)."""

import io
import json
import os
import re
import signal
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from helpers import MergeCase, git, spec_guard_interface
from test_host_handover import GapCase, close_batch
from test_light_task import new_task
from test_session_handover import WRITES

from module_crew import __main__ as cli
from module_crew import handover, hooks, merge, mergelock, probe, store

SESSION_VARS = ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")


class CodexCoordCase(MergeCase):
    """MergeCase whose coordinator shop-coord was handed over to Codex and is bound to thread `thread-coord`."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        with self.db.transaction(actor="t") as tx:
            rec = tx.get("session", "shop-coord")
            tx.put("session", "shop-coord", {
                **rec, "host": "codex-desktop", "hostSession": hooks.identity("thread-coord", ""),
                "hostHandover": {"from": "claude-desktop", "to": "codex-desktop", "at": store.now(),
                                 "original": "换到 Codex", "pending": False}}, action="registered")

    def env(self, codex: str | None = None, claude: str | None = None) -> dict:
        env = {k: v for k, v in os.environ.items() if k not in SESSION_VARS}
        if codex:
            env["CODEX_THREAD_ID"] = codex
        if claude:
            env["CLAUDE_CODE_SESSION_ID"] = claude
        return env

    def cli(self, *args, codex: str | None = "thread-coord", claude: str | None = None, cwd=None):
        return self.run_cli(*args, env=self.env(codex, claude), cwd=cwd)


class StatusCodexSelfTest(CodexCoordCase):
    """Acceptance 7: with no hook to say who it is, `status` tells a Codex thread whether it is the coordinator."""

    def test_registered_thread_is_told_it_is_the_coordinator(self):
        out = self.cli("status").stdout
        self.assertEqual(out.splitlines()[0], "本会话是模块协调 shop-coord（Codex）：没有钩子，以下按状态库为准")
        doc = json.loads(self.cli("status", "--json").stdout)
        self.assertEqual(doc["store"]["codexSelf"], {"name": "shop-coord", "registered": True})

    def test_other_thread_is_told_it_is_not(self):
        out = self.cli("status", codex="thread-other").stdout
        self.assertEqual(out.splitlines()[0], "本线程不是登记的模块协调，不要按模块协调行事")
        doc = json.loads(self.cli("status", "--json", codex="thread-other").stdout)
        self.assertEqual(doc["store"]["codexSelf"], {"name": "shop-coord", "registered": False})

    def test_codex_host_line(self):
        self.assertIn("模块协调：Codex 桌面版；模块会话：Codex 桌面版", self.cli("status").stdout)

    def test_claude_output_unchanged(self):
        """Without CODEX_THREAD_ID nothing is added (a Claude conversation, or the user's own terminal)."""
        for claude in (None, "sid-x"):
            with self.subTest(claude=claude):
                out = self.cli("status", codex=None, claude=claude).stdout
                self.assertTrue(out.startswith("体检\n"))
                self.assertNotIn("Codex）：没有钩子", out)
                doc = json.loads(self.cli("status", "--json", codex=None, claude=claude).stdout)
                self.assertIsNone(doc["store"]["codexSelf"])

    def test_claude_session_wins_over_codex_variable(self):
        """A Claude conversation that inherited CODEX_THREAD_ID is still Claude (hooks.own_host)."""
        out = self.cli("status", codex="thread-coord", claude="sid-x").stdout
        self.assertTrue(out.startswith("体检\n"))


class HostCheckCoordinatorTest(CodexCoordCase):
    """Acceptance 6: `host-check` in the integration checkout checks what the coordinator needs."""

    def check(self, *args):
        return self.cli("host-check", *args)

    def test_all_pass(self):
        r = self.check("--json")
        self.assertEqual(r.returncode, 0, r.stdout)
        doc = json.loads(r.stdout)
        self.assertEqual(doc["role"], "coordinator")
        self.assertEqual({c["id"] for c in doc["checks"]},
                         {"store", "registered", "version", "git-writable", "spec-guard", "entry"})
        self.assertTrue(all(c["ok"] for c in doc["checks"]), doc["checks"])

    def test_git_common_dir_read_only(self):
        gitdir = self.repo / ".git"
        mode = gitdir.stat().st_mode
        gitdir.chmod(0o555)
        self.addCleanup(gitdir.chmod, mode)
        r = self.check("--json")
        self.assertEqual(r.returncode, 3)
        bad = {c["id"]: c for c in json.loads(r.stdout)["checks"] if not c["ok"]}
        self.assertEqual(set(bad), {"git-writable"})
        self.assertIn("沙箱外运行", bad["git-writable"]["fix"])

    def test_spec_guard_missing(self):
        self.plugins.entries.pop("spec-guard@m")
        self.plugins.write()
        bad = {c["id"] for c in json.loads(self.check("--json").stdout)["checks"] if not c["ok"]}
        self.assertEqual(bad, {"spec-guard"})

    def test_module_worktree_unchanged(self):
        """A module worktree keeps the module-session checks, now with role 'dev'."""
        doc = json.loads(self.cli("host-check", "--json", cwd=self.wt["b"]).stdout)
        self.assertEqual(doc["role"], "dev")
        self.assertEqual([c["id"] for c in doc["checks"]], ["store", "registered", "version", "git-writable",
                                                          "commit-hooks"])   # S22


SANDBOX = "Codex 沙箱不让写 git 目录：请申请在沙箱外运行这条命令"
CODEX_PLUGIN = "Codex 侧的插件安装 module-crew 不读"


class SandboxHintTest(unittest.TestCase):
    """Acceptance 8: a write the Codex sandbox refused says to ask for running outside the sandbox."""

    def setUp(self):
        for key in SESSION_VARS:
            if key in os.environ:
                self.addCleanup(os.environ.__setitem__, key, os.environ.pop(key))

    def codex(self):
        return mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "thread-coord"})

    def test_recognised_texts(self):
        with self.codex():
            for text in ("fatal: Unable to create '/r/.git/index.lock': Operation not permitted",
                         "error: could not lock config file .git/config: Operation not permitted",
                         "fatal: Unable to create '/r/.git/index.lock': Permission denied"):
                with self.subTest(text=text):
                    self.assertEqual(probe.sandbox_hint(text), SANDBOX)
            for text in ("fatal: Unable to create '/r/.git/index.lock': File exists.", "fatal: not a git repository", ""):
                with self.subTest(text=text):
                    self.assertIsNone(probe.sandbox_hint(text))

    def test_only_in_codex(self):
        self.assertIsNone(probe.sandbox_hint("Operation not permitted"))

    def test_git_stderr_carries_hint(self):
        failed = mock.Mock(returncode=128, pid=0)       # S28: _git runs git through Popen
        failed.communicate.return_value = ("", "fatal: Unable to create 'x/index.lock': Operation not permitted\n")
        with self.codex(), mock.patch("subprocess.Popen", return_value=failed):
            out = probe._git(Path("."), "commit", "-m", "x")
        self.assertIn("Operation not permitted", out.stderr)
        self.assertIn(SANDBOX, out.stderr)

    def test_store_write_refused(self):
        refused = PermissionError(1, "Operation not permitted", "/r/.git/module-crew/events.jsonl")
        err = io.StringIO()
        with self.codex(), mock.patch.object(cli, "_main", side_effect=refused), redirect_stderr(err):
            self.assertEqual(cli.main(["task", "list"]), 1)
        self.assertIn("Operation not permitted", err.getvalue())
        self.assertIn(SANDBOX, err.getvalue())

    def test_store_write_refused_outside_codex_unchanged(self):
        refused = PermissionError(1, "Operation not permitted")
        with mock.patch.object(cli, "_main", side_effect=refused), self.assertRaises(PermissionError):
            cli.main(["task", "list"])


class CodexPluginHintTest(CodexCoordCase):
    """Acceptance 8: in Codex, a plugin missing from Claude's records says module-crew does not read Codex installs."""

    def drop(self, name):
        self.plugins.entries.pop(f"{name}@m")
        self.plugins.write()

    def reasons(self, *args, **kw):
        doc = json.loads(self.cli("status", "--json", *args, **kw).stdout)
        return {c["id"]: c["reason"] for c in doc["checks"]}

    def test_status(self):
        for name in ("spec-guard", "agent-relay"):
            with self.subTest(name=name):
                self.drop(name)
                self.assertIn(CODEX_PLUGIN, self.reasons()[name])
                self.assertNotIn(CODEX_PLUGIN, self.reasons(codex=None)[name])
                self.plugins.install(name, {"interface": "2.0"} if name == "agent-relay" else spec_guard_interface("1.7"),
                                     map_script=name == "spec-guard")

    def test_host_check(self):
        self.drop("spec-guard")
        bad = {c["id"]: c for c in json.loads(self.cli("host-check", "--json").stdout)["checks"] if not c["ok"]}
        self.assertIn(CODEX_PLUGIN, bad["spec-guard"]["reason"])


class CodexCoordinatorCommandsTest(CodexCoordCase):
    """Acceptance 3: a coordinator registered on Codex (through a handover) runs the coordinator commands."""

    def test_write_guard_knows_codex_threads(self):
        (self.repo / "msg.txt").write_text("【等待用户】\n", encoding="utf-8")
        for args in WRITES:
            with self.subTest(args=args[:2]):
                self.assertNotEqual(self.cli(*args).returncode, 7)
                before = len(list(store.events(self.db)))
                r = self.cli(*args, codex="thread-other")
                self.assertEqual(r.returncode, 7, (r.stdout, r.stderr))
                self.assertEqual(len(list(store.events(self.db))), before)

    def test_review_merge_cleanup_from_codex(self):
        final = self.tmp / "final.txt"
        final.write_text(self.finish("b"), encoding="utf-8")
        r = self.cli("review", "add", str(final), "--from", "shop-b", "--relay-id", "31")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        number = int(re.search(r"C(\d+)", r.stdout).group(1))
        r = self.cli("merge", "approve", str(number), "--original", "b 验收通过")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.cli("merge", "run", "--check-command", "python3 -c pass")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.cli("merge", "cleanup", "b", "--original", "收回 b")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotEqual(self.cli("merge", "push-plan").returncode, 7)

    def test_open_more_from_codex(self):
        r = self.cli("start", "prepare", "d", "--original", "开 d")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(store.get(self.db, "session", "shop-d")["host"], "codex-desktop")
        r = self.cli("coordinator", "down", "--original", "关")
        self.assertNotEqual(r.returncode, 7, r.stdout + r.stderr)


def wait_until(cond, timeout=60.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.2)
    return False


class DetachCase(MergeCase):
    """A final acceptance for b approved and queued; the full check sleeps so the merge outlives the parent."""

    def setUp(self):
        super().setUp()
        self.db = store.open_store(self.repo)
        self.number = self.approve_final("b", 31)

    def detach(self, sleep=3.0, fail_if=None):
        return self.run_cli("merge", "run", "--check-command", self.check_script(fail_if=fail_if, sleep=sleep), "--detach")

    def info(self):
        return json.loads((self.db.path / mergelock.INFO).read_text(encoding="utf-8"))


class ConflictCase(DetachCase):
    """b's final acceptance edits README.md, which the integration branch changed meanwhile: the merge conflicts."""

    def setUp(self):
        MergeCase.setUp(self)
        self.db = store.open_store(self.repo)
        (self.repo / "README.md").write_text("main changed\n")
        git(self.repo, "commit", "-q", "-am", "main edit")
        self.number = self.approve_final("b", 31, path="README.md", content="b changed\n")


class DetachTest(DetachCase):
    """Acceptance 4: start, lock and a killed child."""

    def test_parent_returns_at_once_child_holds_the_lock(self):
        began = time.monotonic()
        r = self.detach(sleep=4)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertLess(time.monotonic() - began, 4)
        log = self.db.path / "merge-output" / f"C{self.number}.log"
        self.assertIn(f"C{self.number}", r.stdout)
        self.assertIn(str(log), r.stdout)
        self.assertTrue(mergelock.locked(self.db))
        self.assertNotEqual(self.info()["pid"], os.getpid())
        self.assertEqual(self.run_cli("merge", "run", "--check-command", "python3 -c pass").returncode, 6)
        self.assertEqual(self.run_cli("coordinator", "down", "--original", "关").returncode, 6)
        self.assertTrue(wait_until(lambda: "exitCode" in self.info()))      # written just after the lock goes
        self.assertFalse(mergelock.locked(self.db))
        info = self.info()
        self.assertEqual((info["running"], info["approval"], info["exitCode"], info["resultRead"]),
                         (False, self.number, 0, False))
        self.assertEqual(info["log"], str(log))
        self.assertTrue(log.read_text(encoding="utf-8"), (info, sorted(p.name for p in log.parent.iterdir())))
        self.assertEqual(merge.queue(self.repo), [])

    def test_refusals_start_nothing(self):
        r = self.run_cli("merge", "run", "--check-command", "python3 -c pass")      # empties the queue
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.detach()
        self.assertEqual(r.returncode, 3)
        self.assertFalse((self.db.path / "merge-output").exists())

    def test_killed_child_leaves_a_stale_lock(self):
        self.assertEqual(self.detach(sleep=30).returncode, 0)
        self.assertTrue(wait_until(lambda: self.info().get("adopted")))      # the child has taken the lock over
        pid = self.info()["pid"]
        os.kill(pid, signal.SIGKILL)
        self.assertTrue(wait_until(lambda: not mergelock.locked(self.db)))
        self.assertTrue(self.info()["running"])
        self.assertIn("失效", self.run_cli("status").stdout)

    def test_child_entry_needs_the_lock(self):
        r = self.run_cli("merge", "run", "--check-command", "python3 -c pass", "--detached-child")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(len(merge.queue(self.repo)), 1)


def normalized(text: str, case) -> str:
    """Output of one fixture made comparable with another: temp paths and commit ids differ between them."""
    text = text.replace(str(case.tmp), "<tmp>")
    return re.sub(r"\b[0-9a-f]{7,40}\b", "<sha>", text)


class MergeResultTest(DetachCase):
    """Acceptance 4 (results) and 5."""

    def fresh(self):
        other = DetachCase("info")
        other.setUp()
        self.addCleanup(other.doCleanups)
        return other

    def result(self, *args, case=None):
        return (case or self).run_cli("merge", "result", *args)

    def finished(self, case=None):
        case = case or self
        return wait_until(lambda: "exitCode" in case.info())

    def test_running_then_ready(self):
        self.assertEqual(self.detach(sleep=6).returncode, 0)
        r = self.result()
        self.assertEqual(r.returncode, 6, r.stdout + r.stderr)
        self.assertIn("已跑", r.stdout)
        self.assertEqual(self.result(f"C{self.number}", "--wait", "0.02").returncode, 6)     # minutes
        r = self.result("--wait", "2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"C{self.number}", r.stdout)

    def test_same_output_and_code_as_foreground(self):
        for name, fail, code in (("merged", False, 0), ("check failed", True, 5)):
            with self.subTest(name):
                fg, bg = self.fresh(), self.fresh()
                flags = {}
                for c in (fg, bg):
                    flags[c] = str(c.tmp / "fail.flag") if fail else None
                    if fail:
                        (c.tmp / "fail.flag").touch()
                fore = fg.run_cli("merge", "run", "--check-command", fg.check_script(fail_if=flags[fg]))
                self.assertEqual(bg.detach(sleep=0, fail_if=flags[bg]).returncode, 0)
                self.assertTrue(self.finished(bg))
                back = self.result(case=bg)
                self.assertEqual((fore.returncode, back.returncode), (code, code), back.stdout)
                self.assertEqual(normalized(back.stdout, bg), normalized(fore.stdout + fore.stderr, fg))

    def test_conflict_same_as_foreground(self):
        fg, bg = ConflictCase("info"), ConflictCase("info")
        for c in (fg, bg):
            c.setUp()
            self.addCleanup(c.doCleanups)
        fore = fg.run_cli("merge", "run", "--check-command", "python3 -c pass")
        self.assertEqual(bg.run_cli("merge", "run", "--check-command", "python3 -c pass", "--detach").returncode, 0)
        self.assertTrue(self.finished(bg))
        back = self.result(case=bg)
        self.assertEqual((fore.returncode, back.returncode), (5, 5), back.stdout)
        self.assertEqual(normalized(back.stdout, bg), normalized(fore.stdout + fore.stderr, fg))

    def test_read_once_status_line(self):
        self.assertEqual(self.detach(sleep=0).returncode, 0)
        self.assertTrue(self.finished())
        line = f"合并 C{self.number} 已结束，运行 merge result 取通知"
        self.assertIn(line, self.run_cli("status").stdout)
        doc = json.loads(self.run_cli("status", "--json").stdout)["store"]["mergeResult"]
        self.assertEqual((doc["approval"], doc["exitCode"], doc["read"]), (self.number, 0, False))
        r = self.result("--json")
        self.assertEqual(r.returncode, 0)
        got = json.loads(r.stdout)
        self.assertEqual((got["approval"], got["running"], got["exitCode"]), (self.number, False, 0))
        self.assertTrue(got["output"])
        self.assertNotIn(line, self.run_cli("status").stdout)
        self.assertTrue(json.loads(self.run_cli("status", "--json").stdout)["store"]["mergeResult"]["read"])
        self.assertEqual(self.result().returncode, 0)          # read again: still there, never deleted

    def test_nothing_to_read(self):
        self.assertEqual(self.result().returncode, 3)
        self.run_cli("merge", "run", "--check-command", "python3 -c pass")      # a foreground merge leaves no result
        self.assertEqual(self.result().returncode, 3)


CODEX_OPEN = "请用户去 Codex 新建任务"


class CodexOpenGuideTest(CodexCoordCase):
    """Acceptance 9: with the coordinator on Codex, opening a module or a task says how to open it in Codex."""

    def test_start_prepare(self):
        r = self.cli("start", "prepare", "d", "--original", "开 d")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        tail = r.stdout[r.stdout.index(CODEX_OPEN):]
        rec = store.get(self.db, "session", "shop-d")
        self.assertIn("d：工作目录选", tail)
        self.assertIn(os.path.realpath(self.tmp), os.path.realpath(tail.split("工作目录选 ")[1].split("，")[0]))
        self.assertIn("第一条消息贴", tail)
        self.assertIn(".txt", tail)
        self.assertEqual(rec["host"], "codex-desktop")

    def test_task_dispatch(self):
        number = new_task(self.db, self.repo, kind="bug")
        r = self.cli("task", "dispatch", str(number))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(CODEX_OPEN, r.stdout)
        self.assertIn(f"T{number}：工作目录选", r.stdout)
        self.assertNotIn("用桌面版在这个 worktree 开新会话", r.stdout)


class ClaudeOpenUnchangedTest(MergeCase):
    """Acceptance 9, the other half: a Claude coordinator's output does not get the Codex section."""

    def test_start_prepare(self):
        r = self.run_cli("start", "prepare", "d", "--original", "开 d")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(CODEX_OPEN, r.stdout)


class HandoverGuideCodexTest(unittest.TestCase):
    """Acceptance 2, the guide: after taking over, run host-check; then the three steps every round."""

    def test_codex_guide(self):
        from module_crew import handover
        text = handover.guide("codex", "shop-coord", "/x/module-crew", "/r", "/r/orig.txt")
        self.assertIn("`/x/module-crew host-check`", text)
        self.assertIn("每轮开头三步", text)
        self.assertIn("重新 bridge_register（不带 takeover）→ 运行 status → 读收件箱", text)

    def test_claude_guide_unchanged_by_this(self):
        from module_crew import handover
        self.assertNotIn("host-check", handover.guide("claude", "shop-coord", "/x/module-crew", "/r", "/r/orig.txt"))


class RoundTripTest(GapCase):
    """Acceptance 2: with the real Codex coordinator skill in the plugin, the gap handover goes to Codex and back."""

    def env(self, codex=None, claude=None):
        env = {k: v for k, v in os.environ.items() if k not in SESSION_VARS}
        env.update({k: v for k, v in (("CODEX_THREAD_ID", codex), ("CLAUDE_CODE_SESSION_ID", claude)) if v})
        return env

    def test_to_codex_and_back(self):
        hooks.bind(self.db, "shop-coord", "sid-coord", self.repo, original="你来做模块协调")
        close_batch(self.db)
        self.assertTrue(handover.codex_coordinator_skill().is_file())
        r = self.run_cli("coordinator", "handover", "--to", "codex", "--original", "换到 Codex", env=self.env(claude="sid-coord"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("host-check", r.stdout)
        self.assertIn("每轮开头三步", r.stdout)
        original = re.search(r"--original-file ([^`\s]+)", r.stdout).group(1)
        r = self.run_cli("bind", "shop-coord", "--takeover", "--original-file", original, env=self.env(codex="thread-1"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.run_cli("status", env=self.env(codex="thread-1"))
        self.assertEqual(r.stdout.splitlines()[0], "本会话是模块协调 shop-coord（Codex）：没有钩子，以下按状态库为准")
        r = self.run_cli("host-check", "--json", env=self.env(codex="thread-1"))
        self.assertEqual(json.loads(r.stdout)["role"], "coordinator")
        r = self.run_cli("coordinator", "handover", "--to", "claude", "--original", "换回 Claude", env=self.env(codex="thread-1"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        original = re.search(r"--original-file ([^`\s]+)", r.stdout).group(1)
        r = self.run_cli("bind", "shop-coord", "--takeover", "--original-file", original, env=self.env(claude="sid-new"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rec = store.get(self.db, "session", "shop-coord")
        self.assertEqual((rec["host"], rec["hostSession"]["sessionId"], rec["hostHandover"]["pending"]),
                         ("claude-desktop", "sid-new", False))


class DocsTest(unittest.TestCase):
    """Acceptance 10."""

    ROOT = handover.PLUGIN_ROOT

    def test_readme(self):
        text = (self.ROOT / "README.md").read_text(encoding="utf-8")
        for words in ("### 模块协调在 Codex 上", "每轮开头三步", "申请在沙箱外运行", "merge run --detach", "merge result",
                      "请用户去 Codex 新建任务", "逐个点开", "module-crew merge run --detach / merge result"):
            with self.subTest(words=words):
                self.assertIn(words, text)
        self.assertNotIn("待定模块 B", text)

    def test_codex_plugin_description(self):
        doc = json.loads((self.ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertNotIn("协调会话在 Claude 桌面版", doc["description"])
        self.assertIn("模块协调", doc["description"])

    def test_claude_skill_no_longer_says_refused_until_b(self):
        text = (self.ROOT / "skills" / "crew-coordinator" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("待定模块 B", text)
        self.assertIn("Codex 版 crew-coordinator", text)


class StatusClaudeCoordinatorTest(MergeCase):
    """Acceptance 7, the other half: a Claude coordinator's status is unchanged."""

    def test_host_line_unchanged(self):
        self.assertIn("模块协调：Claude 桌面版；模块会话：Claude 或 Codex 桌面版", self.run_cli("status").stdout)


if __name__ == "__main__":
    unittest.main()
