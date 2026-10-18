"""Approval sources besides the coordinator's own user (see spec/crew-hub-bridge.md).

The user, in the coordinating session, whitelists the relay names that may carry their decisions: a decision
inbox hub (`hub`) or a designated lead such as a review session (`lead`).  An approval that names such a source
must come with that session's message; the user's words are read out of it, never retyped by the coordinator.
"""

from __future__ import annotations

from dataclasses import dataclass

from module_crew import protocol, store

KINDS = ("hub", "lead")


class SourceRefused(Exception):
    """The source cannot be used; nothing was written."""


@dataclass(frozen=True)
class SourceInfo:
    original: str            # the user's words, as read from the source's message
    source: dict             # recorded on the approval: {"name", "kind", "item", "relayId"}


SELF = {"kind": "self"}


def _need(original: str | None) -> None:
    if not original or not original.strip():
        raise SourceRefused("用户原话不能为空：来源只能由用户在本会话亲手登记")


def add(db: store.Store, name: str, kind: str, original: str) -> None:
    _need(original)
    if kind not in KINDS:
        raise SourceRefused(f"来源种类只能是 {'／'.join(KINDS)}")
    if not name or not name.strip():
        raise SourceRefused("来源的邮箱名不能为空")
    with db.transaction(actor="coordinator") as tx:
        cfg = tx.get("config", "main") or {}
        rows = list(cfg.get("sources") or [])
        if any(r.get("name") == name for r in rows):
            raise SourceRefused(f"{name} 已经登记为来源")
        rows.append({"name": name, "kind": kind, "addedAt": store.now(), "original": original})
        tx.put("config", "main", {**cfg, "sources": rows}, action="source-added", data={"name": name, "kind": kind})


def remove(db: store.Store, name: str, original: str) -> None:
    _need(original)
    with db.transaction(actor="coordinator") as tx:
        cfg = tx.get("config", "main") or {}
        rows = list(cfg.get("sources") or [])
        if not any(r.get("name") == name for r in rows):
            raise SourceRefused(f"{name} 没有登记为来源")
        tx.put("config", "main", {**cfg, "sources": [r for r in rows if r.get("name") != name]},
               action="source-removed", data={"name": name, "original": original})


def listing(db: store.Store) -> list[dict]:
    return list((store.get(db, "config", "main") or {}).get("sources") or [])


def check(db: store.Store, name: str, item: int, relay_id: int, text: str | None) -> SourceInfo:
    """Validate a decision carried by a whitelisted source and read the user's words out of its message."""
    row = next((r for r in listing(db) if r.get("name") == name), None)
    if row is None:
        raise SourceRefused(f"{name} 不是登记过的来源（先请用户在本会话 source add）")
    if not text or not text.strip():
        raise SourceRefused("来源消息的全文不能为空（--original-file 放对方那条消息）")
    if row["kind"] == "lead":
        raise SourceRefused("负责人转交的消息格式要等 session-protocol v1.6 定稿，现在不接受 lead 来源")
    msg = protocol.parse(text)
    if msg.kind != "user-reply" or not msg.ok:
        raise SourceRefused("来源消息不是合格的【用户答复】：" + ("、".join(msg.problems) or msg.kind))
    if msg.item != item:
        raise SourceRefused(f"来源消息的事项是 #{msg.item}，不是 --source-item 给的 #{item}")
    return SourceInfo(msg.fields["用户原话"], {"name": name, "kind": row["kind"], "item": item, "relayId": relay_id})
