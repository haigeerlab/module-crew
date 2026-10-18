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


def check(db: store.Store, name: str, item: int, relay_id: int, text: str | None, *, sender: str) -> SourceInfo:
    """Validate a decision carried by a whitelisted source and read the user's words out of its message.

    `sender` is the mailbox the message actually came from (copied from bridge_inbox): it must be the source itself
    and never a registered module session, so a module session cannot pass off a 【用户答复】 as the hub's.
    """
    dev = store.get(db, "session", sender)
    if dev is not None and dev.get("role") == "dev":
        raise SourceRefused(f"{sender} 是登记的模块会话，它发来的消息不能当作用户的决定")
    if sender != name:
        raise SourceRefused(f"这条消息的发件人是 {sender}，不是来源 {name}：只认来源自己发来的消息")
    row = next((r for r in listing(db) if r.get("name") == name), None)
    if row is None:
        raise SourceRefused(f"{name} 不是登记过的来源（先请用户在本会话 source add）")
    if not text or not text.strip():
        raise SourceRefused("来源消息的全文不能为空（--original-file 放对方那条消息）")
    msg = protocol.parse(text)
    want, label = ("owner-handoff", "【负责人转交】") if row["kind"] == "lead" else ("user-reply", "【用户答复】")
    if msg.kind != want or not msg.ok:
        raise SourceRefused(f"来源消息不是合格的{label}：" + ("、".join(msg.problems) or msg.kind))
    if msg.item != item:
        raise SourceRefused(f"来源消息的事项是 #{msg.item}，不是 --source-item 给的 #{item}")
    source = {"name": name, "kind": row["kind"], "item": item, "relayId": relay_id}
    if row["kind"] == "lead":
        source.update(owner=msg.fields["来自"].strip(), scope=msg.fields["转交范围"])
    return SourceInfo(msg.fields["用户原话"], source)


def relay_line(source: dict) -> str:
    """The v1.6 「转自」 line for a reply relayed to a module session."""
    if source["kind"] == "lead":
        return f"{source['owner']}（负责人转交），消息 #{source['relayId']}"
    return f"收件枢纽，消息 #{source['relayId']}"


def map_item(db: store.Store, item: int) -> list[dict]:
    """crew records approved through source item H (one H can cover several crew numbers)."""
    rows, seen = [], set()
    for e in store.events(db):
        src = (e.get("data") or {}).get("source") or {}
        if src.get("item") != item or e["type"].split(".")[0] != "item" or e["key"] in seen:
            continue
        seen.add(e["key"])
        rec = (e.get("data") or {}).get("record") or {}
        rows.append({"number": int(e["key"]), "kind": rec.get("kind"), "module": rec.get("module"),
                     "node": rec.get("node"), "source": src})
    return rows


def map_crew(db: store.Store, number: int) -> dict | None:
    """The source a crew record was approved through, or None when it was the user in this session."""
    for e in reversed(store.events(db, key=str(number), kind="item")):
        src = (e.get("data") or {}).get("source")
        if src:
            return src
    return None

