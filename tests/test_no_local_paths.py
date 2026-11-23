"""Tracked files carry no machine-local home paths (S107: block new ones).

Scans every file listed by ``git ls-files`` for ``/Users/<name>`` and ``/home/<name>``,
and for the encoded form ``-Users-<name>-`` / ``-home-<name>-`` (Claude project dir names).
Placeholder names pass; real-looking names fail with file, line and how to fix it.
Samples copied verbatim from the session-protocol contract are exempt as a whole.

The test strings below never spell a home path in one literal, so this file
does not trip its own scan.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import git, make_repo

ROOT = Path(__file__).resolve().parent.parent
EXEMPT_PREFIXES = ("tests/fixtures/session-protocol/",)
PLACEHOLDERS = {"me", "user", "username", "you", "name", "example", "someone", "xxx", "..."}
HOME_PATH = re.compile(r"/(?:Users|home)/([^/\s\"'`)\]]+)")
# Encoded form, e.g. a Claude project dir name: -Users-<name>-Documents-…
ENCODED_HOME = re.compile(r"(?<![\w-])-(?:Users|home)-([^-/\s\"'`)\]]+)-")


def _is_placeholder(name: str) -> bool:
    if name.lower() in PLACEHOLDERS:
        return True
    # <名字> / <user> / $USER / ${USER} / {user} / %USERNAME% / * / …
    return any(ch in name for ch in "<>${}%*…")


def scan(repo: Path) -> list[str]:
    """Return one problem line per real-looking home path in tracked files."""
    out = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"], check=True, capture_output=True).stdout
    problems = []
    for rel in out.decode("utf-8").split("\0"):
        if not rel or rel.startswith(EXEMPT_PREFIXES):
            continue
        path = repo / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in HOME_PATH.finditer(line):
                if not _is_placeholder(match.group(1)):
                    problems.append(
                        f"{rel}:{lineno}: 带本机用户名的绝对路径 {match.group(0)!r}；"
                        "改成相对路径、环境变量（$HOME、tempfile），或用占位名 /Users/me/")
            for match in ENCODED_HOME.finditer(line):
                if not _is_placeholder(match.group(1)):
                    problems.append(
                        f"{rel}:{lineno}: 带本机用户名的编码路径 {match.group(0)!r}；"
                        "改成占位名 -Users-me- 或 -Users-<名字>-")
    return problems


def _home(name: str) -> str:
    return "/" + "Users" + "/" + name + "/"


def _encoded(name: str, root: str = "Users") -> str:
    return "-" + root + "-" + name + "-"


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = make_repo(self.tmp)

    def commit(self, rel: str, text: str) -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        git(self.repo, "add", rel)
        git(self.repo, "commit", "-qm", "x")

    def test_real_name_reported_with_file_line_and_fix(self):
        self.commit("docs/a.md", "ok\nsee " + _home("alice") + "proj\n")
        self.commit("b.py", 'p = "' + "/" + "home" + "/bob/x" + '"\n')
        problems = scan(self.repo)
        self.assertEqual(len(problems), 2, problems)
        self.assertTrue(problems[0].startswith("b.py:1:") or problems[1].startswith("b.py:1:"), problems)
        alice = [p for p in problems if p.startswith("docs/a.md:2:")]
        self.assertEqual(len(alice), 1, problems)
        self.assertIn("alice", alice[0])
        self.assertIn("改成", alice[0])

    def test_placeholders_pass(self):
        names = ["me", "<名字>", "<user>", "<用户名>", "$USER", "${USER}", "{user}", "USER", "you"]
        self.commit("docs/p.md", "\n".join(_home(n) + "x" for n in names) + "\n")
        self.assertEqual(scan(self.repo), [])

    def test_encoded_real_name_reported(self):
        # Claude 项目目录名把 / 换成 -：-Users-<名字>-Documents-…
        self.commit("docs/m.md", "ok\nmemory: ~/.claude/projects/" + _encoded("alice") + "Documents-x/\n")
        self.commit("c.txt", _encoded("bob", "home") + "proj\n")
        problems = scan(self.repo)
        self.assertEqual(len(problems), 2, problems)
        alice = [p for p in problems if p.startswith("docs/m.md:2:")]
        self.assertEqual(len(alice), 1, problems)
        self.assertIn("alice", alice[0])
        self.assertIn("改成", alice[0])
        self.assertTrue(any(p.startswith("c.txt:1:") and "bob" in p for p in problems), problems)

    def test_encoded_placeholders_pass(self):
        names = ["me", "<名字>", "<user>", "$USER", "${USER}", "{user}", "you"]
        self.commit("docs/q.md", "\n".join(_encoded(n) + "x" for n in names) + "\n")
        self.assertEqual(scan(self.repo), [])

    def test_contract_samples_exempt(self):
        self.commit("tests/fixtures/session-protocol/v9/x.txt", _home("carol") + "repo\n")
        self.assertEqual(scan(self.repo), [])

    def test_untracked_files_not_scanned(self):
        (self.repo / "loose.md").write_text(_home("dave") + "x\n", encoding="utf-8")
        self.assertEqual(scan(self.repo), [])


class RepositoryTest(unittest.TestCase):
    def test_tracked_files_have_no_local_home_paths(self):
        problems = scan(ROOT)
        self.assertEqual(problems, [], "\n" + "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
