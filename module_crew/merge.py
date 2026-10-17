"""Local merge queue and remote hand-off (see spec/crew-merge.md).

Approved final acceptances are merged into the local integration branch one at a time with
--no-ff and checked; failures are reverted (or aborted) and the module is sent back. Pushing
goes to a new remote branch and a PR the user merges.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from module_crew import probe, protocol, store
from module_crew.inbox import AnswerRefused, Reply
from module_crew.review import _reply_text

DEFAULT_CHECK_TIMEOUT = 1800


@dataclass
class Approved:
    approval: int
    reply: Reply


def approve(db: store.Store, review_no: int, original: str) -> Approved:
    """Record the user's approval of a final acceptance and queue the module for a local merge."""
    with db.transaction(actor="coordinator") as tx:
        rec = tx.get("item", str(review_no))
        if rec is None or rec.get("kind") != "review":
            raise AnswerRefused(f"没有交审事项 #{review_no}")
        if rec.get("node") != "final":
            raise AnswerRefused(f"交审事项 #{review_no} 不是最终验收（Spec／Plan 用 review approve）")
        if rec.get("state") != "open":
            raise AnswerRefused(f"交审事项 #{review_no} 已关闭（{rec.get('closedReason')}）")
        answered_at = store.now()
        text = _reply_text(review_no, rec, original, answered_at)
        approval = tx.allocate_number()
        tx.put("item", str(approval), {
            "state": "open", "kind": "merge-approval", "module": rec["module"], "review": review_no,
            "commit": rec["commit"], "from": rec["from"], "relayId": rec["relayId"],
            "answer": {"original": original, "answeredAt": answered_at},
            "closedReason": None, "mergeCommit": None, "revertCommit": None, "reason": None,
        }, action="merge-approved")
        body = tx.allocate_number()
        meta = tx.write_body(body, text)
        tx.put("item", str(review_no), dict(rec, state="closed", closedReason="answered",
                                            answer={"original": original, "answeredAt": answered_at, "body": body,
                                                    "approval": approval}),
               action="answered", data={"body": body})
    return Approved(approval, Reply(rec["from"], rec["relayId"], body, db.path / meta["path"]))


def _build_order(project: Path) -> list[str] | None:
    report = probe.run(project)
    if not report.map:
        return None
    return [m.get("id") for m in report.map.get("modules") or [] if isinstance(m, dict)]


def queue(project: str | os.PathLike) -> list[tuple[int, dict]]:
    """Open merge approvals in Build order (approval number when /map is unavailable)."""
    project = Path(project)
    db = store.open_store(project)
    rows = [(int(k), v) for k, v in store.records(db, "item").items()
            if v.get("kind") == "merge-approval" and v.get("state") == "open"]
    order = _build_order(project) or []
    pos = {m: i for i, m in enumerate(order)}
    return sorted(rows, key=lambda kv: (pos.get(kv[1]["module"], len(pos)), kv[0]))
