"""Coordinator bookkeeping for incoming wait-type messages and relayed answers (see spec/crew-onboarding.md).

The session only follows instructions; these functions judge each message,
record it in the store, and say what to send back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from module_crew import protocol, store

RECORDED_HERE = ("wait-user", "wait-session", "resumed", "withdraw")
RECORDED_ELSEWHERE = {"review-request": "crew-review-batch", "shared-change-request": "crew-shared-changes"}


@dataclass
class Outcome:
    kind: str
    code: int                                  # 0 recorded / 3 rejected / 4 not recorded here
    number: int | None = None                  # new record number
    closed: list[int] = field(default_factory=list)
    unmatched: list[int] = field(default_factory=list)
    tell_sender: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)


def _active_dev(db: store.Store, sender: str) -> bool:
    rec = store.get(db, "session", sender)
    return bool(rec) and rec.get("role") == "dev" and rec.get("status") == "active"


def add(db: store.Store, text: str, sender: str, relay_id: int) -> Outcome:
    """Judge one incoming message and record it; nothing is written unless the code is 0."""
    msg = protocol.parse(text)
    if not _active_dev(db, sender):
        return Outcome(msg.kind, 3, lines=[f"发件人 {sender} 不是状态库里登记的在用模块会话，拒收"])
    if not msg.supported or not msg.ok:
        reasons = list(msg.problems) or [f"{msg.kind} 第一版不处理"]
        return Outcome(msg.kind, 3, lines=["消息不合格，请退回：" + "、".join(reasons)])
    if msg.kind in RECORDED_ELSEWHERE:
        return Outcome(msg.kind, 4, lines=[f"合格；{msg.kind} 由 {RECORDED_ELSEWHERE[msg.kind]} 记账，本命令不记"])
    if msg.kind not in RECORDED_HERE:
        return Outcome(msg.kind, 3, lines=[f"{msg.kind} 不应由模块会话发来，拒收"])
    with db.transaction(actor=sender) as tx:
        out = Outcome(msg.kind, 0)
        if any(e["actor"] == sender and e["data"].get("relayId") == relay_id for e in store.events(db)):
            out.lines.append(f"已记过：{sender} 的邮箱消息 #{relay_id}，没有重复记账")
            return out
        if msg.kind in ("wait-user", "wait-session"):
            _close_tickets(tx, sender, msg.end.items, 2, relay_id, out)
        if msg.kind == "wait-user":
            _wait_user(tx, msg, text, sender, relay_id, out)
        elif msg.kind == "wait-session":
            n = tx.allocate_number()
            tx.put("ticket", str(n), {
                "state": "open", "from": sender, "relayId": relay_id, "text": text,
                "waitingFor": msg.fields.get("在等谁", "").strip(), "what": msg.fields.get("等什么", ""),
                "closedReason": None, "closedBy": None,
            }, action="opened", data={"relayId": relay_id})
            out.number = n
            out.lines.append(f"已记为等待单 #{n}")
        elif msg.kind == "resumed":
            _close_tickets(tx, sender, msg.end.items, 1, relay_id, out)
            if msg.end.unnumbered_reason:
                out.lines.append(f"对方没给编号：{msg.end.unnumbered_reason}；请核对是哪张等待单")
        elif msg.kind == "withdraw":
            items = tx.records("item")
            key = _find(items, sender, msg.item)
            if key and items[key]["state"] == "open":
                _close_item(tx, key, "withdrawn", relay_id, out)
            else:
                out.unmatched.append(msg.item)
        if out.closed:
            out.lines.append("已关闭 " + "、".join(f"#{n}" for n in out.closed))
        return out


def _close_tickets(tx, sender: str, refs, reason: int, by: int, out: Outcome) -> None:
    """Close the sender's open tickets named in a 结束 line (contract section 11 reasons)."""
    tickets = tx.records("ticket")
    for n in refs:
        key = _find(tickets, sender, n)
        if key and tickets[key]["state"] == "open":
            rec = dict(tickets[key], state="closed", closedReason=reason, closedBy=by)
            tx.put("ticket", key, rec, action="closed", data={"relayId": by, "reason": reason})
            tickets[key] = rec
            out.closed.append(int(key))
        else:
            out.unmatched.append(n)


def _find(records: dict, sender: str, n: int) -> str | None:
    """Key of the sender's record #n: store number first, then the sender's own relay id."""
    rec = records.get(str(n))
    if rec is not None and rec.get("from") == sender:
        return str(n)
    for key, rec in records.items():
        if rec.get("from") == sender and rec.get("relayId") == n:
            return key
    return None


def _close_item(tx, key: str, reason: str, by: int, out: Outcome) -> None:
    rec = dict(tx.get("item", key), state="closed", closedReason=reason)
    tx.put("item", key, rec, action=reason, data={"relayId": by})
    out.closed.append(int(key))


def _wait_user(tx, msg: protocol.Message, text: str, sender: str, relay_id: int, out: Outcome) -> None:
    doc = msg.contract()
    items = tx.records("item")
    multiline = bool(doc["linesInScope"])
    parallel = {n for kind, n in msg.markers if kind == "parallel"}
    explicit = [n for kind, n in msg.markers if kind == "supersede"]
    if explicit:
        for n in explicit:
            key = _find(items, sender, n)
            if key and items[key]["state"] == "open":
                _close_item(tx, key, "superseded", relay_id, out)
            else:
                out.unmatched.append(n)
    else:
        keep = {_find(items, sender, n) for n in parallel}
        for key, rec in sorted(items.items(), key=lambda kv: int(kv[0])):
            if (rec.get("from") == sender and rec.get("state") == "open" and rec.get("kind") == "wait-user"
                    and rec.get("multiline") == multiline and key not in keep):
                _close_item(tx, key, "superseded", relay_id, out)
                out.tell_sender.append(f"#{key} 已被新事项自动取代；确实要两项都答，请写【与 #{key} 并行】重发")
    n = tx.allocate_number()
    tx.put("item", str(n), {
        "state": "open", "kind": "wait-user", "from": sender, "relayId": relay_id, "text": text,
        "decide": msg.fields.get("要你决定", ""),
        "options": [{"letter": o["letter"], "text": o["text"]} for o in doc["options"]],
        "recommended": doc["recommended"], "fullyStopped": doc["fullyStopped"],
        "multiline": multiline, "closedReason": None, "answer": None,
    }, action="created", data={"relayId": relay_id})
    out.number = n
    out.lines.append(f"已记为事项 #{n}")


class AnswerRefused(Exception):
    """The answer cannot be recorded; nothing was written."""


@dataclass(frozen=True)
class Reply:
    to: str
    reply_to: int
    body: int
    path: Path


def answer(db: store.Store, number: int, original: str, option: str | None = None) -> Reply:
    """Render 【用户答复】 for an open item, store the body and close the item in one transaction."""
    with db.transaction(actor="coordinator") as tx:
        item = tx.get("item", str(number))
        if item is None:
            raise AnswerRefused(f"没有事项 #{number}")
        if item.get("state") != "open":
            raise AnswerRefused(f"事项 #{number} 已关闭（{item.get('closedReason')}），不能再答")
        option_text = None
        if option is not None:
            match = [o for o in item.get("options", []) if o["letter"] == option.strip().upper()]
            if not match:
                raise AnswerRefused(f"事项 #{number} 没有选项 {option}")
            option_text = f"{match[0]['letter']}：{match[0]['text']}"
        answered_at = store.now()
        try:
            text = protocol.render_user_reply(item=number, original=original, answered_at=answered_at,
                                              option_text=option_text, source_relay_id=item["relayId"])
        except ValueError as exc:
            raise AnswerRefused(str(exc)) from exc
        body = tx.allocate_number()
        meta = tx.write_body(body, text)
        closed = dict(item, state="closed", closedReason="answered",
                      answer={"original": original, **store.source_field(), "option": option_text[0] if option_text else None,
                              "answeredAt": answered_at, "body": body})
        tx.put("item", str(number), closed, action="answered", data={"body": body})
    return Reply(item["from"], item["relayId"], body, db.path / meta["path"])


TICKET_REASONS = {"happened": 3, "user": 4}  # contract section 11: 3 what was waited for happened, 4 the user closed it


def close_ticket(db: store.Store, number: int, reason: str, original: str) -> int:
    """Close an open waiting ticket on the coordinator's side; returns the contract reason code."""
    code = TICKET_REASONS.get(reason)
    if code is None:
        raise AnswerRefused(f"关单理由只能是 {'／'.join(TICKET_REASONS)}")
    if not original or not original.strip():
        raise AnswerRefused("说明不能为空：happened 写清所等的事怎样发生了，user 写用户原话")
    with db.transaction(actor="coordinator") as tx:
        rec = tx.get("ticket", str(number))
        if rec is None:
            raise AnswerRefused(f"没有等待单 #{number}")
        if rec.get("state") != "open":
            raise AnswerRefused(f"等待单 #{number} 已关闭（理由 {rec.get('closedReason')}）")
        tx.put("ticket", str(number), dict(rec, state="closed", closedReason=code, closedBy="coordinator"),
               action="closed", data={"reason": code, "note": original})
    return code
