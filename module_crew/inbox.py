"""Coordinator bookkeeping for incoming wait-type messages and relayed answers (see spec/crew-onboarding.md).

The session only follows instructions; these functions judge each message,
record it in the store, and say what to send back.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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
        if msg.kind == "wait-user":
            _wait_user(tx, msg, text, sender, relay_id, out)
        return out


def _wait_user(tx, msg: protocol.Message, text: str, sender: str, relay_id: int, out: Outcome) -> None:
    doc = msg.contract()
    n = tx.allocate_number()
    tx.put("item", str(n), {
        "state": "open", "kind": "wait-user", "from": sender, "relayId": relay_id, "text": text,
        "decide": msg.fields.get("要你决定", ""),
        "options": [{"letter": o["letter"], "text": o["text"]} for o in doc["options"]],
        "recommended": doc["recommended"], "fullyStopped": doc["fullyStopped"],
        "multiline": bool(doc["linesInScope"]), "closedReason": None, "answer": None,
    }, action="created", data={"relayId": relay_id})
    out.number = n
    out.lines.append(f"已记为事项 #{n}")
