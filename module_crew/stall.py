"""Read-only facts the decision inbox uses to notice a stalled module (see spec/crew-stall-signals.md).

No thresholds and no verdicts here: how long is too long, and how many asks are too many, is the inbox's call.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git(worktree: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(worktree), *args], capture_output=True, text=True)


def _error(out: subprocess.CompletedProcess) -> str:
    return (out.stderr.strip().splitlines() or [f"git 退出码 {out.returncode}"])[0]


def commit_facts(worktree: str | None, integration: str | None) -> dict:
    """Commits on the worktree's HEAD that are not on the integration branch: how many, and the latest one."""
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
    if ahead == 0:
        return {"ahead": 0, "last": None, "error": None}
    log = _git(path, "log", "-1", "--format=%H%x00%cI", span)
    if log.returncode != 0:
        return {**failed, "error": _error(log)}
    commit, at = log.stdout.strip().split("\0")
    return {"ahead": ahead, "last": {"commit": commit, "at": at}, "error": None}


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
    return [{"node": node, "count": len(seen[node]), "refs": [f"C{n}" for n, _ in sorted(seen[node])],
             "lastAt": max(t for _, t in seen[node])} for node in NODES if node in seen]


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
