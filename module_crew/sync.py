"""`module-crew sync`: merge the integration branch into this module's branch (see spec/crew-pilot-fixes.md).

The module session runs one command that is already allowed, instead of `git merge` in whatever spelling it happens
to type (X-1, X-3).  Conflicts in the module's own Spec and tasks take the integration version (it carries the
approval mark); any other conflict is left in place for the module to resolve with its editor, `git add` and
`git commit --no-edit`, all of which are allowed.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from module_crew import hooks, store

# The one wording every start / sync-baseline / resume notice uses for "merge the integration branch in".
STEP = "跑 `module-crew sync` 把集成分支合进你的模块分支（单独执行，不和别的命令连写）"


@dataclass
class SyncResult:
    code: int                       # 0 done or up to date / 2 conflicts left for the module / 3 refused
    lines: list[str] = field(default_factory=list)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def _own(module: str, path: str) -> bool:
    return path == f"spec/{module}.md" or path.startswith(f"tasks/{module}/")


def run(cwd: str | Path) -> SyncResult:
    cwd = Path(cwd)
    try:
        db = store.open_store(cwd)
    except store.StoreError as exc:
        return SyncResult(3, [f"不在 module-crew 管理的仓库里：{exc}"])
    role = hooks.detect(cwd)
    if role is None or role.kind != "dev":
        return SyncResult(3, ["这里不是登记过的在用模块会话的 worktree：sync 只在模块 worktree 里跑，集成 checkout 的合并走 merge run"])
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch")
    if not branch:
        return SyncResult(3, ["运行配置里没有集成分支（integrationBranch）"])
    top = Path(_git(cwd, "rev-parse", "--show-toplevel").stdout.strip() or cwd)
    if _git(top, "status", "--porcelain").stdout.strip():
        return SyncResult(3, ["工作区有未提交的改动：先提交或收起改动再同步（sync 不替你提交）"])
    target = _git(top, "rev-parse", "--verify", f"refs/heads/{branch}").stdout.strip()
    if not target:
        return SyncResult(3, [f"找不到集成分支 {branch}"])
    if _git(top, "merge-base", "--is-ancestor", target, "HEAD").returncode == 0:
        return SyncResult(0, [f"已是最新：已包含集成分支 {branch} {target[:7]}"])
    count = _git(top, "rev-list", "--count", f"HEAD..{target}").stdout.strip() or "?"
    merged = _git(top, "merge", "--no-edit", branch)
    if merged.returncode == 0:
        return _done(top, branch, target, count)
    conflicts = [p for p in _git(top, "diff", "--name-only", "--diff-filter=U").stdout.splitlines() if p]
    if not conflicts:
        _git(top, "merge", "--abort")
        return SyncResult(3, [f"合并失败，已中止：{(merged.stderr or merged.stdout).strip()[:300]}"])
    others, taken = [], []
    for path in conflicts:
        if _own(role.module, path) and _git(top, "checkout", "--theirs", "--", path).returncode == 0 \
                and _git(top, "add", "--", path).returncode == 0:
            taken.append(path)
        else:
            others.append(path)
    lines = [f"本模块文件冲突，已取集成分支版本：{'、'.join(taken)}"] if taken else []
    if others:
        return SyncResult(2, lines + [
            f"其他冲突（{len(others)} 个，合并没有中止）：", *[f"  {p}" for p in others],
            "用编辑工具解决后 git add 这些文件、git commit --no-edit，再跑一次 module-crew sync 确认"])
    done = _git(top, "commit", "--no-edit")
    if done.returncode != 0:
        return SyncResult(3, lines + [f"完成合并提交失败：{(done.stderr or done.stdout).strip()[:300]}"])
    result = _done(top, branch, target, count)
    result.lines[:0] = lines
    return result


def _done(top: Path, branch: str, target: str, count: str) -> SyncResult:
    head = _git(top, "rev-parse", "--short", "HEAD").stdout.strip()
    if _git(top, "merge-base", "--is-ancestor", target, "HEAD").returncode != 0:
        return SyncResult(3, [f"合并后 HEAD {head} 仍不包含集成分支 {branch} {target[:7]}"])
    return SyncResult(0, [f"已合入集成分支 {branch} {target[:7]}：合入 {count} 个提交，HEAD {head}",
                          "接着跑完整检查再继续"])
