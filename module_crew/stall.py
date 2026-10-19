"""Read-only facts the decision inbox uses to notice a stalled module (see spec/crew-stall-signals.md).

No thresholds and no verdicts here: how long is too long, and how many asks are too many, is the inbox's call.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path


def _git(worktree: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(worktree), *args], capture_output=True, text=True)


def _error(out: subprocess.CompletedProcess) -> str:
    return (out.stderr.strip().splitlines() or [f"git 退出码 {out.returncode}"])[0]


def commit_facts(worktree: str | None, integration: str | None, since: str | None = None) -> dict:
    """How many commits are not merged yet (`ahead`), and the module's own latest commit since it started (`last`).

    `last` walks HEAD's first-parent chain since `since`, skipping what is on the integration branch's first-parent
    chain: it survives the module's merge into the integration branch, and a fast-forward sync is not module output.
    """
    failed = {"ahead": None, "last": None}
    if not integration:
        return {**failed, "error": "运行配置没有集成分支"}
    path = Path(worktree) if worktree else None
    if path is None or not path.is_dir():
        return {**failed, "error": f"worktree 不存在：{worktree}"}
    span = f"{integration}..HEAD"
    count = _git(path, "rev-list", "--count", span)
    if count.returncode != 0:
        return {**failed, "error": _error(count)}
    ahead = int(count.stdout.strip())
    if since:
        own = _git(path, "rev-list", "--first-parent", f"--since={since}", "HEAD")
        theirs = _git(path, "rev-list", "--first-parent", f"--since={since}", integration)
        if own.returncode != 0 or theirs.returncode != 0:
            return {**failed, "error": _error(own if own.returncode != 0 else theirs)}
        skip = set(theirs.stdout.split())
        commit = next((c for c in own.stdout.split() if c not in skip), None)
    else:
        commit = _git(path, "rev-list", "-1", span).stdout.strip() or None
    if commit is None:
        return {"ahead": ahead, "last": None, "error": None}
    at = _git(path, "log", "-1", "--format=%cI", commit)
    if at.returncode != 0:
        return {**failed, "error": _error(at)}
    return {"ahead": ahead, "last": {"commit": commit, "at": at.stdout.strip()}, "error": None}


def started_at(events: list[dict], name: str) -> str | None:
    """When `start prepare` registered this session; a takeover does not move it."""
    return next((e["at"] for e in reversed(events) if e["type"] == "session.registered" and e["key"] == name), None)


NODES = ("spec", "plan", "interface", "final")      # display order of the spec; not review.NODE_RANK


def _event_at(events: list[dict]) -> dict[tuple[str, str], str]:
    """(type, key) -> time of the first such event."""
    at: dict[tuple[str, str], str] = {}
    for e in events:
        at.setdefault((e["type"], e["key"]), e["at"])
    return at


def asks(events: list[dict], items: dict, module: str) -> list[dict]:
    """Per node, the reviews that reached the user: put into a hub batch, or answered by the user."""
    at = _event_at(events)
    hub: dict[str, str] = {}
    for key, v in items.items():
        if v.get("kind") == "hub-batch" and (when := at.get(("item.hub-batch", key))):
            for n in v.get("reviews", []):
                hub[str(n)] = max(hub.get(str(n), when), when)
    seen: dict[str, list[tuple[int, str]]] = {}
    for key, v in items.items():
        if v.get("kind") != "review" or v.get("module") != module:
            continue
        times = [t for t in (hub.get(key), (v.get("answer") or {}).get("answeredAt")
                             if v.get("closedReason") == "answered" else None) if t]
        if times:
            seen.setdefault(v["node"], []).append((int(key), max(times)))
    out = []
    for node in NODES:
        if node in seen:
            ordered = sorted(seen[node])
            out.append({"node": node, "count": len(ordered), "refs": [f"C{n}" for n, _ in ordered],
                        "ats": [t for _, t in ordered], "lastAt": max(t for _, t in ordered)})
    return out


def returns(events: list[dict], items: dict, module: str) -> list[dict]:
    """Final acceptances approved by the user and then returned by the merge check."""
    at = _event_at(events)
    return [{"ref": f"C{n}", "returnKind": v.get("returnKind"), "at": at.get(("item.returned", str(n)))}
            for n, v in sorted((int(k), v) for k, v in items.items())
            if v.get("kind") == "merge-approval" and v.get("module") == module and v.get("closedReason") == "returned"]


def wait_user(events: list[dict], items: dict, name: str) -> list[dict]:
    """Every 【等待用户】 this module session sent, open or closed; whether two are the same question is the inbox's call."""
    first: dict[str, str] = {}
    for e in events:
        if e["type"].startswith("item."):
            first.setdefault(e["key"], e["at"])
    return [{"ref": f"C{n}", "state": v.get("state"), "closedReason": v.get("closedReason"),
             "decide": (v.get("decide") or "").strip().split("\n")[0], "at": first.get(str(n))}
            for n, v in sorted((int(k), v) for k, v in items.items())
            if v.get("kind") == "wait-user" and v.get("from") == name]


ANSWERED = ("review", "wait-user", "merge-approval")
_TICK = re.compile(r"^\s*- \[[xX]\]", re.M)


def _own_commits(path: Path, integration: str, since: str) -> list[tuple[str, datetime]] | None:
    """The module's own first-parent commits since it started (same rule as `commit_facts`), newest first."""
    own = _git(path, "log", "--first-parent", f"--since={since}", "--format=%H%x00%cI", "HEAD")
    theirs = _git(path, "rev-list", "--first-parent", f"--since={since}", integration)
    if own.returncode != 0 or theirs.returncode != 0:
        return None
    skip = set(theirs.stdout.split())
    return [(c, datetime.fromisoformat(t)) for c, t in (line.split("\0") for line in own.stdout.splitlines())
            if c not in skip]


def _ticks(path: Path, module: str, before: datetime | None) -> int:
    """Checked todo items: in the last first-parent commit before `before`, or in the working tree when None."""
    rel = f"tasks/{module}/todo.md"
    if before is None:
        try:
            return len(_TICK.findall((path / rel).read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            return 0
    commit = _git(path, "rev-list", "-1", "--first-parent", f"--before={before.isoformat()}", "HEAD").stdout.strip()
    shown = _git(path, "show", f"{commit}:{rel}") if commit else None
    return len(_TICK.findall(shown.stdout)) if shown is not None and shown.returncode == 0 else 0


def answers(items: dict, module: str, name: str, worktree: str | None, integration: str | None,
            since: str | None) -> list[dict]:
    """R21: each user answer to this module, and what moved before the next one (commits, ticked todo items)."""
    found = sorted((datetime.fromisoformat(v["answer"]["answeredAt"]), int(k))
                   for k, v in items.items()
                   if v.get("kind") in ANSWERED and (v.get("module") == module or v.get("from") == name)
                   and (v.get("answer") or {}).get("answeredAt"))
    path = Path(worktree) if worktree else None
    own = _own_commits(path, integration, since) if path and path.is_dir() and integration and since else None
    out = []
    for i, (at, n) in enumerate(found):
        end = found[i + 1][0] if i + 1 < len(found) else None
        row = {"ref": f"C{n}", "at": at.isoformat(), "commitsAfter": None, "ticksAfter": None}
        if own is not None:
            row["commitsAfter"] = sum(1 for _, t in own if t > at and (end is None or t <= end))
            row["ticksAfter"] = max(_ticks(path, module, end) - _ticks(path, module, at), 0)
        out.append(row)
    return out
