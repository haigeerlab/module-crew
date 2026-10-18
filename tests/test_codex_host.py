"""crew-codex-host: module sessions in Codex desktop (coordinator stays in Claude desktop)."""

import unittest

from helpers import RepoCase, StartCase

from module_crew import start, store


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


if __name__ == "__main__":
    unittest.main()
