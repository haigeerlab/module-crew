"""crew-codex-host: module sessions in Codex desktop (coordinator stays in Claude desktop)."""

import json
import os
import stat
import subprocess
import unittest

from helpers import RepoCase, StartCase

from module_crew import failure, hostcheck, start, store


class HostRegistryTest(RepoCase):
    def setUp(self):
        super().setUp()
        self.db, _ = store.init_store(self.repo)

    def put(self, key, rec):
        with self.db.transaction(actor="t") as tx:
            tx.put("session", key, rec, action="registered")

    def test_codex_module_session_accepted(self):
        self.put("shop-coord", {"role": "coordinator", "host": "claude-desktop", "status": "active"})
        self.put("shop-b", {"role": "dev", "host": "codex-desktop", "status": "active", "module": "b", "worktree": "/tmp/b"})
        self.assertEqual(store.get(self.db, "session", "shop-b")["host"], "codex-desktop")

    def test_coordinator_must_be_claude(self):
        with self.assertRaises(store.InvalidSession):
            self.put("shop-coord", {"role": "coordinator", "host": "codex-desktop", "status": "active"})
        with self.assertRaises(store.InvalidSession):
            self.put("shop-b", {"role": "dev", "host": "codex-cli", "status": "active", "module": "b", "worktree": "/tmp/b"})


class PrepareHostTest(StartCase):
    def kickoff(self, res, m):
        db = store.open_store(self.repo)
        p = next(x for x in res.prepared if x["id"] == m)
        return store.read_body(db, p["kickoff"])

    def test_codex_prepare(self):
        res = start.prepare(self.repo, ["b"], "开 b", short="shop", host="codex")
        self.assertEqual(res.code, 0, res.lines)
        db = store.open_store(self.repo)
        self.assertEqual(store.get(db, "session", "shop-b")["host"], "codex-desktop")
        self.assertEqual(store.get(db, "item", str(res.approval))["host"], "codex-desktop")
        text = self.kickoff(res, "b")
        for words in (str(start.BIN), "host-check", "提权", 'host:{app:"codex"', "重新注册", "module-crew status", "Codex 版 crew-dev"):
            self.assertIn(words, text)
        self.assertEqual(res.prepared[0]["host"], "codex-desktop")

    def test_claude_path_unchanged(self):
        res = start.prepare(self.repo, ["b"], "开 b", short="shop")
        db = store.open_store(self.repo)
        info = {"id": "b", "responsibility": "支付页", "dependsOn": ["a"]}
        want = start.render_kickoff("b", info, res.prepared[0]["worktree"], store.get(db, "config", "main"),
                                    "shop-b", "shop-coord", res.approval)
        self.assertEqual(self.kickoff(res, "b"), want)
        self.assertNotIn("Codex", want)
        self.assertNotIn("host", store.get(db, "item", str(res.approval)))
        self.assertEqual(store.get(db, "session", "shop-b")["host"], "claude-desktop")

    def test_mixed_batch_and_bad_host(self):
        self.assertEqual(start.prepare(self.repo, ["b"], "开 b", short="shop", host="codex").code, 0)
        self.assertEqual(start.prepare(self.repo, ["c"], "开 c").code, 0)
        db = store.open_store(self.repo)
        hosts = {k: v["host"] for k, v in store.records(db, "session").items() if v["role"] == "dev"}
        self.assertEqual(hosts, {"shop-b": "codex-desktop", "shop-c": "claude-desktop"})
        self.assertEqual(start.plan(self.repo).slots, 1)
        self.assertEqual(start.prepare(self.repo, ["d"], "开 d", host="foo").code, 3)
        out = self.run_cli("start", "prepare", "d", "--original", "开", "--host", "foo")
        self.assertEqual(out.returncode, 2)
        out = self.run_cli("start", "prepare", "d", "--original", "开 d", "--host", "codex")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("宿主：Codex 桌面版", out.stdout)


class HostCheckTest(StartCase):
    def setUp(self):
        super().setUp()
        res = start.prepare(self.repo, ["b"], "开 b", short="shop", host="codex")
        self.assertEqual(res.code, 0, res.lines)
        self.wt = res.prepared[0]["worktree"]

    def state(self):
        db = store.open_store(self.repo)
        files = {str(p): p.read_bytes() for p in db.path.rglob("*") if p.is_file() and p.name != ".lock"}
        return files, subprocess.run(["git", "-C", str(self.wt), "status", "--porcelain"], capture_output=True, text=True).stdout

    def test_all_pass_in_codex_worktree(self):
        before = self.state()
        rep = hostcheck.run(self.wt)
        self.assertEqual(rep.code, 0, [c for c in rep.checks if not c["ok"]])
        self.assertEqual((rep.module, rep.host), ("b", "codex-desktop"))
        self.assertEqual(self.state(), before)
        out = self.run_cli("host-check", "--json", cwd=self.wt)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(json.loads(out.stdout)["module"], "b")

    def test_git_dir_not_writable(self):
        gitdir = subprocess.run(["git", "-C", str(self.wt), "rev-parse", "--absolute-git-dir"],
                                capture_output=True, text=True).stdout.strip()
        mode = os.stat(gitdir).st_mode
        os.chmod(gitdir, stat.S_IRUSR | stat.S_IXUSR)
        try:
            rep = hostcheck.run(self.wt)
        finally:
            os.chmod(gitdir, mode)
        self.assertEqual(rep.code, 3)
        bad = [c for c in rep.checks if not c["ok"]]
        self.assertEqual([c["id"] for c in bad], ["git-writable"])
        self.assertIn("提权", bad[0]["fix"])

    def test_unregistered_and_outside(self):
        other = self.tmp / "other"
        other.mkdir()
        self.assertEqual(hostcheck.run(other).code, 2)
        plain = self.repo / "sub"
        plain.mkdir()
        rep = hostcheck.run(plain)            # the integration checkout is the coordinator, not a module session
        self.assertEqual(rep.code, 3)
        self.assertFalse(next(c for c in rep.checks if c["id"] == "registered")["ok"])

    def test_version_recorded_and_compared(self):
        db = store.open_store(self.repo)
        self.assertEqual(store.get(db, "config", "main")["pluginVersion"], hostcheck.plugin_version())
        with db.transaction(actor="t") as tx:
            tx.put("config", "main", dict(tx.get("config", "main"), pluginVersion="9.9.9"), action="set")
        rep = hostcheck.run(self.wt)
        self.assertFalse(next(c for c in rep.checks if c["id"] == "version")["ok"])


class RecoveryHostTest(StartCase):
    def test_resume_kit_and_sessions_follow_host(self):
        self.assertEqual(start.prepare(self.repo, ["b"], "开 b", short="shop", host="codex").code, 0)
        self.assertEqual(start.prepare(self.repo, ["c"], "开 c").code, 0)
        db = store.open_store(self.repo)
        codex = store.read_body(db, failure.resume_kit(db, "b").body)
        claude = store.read_body(db, failure.resume_kit(db, "c").body)
        for words in ("Codex", "用原名重新注册", "host-check", f"{start.BIN} status"):
            self.assertIn(words, codex)
            self.assertNotIn(words, claude)
        self.assertIn("module-crew takeover shop-c", claude)
        rows = {r["module"]: r for r in failure.sessions(db)}
        self.assertEqual((rows["b"]["host"], rows["c"]["host"]), ("codex-desktop", "claude-desktop"))
        doc = json.loads(self.run_cli("sessions", "--json", cwd=self.repo).stdout)
        self.assertEqual(doc["schemaVersion"], 1)
        self.assertEqual({r["module"]: r["host"] for r in doc["sessions"]}, {"b": "codex-desktop", "c": "claude-desktop"})


if __name__ == "__main__":
    unittest.main()
