"""Read-only facts the decision inbox uses to notice a stalled module (see spec/crew-stall-signals.md).

No thresholds and no verdicts here: how long is too long, and how many asks are too many, is the inbox's call.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path


_SEEN: dict[tuple, subprocess.CompletedProcess] = {}


def forget() -> None:
    """Drop the answers of the previous `sessions` run: the repository may have moved since."""
    _SEEN.clear()


def _git(worktree: Path, *args: str) -> subprocess.CompletedProcess:
    """Read-only git query, asked once per `sessions` run (0.8.1: 136 processes for 7 modules ran past 15 s under load)."""
    key = (str(worktree), args)
    if key not in _SEEN:
        _SEEN[key] = subprocess.run(["git", "-C", str(worktree), *args], capture_output=True, text=True)
    return _SEEN[key]


def _iso(text: str) -> str:
    """git's %cI writes a UTC date as ...Z, which datetime.fromisoformat only accepts from Python 3.11 (0.10.1)."""
    text = text.strip()
    return text[:-1] + "+00:00" if text.endswith("Z") else text


def _first_parents(path: Path) -> list[tuple[str, datetime]] | None:
    """HEAD's whole first-parent chain with commit dates, in walk order (one git process)."""
    out = _git(path, "log", "--first-parent", "--format=%H%x00%cI", "HEAD")
    if out.returncode != 0:
        return None
    return [(c, datetime.fromisoformat(_iso(t))) for c, t in (line.split("\0") for line in out.stdout.splitlines())]


def _blobs(path: Path, specs: list[str]) -> dict[str, str | None]:
    """`<commit>:<path>` → text (None when missing), all through one `git cat-file --batch`."""
    specs = list(dict.fromkeys(specs))
    if not specs:
        return {}
    out = subprocess.run(["git", "-C", str(path), "cat-file", "--batch"], input=("\n".join(specs) + "\n").encode("utf-8"),
                         capture_output=True)
    found: dict[str, str | None] = {}
    data, pos = out.stdout, 0
    for spec in specs:
        end = data.find(b"\n", pos)
        if out.returncode != 0 or end < 0:
            found[spec] = None
            continue
        head = data[pos:end].split()
        if len(head) != 3:                       # "<spec> missing" (or ambiguous)
            found[spec], pos = None, end + 1
            continue
        size = int(head[2])
        found[spec] = data[end + 1:end + 1 + size].decode("utf-8", "replace")
        pos = end + 1 + size + 1                 # contents are followed by a newline
    return found


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
        own = _git(path, "log", "--first-parent", f"--since={since}", "--format=%H%x00%cI", "HEAD")
        theirs = _git(path, "rev-list", "--first-parent", f"--since={since}", integration)
        if own.returncode != 0 or theirs.returncode != 0:
            return {**failed, "error": _error(own if own.returncode != 0 else theirs)}
        skip = set(theirs.stdout.split())
        hit = next((line.split("\0") for line in own.stdout.splitlines() if line.split("\0")[0] not in skip), None)
        if hit is None:
            return {"ahead": ahead, "last": None, "error": None}
        return {"ahead": ahead, "last": {"commit": hit[0], "at": _iso(hit[1])}, "error": None}
    commit = _git(path, "rev-list", "-1", span).stdout.strip() or None
    if commit is None:
        return {"ahead": ahead, "last": None, "error": None}
    at = _git(path, "log", "-1", "--format=%cI", commit)
    if at.returncode != 0:
        return {**failed, "error": _error(at)}
    return {"ahead": ahead, "last": {"commit": commit, "at": _iso(at.stdout)}, "error": None}


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


ANSWERED = ("review", "wait-user")   # a merge approval carries the same answer as its final review: counted once, as the review
_TICK = re.compile(r"^\s*- \[[xX]\]", re.M)


def _own_commits(path: Path, integration: str, since: str) -> list[tuple[str, datetime]] | None:
    """The module's own first-parent commits since it started (same rule as `commit_facts`), newest first."""
    own = _git(path, "log", "--first-parent", f"--since={since}", "--format=%H%x00%cI", "HEAD")
    theirs = _git(path, "rev-list", "--first-parent", f"--since={since}", integration)
    if own.returncode != 0 or theirs.returncode != 0:
        return None
    skip = set(theirs.stdout.split())
    return [(c, datetime.fromisoformat(_iso(t))) for c, t in (line.split("\0") for line in own.stdout.splitlines())
            if c not in skip]


def _tick_counts(path: Path, module: str, bounds: list[datetime | None]) -> dict[datetime | None, int]:
    """Checked todo items at each bound: in the last first-parent commit at or before it, or in the working tree
    for None. One `git log` and one `git cat-file --batch` for all bounds together.

    What counts as checked is spec-guard's rule (its `/map --json` progressFacts); spec-guard only reports the
    current value, not the value at each answer, so the history is read here. The current value is not taken from
    `/map` either: `sessions --json` must stay under the decision inbox's 15 s limit (0.8.1). Re-check this when
    spec-guard changes how todo items are written (spec/crew-stall-signals.md, 2026-10-22)."""
    rel = f"tasks/{module}/todo.md"
    out: dict[datetime | None, int] = {}
    if None in bounds:
        try:
            out[None] = len(_TICK.findall((path / rel).read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            out[None] = 0
    dated = [b for b in dict.fromkeys(bounds) if b is not None]
    chain = _first_parents(path) if dated else []
    commit = {b: next((c for c, t in chain or [] if t <= b), None) for b in dated}
    texts = _blobs(path, [f"{c}:{rel}" for c in commit.values() if c])
    for b in dated:
        text = texts.get(f"{commit[b]}:{rel}") if commit[b] else None
        out[b] = len(_TICK.findall(text)) if text else 0
    return out


def answers(items: dict, module: str, name: str, worktree: str | None, integration: str | None,
            since: str | None) -> list[dict]:
    """R21: each user answer to this module, and what moved before the next one (commits, ticked todo items)."""
    found = sorted((datetime.fromisoformat(v["answer"]["answeredAt"]), int(k))
                   for k, v in items.items()
                   if v.get("kind") in ANSWERED and (v.get("module") == module or v.get("from") == name)
                   and (v.get("answer") or {}).get("answeredAt"))
    path = Path(worktree) if worktree else None
    own = _own_commits(path, integration, since) if path and path.is_dir() and integration and since else None
    ends = [found[i + 1][0] if i + 1 < len(found) else None for i in range(len(found))]
    ticks = _tick_counts(path, module, [at for at, _ in found] + ends) if own is not None and found else {}
    out = []
    for (at, n), end in zip(found, ends):
        row = {"ref": f"C{n}", "at": at.isoformat(), "commitsAfter": None, "ticksAfter": None}
        if own is not None:
            row["commitsAfter"] = sum(1 for _, t in own if t > at and (end is None or t <= end))
            row["ticksAfter"] = max(ticks[end] - ticks[at], 0)
        out.append(row)
    return out
