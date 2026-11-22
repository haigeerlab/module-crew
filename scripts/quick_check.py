#!/usr/bin/env python3
"""Quick check: run only the tests touched by this branch's changes (T652).

`module-crew check quick` runs this in a module or task worktree as argv, without a shell and without arguments.
It compares the working tree with the merge-base of HEAD and the integration branch (read from the module-crew
store, `main` when it cannot be read) and picks tests:

- a changed test file `tests/test_*.py` runs itself;
- a changed `module_crew/<name>.py` runs every test file that references it, plus test_glossary (which reads the
  strings of every module);
- a changed `scripts/<name>.py` runs `tests/test_<name>.py` when it exists;
- a changed file under skills/, codex-skills/, docs/ or a README runs test_docs, test_skills and test_glossary;
- spec/ and tasks/ are read by no test and are skipped.

Anything it cannot map (another file, a deleted file, `__main__.py`, a module no test references), no change at all,
or any error falls back to the full check `python3 -m unittest discover -s tests`. The exit code is unittest's.
Standard library only.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC_TESTS = ("test_docs", "test_skills", "test_glossary")
DOC_PREFIXES = ("skills/", "codex-skills/", "docs/")
SKIPPED_PREFIXES = ("spec/", "tasks/")
FULL = ["-m", "unittest", "discover", "-s", "tests"]


class Fallback(Exception):
    """The changes cannot be mapped to tests; run the full check for this reason."""


def integration_branch(root: Path) -> str:
    sys.path.insert(0, str(root))
    try:
        from module_crew import store
        branch = (store.get(store.open_store(root), "config", "main") or {}).get("integrationBranch")
        return branch or "main"
    except Exception:
        return "main"
    finally:
        sys.path.remove(str(root))


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise Fallback(f"git {' '.join(args)} 失败：{done.stderr.strip() or done.returncode}")
    return done.stdout


def changed_files(root: Path, branch: str) -> list[tuple[str, str]]:
    """(status, path) of every change in the working tree since the merge-base, untracked files included."""
    base = _git(root, "merge-base", "HEAD", f"refs/heads/{branch}").strip()
    out = []
    for line in _git(root, "diff", "--name-status", "--no-renames", base).splitlines():
        status, _, path = line.partition("\t")
        out.append((status[:1], path))
    out += [("A", p) for p in _git(root, "ls-files", "--others", "--exclude-standard").splitlines() if p]
    return out


def _references(text: str, name: str) -> bool:
    if re.search(rf"\bmodule_crew\.{re.escape(name)}\b", text):
        return True
    if re.search(rf"[\"']module_crew[\"']\s*/\s*[\"']{re.escape(name)}\.py[\"']", text):
        return True
    for names in re.findall(r"from\s+module_crew\s+import\s+(\([^)]*\)|[^\n]+)", text):
        if name in re.findall(r"\w+", names.split("#")[0]):
            return True
    return False


def referencing_tests(root: Path, name: str) -> list[str]:
    return sorted(p.stem for p in (root / "tests").glob("test_*.py")
                  if _references(p.read_text(encoding="utf-8"), name))


def _summary(whys: list[str]) -> str:
    """One reason per kind: a single path is named, several are counted."""
    kinds: dict[str, list[str]] = {}
    for why in dict.fromkeys(whys):
        kind, _, path = why.rpartition(" ")
        kinds.setdefault(kind, []).append(path)
    return "；".join(f"{k} {paths[0]}" if len(paths) == 1 else f"{k} {paths[0]} 等 {len(paths)} 个文件"
                    for k, paths in kinds.items())


def select(root: Path, changes: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    """(test module names, one reason line per pick); raises Fallback when the full check has to run."""
    if not changes:
        raise Fallback("相对集成分支没有改动")
    picks: dict[str, list[str]] = {}

    def add(test: str, why: str):
        picks.setdefault(test, []).append(why)

    skipped = []
    for status, path in changes:
        if path.startswith(SKIPPED_PREFIXES):
            skipped.append(path)
            continue
        if status == "D":
            raise Fallback(f"删除了 {path}，对不上号")
        parts = path.split("/")
        if len(parts) == 2 and parts[0] == "tests" and re.fullmatch(r"test_\w+\.py", parts[1]):
            add(parts[1][:-3], f"改了测试文件 {path}")
        elif len(parts) == 2 and parts[0] == "module_crew" and parts[1].endswith(".py") \
                and parts[1] not in ("__init__.py", "__main__.py"):
            name = parts[1][:-3]
            tests = referencing_tests(root, name)
            if not tests:
                raise Fallback(f"没有测试文件引用 {path}，对不上号")
            for test in tests:
                add(test, f"引用了改过的 {path}")
            add("test_glossary", f"读所有模块的文字，改了 {path}")
        elif len(parts) == 2 and parts[0] == "scripts" and parts[1].endswith(".py") \
                and (root / "tests" / f"test_{parts[1]}").exists():
            add(f"test_{parts[1][:-3]}", f"改了脚本 {path}")
        elif path.startswith(DOC_PREFIXES) or re.fullmatch(r"README(\.[\w-]+)?\.md", path):
            for test in DOC_TESTS:
                add(test, f"文档类改动 {path}")
        else:
            raise Fallback(f"{path} 对不上号")
    if not picks:
        raise Fallback(f"只改了不被测试读取的文件（{len(skipped)} 个），没有可选的测试")
    missing = [t for t in picks if not (root / "tests" / f"{t}.py").exists()]
    if missing:
        raise Fallback(f"测试文件不存在：{'、'.join(missing)}")
    reasons = [f"  {t}：{_summary(picks[t])}" for t in sorted(picks)]
    if skipped:
        reasons.append(f"  跳过 {len(skipped)} 个 spec/、tasks/ 下的文件（没有测试读取）")
    return sorted(picks), reasons


def plan(root: Path) -> tuple[list[str], list[str]]:
    """The argv after the interpreter and the lines to print before running it."""
    try:
        branch = integration_branch(root)
        tests, reasons = select(root, changed_files(root, branch))
    except Fallback as exc:
        return FULL, [f"快检查：退回完整检查（{exc}）", "  跑：python3 " + " ".join(FULL)]
    except Exception as exc:
        return FULL, [f"快检查：退回完整检查（出错：{exc!r}）", "  跑：python3 " + " ".join(FULL)]
    return ["-m", "unittest", *tests], [f"快检查：相对集成分支 {branch} 的改动，跑 {len(tests)} 个测试文件", *reasons]


def main() -> int:
    args, lines = plan(ROOT)
    print("\n".join(lines), flush=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "tests"), str(ROOT), env.get("PYTHONPATH")]))
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
