"""Approval sources besides the coordinator's own user (see spec/crew-hub-bridge.md).

The user, in the coordinating session, whitelists the relay names that may carry their decisions: a decision
inbox hub (`hub`) or a designated lead such as a review session (`lead`).  An approval that names such a source
must come with that session's message; the user's words are read out of it, never retyped by the coordinator.
"""

from __future__ import annotations

from dataclasses import dataclass

from module_crew import protocol, store

KINDS = ("hub", "lead")
PROTOCOLS = ("2.2", "2.3", "2.4", "2.5")   # session-protocol versions a decision inbox may speak (crew-hub-card-fields)
OLDEST_HUB = "2.4"                      # 0.9.5: every inbox here speaks v2.3+; unset or 2.2 registrations count as 2.4
NODES = ("spec", "plan", "interface", "final")       # review nodes a reviewer can be responsible for (crew-routing-fixes)
ALL = "all"
ALL_WORDS = ("all", "全部")
ALL_SCOPE = {"modules": ALL, "nodes": ALL}


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


def parse_scope(modules: str | None, nodes: str | None) -> dict:
    """A reviewer's responsibility from the command line: comma lists, or 全部／all spelled out."""
    def one(raw: str | None, what: str, allowed: tuple[str, ...] | None) -> str | list[str]:
        if raw is None or not raw.strip():
            raise SourceRefused(f"审查者必须写负责的{what}（要全部也写「全部」）：问清用户再登记")
        if raw.strip() in ALL_WORDS:
            return ALL
        items = [x.strip() for x in raw.replace("，", ",").split(",") if x.strip()]
        bad = [x for x in items if allowed is not None and x not in allowed]
        if bad:
            raise SourceRefused(f"{what}只能是 {'／'.join(allowed)} 或「全部」，收到：{'、'.join(bad)}")
        return sorted(dict.fromkeys(items))
    return {"modules": one(modules, "模块", None), "nodes": one(nodes, "节点", NODES)}


def _valid_scope(scope) -> bool:
    return (isinstance(scope, dict)
            and all(scope.get(k) == ALL or (isinstance(scope.get(k), list) and scope.get(k)) for k in ("modules", "nodes")))


def covers(row: dict, module: str, node: str) -> bool:
    """Whether a lead row's registered scope covers this module's node; a row without a scope covers nothing."""
    scope = row.get("scope")
    if not _valid_scope(scope):
        return False
    return all(scope[k] == ALL or v in scope[k] for k, v in (("modules", module), ("nodes", node)))


def scope_text(scope) -> str:
    if not _valid_scope(scope):
        return "未登记负责范围"
    show = lambda v: "全部" if v == ALL else "、".join(v)
    return f"模块 {show(scope['modules'])} × 节点 {show(scope['nodes'])}"


def _overlaps(a: dict, b: dict) -> bool:
    return all(a[k] == ALL or b[k] == ALL or set(a[k]) & set(b[k]) for k in ("modules", "nodes"))


def _overlap_lines(rows: list[dict], name: str, scope: dict) -> list[str]:
    return [f"提示：{name} 的负责范围和 {r['name']}（{scope_text(r['scope'])}）重叠，重叠部分的交审两个都会收到"
            for r in rows if r.get("kind") == "lead" and r.get("name") != name and _valid_scope(r.get("scope"))
            and _overlaps(scope, r["scope"])]


def add(db: store.Store, name: str, kind: str, original: str, protocol: str | None = None,
        scope: dict | None = None) -> list[str]:
    """Whitelist a source; a lead must come with its scope. Returns notes to show (scope overlaps)."""
    _need(original)
    if kind not in KINDS:
        raise SourceRefused(f"来源种类只能是 {'／'.join(KINDS)}")
    if protocol is not None and protocol not in PROTOCOLS:
        raise SourceRefused(f"契约版本只能是 {'／'.join(PROTOCOLS)}")
    if protocol is not None and kind != "hub":
        raise SourceRefused("只有决策收件箱（hub）才登记契约版本")
    if protocol == "2.2":
        raise SourceRefused("决策收件箱已全部是 v2.3 以上，不再按 2.2 登记：不写 --protocol（按 2.4）或写 2.3／2.4")
    if kind == "lead" and not _valid_scope(scope):
        raise SourceRefused("审查者必须写负责范围（--modules 与 --nodes，要全部也写「全部」）：问清用户再登记")
    if kind != "lead" and scope is not None:
        raise SourceRefused("只有审查者（lead）才登记负责范围")
    if not name or not name.strip():
        raise SourceRefused("来源的邮箱名不能为空")
    with db.transaction(actor="coordinator") as tx:
        cfg = tx.get("config", "main") or {}
        rows = list(cfg.get("sources") or [])
        if any(r.get("name") == name for r in rows):
            raise SourceRefused(f"{name} 已经登记为来源")
        row = {"name": name, "kind": kind, "addedAt": store.now(), "original": original}
        if protocol is not None:
            row["protocol"] = protocol
        if scope is not None:
            row["scope"] = scope
        notes = _overlap_lines(rows, name, scope) if scope is not None else []
        rows.append(row)
        tx.put("config", "main", {**cfg, "sources": rows}, action="source-added", data={"name": name, "kind": kind})
    return notes


def set_scope(db: store.Store, name: str, scope: dict, original: str) -> list[str]:
    """Record or change a registered reviewer's scope (also how a pre-0.9.0 lead gets one)."""
    _need(original)
    if not _valid_scope(scope):
        raise SourceRefused("负责范围要同时写模块和节点")
    with db.transaction(actor="coordinator") as tx:
        cfg = tx.get("config", "main") or {}
        rows = list(cfg.get("sources") or [])
        row = next((r for r in rows if r.get("name") == name), None)
        if row is None:
            raise SourceRefused(f"{name} 没有登记为来源")
        if row.get("kind") != "lead":
            raise SourceRefused(f"{name} 不是审查者（lead），没有负责范围")
        notes = _overlap_lines(rows, name, scope)
        rows = [dict(r, scope=scope) if r.get("name") == name else r for r in rows]
        tx.put("config", "main", {**cfg, "sources": rows}, action="source-scoped",
               data={"name": name, "scope": scope, "original": original})
    return notes


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


def hub_protocol(row: dict) -> str:
    """The contract version module-crew writes to a registered hub: as registered, unset or 2.2 counting as 2.4 (0.9.5)."""
    got = row.get("protocol")
    return got if got in ("2.3", "2.4", "2.5") else OLDEST_HUB


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

