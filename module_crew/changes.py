"""【公共变更请求】: record, hint, land on the integration baseline, or decline (see spec/crew-shared-changes.md)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from module_crew import probe, protocol, store
from module_crew.inbox import AnswerRefused, Outcome, Reply

# Routing hints (spec decision 4); only ever added to.
DEPENDENCY_FILES = {"package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "pyproject.toml", "poetry.lock",
                    "Cargo.toml", "Cargo.lock", "go.mod", "go.sum", "Gemfile", "Gemfile.lock"}
CI_PREFIXES = (".github/", ".gitlab-ci.yml", ".circleci/")
ASK_USER = ("dependency", "ci", "migration", "conflict:")


def hints_for(files: list[str], others: dict[str, list[str]]) -> list[str]:
    """Hints for one request; `others` maps open request numbers to their file lists."""
    hints = []
    names = [PurePosixPath(f).name for f in files]
    if any(n in DEPENDENCY_FILES or (n.startswith("requirements") and n.endswith(".txt")) for n in names):
        hints.append("dependency")
    if any(f.startswith(CI_PREFIXES) for f in files):
        hints.append("ci")
    if any("migration" in f.lower() for f in files):
        hints.append("migration")
    hints += [f"conflict:{n}" for n, theirs in others.items() if set(files) & set(theirs)]
    return hints


def _asks_user(hints: list[str]) -> bool:
    return any(h.startswith(ASK_USER) for h in hints)


def _active(db: store.Store, sender: str) -> bool:
    rec = store.get(db, "session", sender)
    return bool(rec) and rec.get("role") == "dev" and rec.get("status") == "active"


def add(db: store.Store, text: str, sender: str, relay_id: int) -> Outcome:
    msg = protocol.parse(text)
    if not _active(db, sender):
        return Outcome(msg.kind, 3, lines=[f"发件人 {sender} 不是状态库里登记的在用模块会话，拒收"])
    if msg.kind != "shared-change-request":
        return Outcome(msg.kind, 3, lines=[f"这不是【公共变更请求】（{msg.kind}）"])
    if not msg.ok:
        return Outcome(msg.kind, 3, lines=["消息不合格，请退回：" + "、".join(msg.problems)])
    doc = msg.contract()
    req_files = doc["changeRequest"]["files"]
    with db.transaction(actor=sender) as tx:
        out = Outcome(msg.kind, 0)
        if any(e["actor"] == sender and e["data"].get("relayId") == relay_id for e in store.events(db)):
            out.lines.append(f"已记过：{sender} 的邮箱消息 #{relay_id}，没有重复记账")
            return out
        open_reqs = {k: v for k, v in tx.records("request").items() if v.get("state") == "open"}
        hints = hints_for(req_files, {k: v["files"] for k, v in open_reqs.items()})
        ticket = None
        if doc["fullyStopped"]:
            coord = next((k for k, v in tx.records("session").items()
                          if v.get("role") == "coordinator" and v.get("status") == "active"), "coordinator")
            ticket = tx.allocate_number()
            tx.put("ticket", str(ticket), {
                "state": "open", "from": sender, "relayId": relay_id, "text": text, "waitingFor": coord,
                "what": "公共变更请求的处理结果", "closedReason": None, "closedBy": None,
            }, action="opened", data={"relayId": relay_id})
        n = tx.allocate_number()
        for k in (k for k, v in open_reqs.items() if set(req_files) & set(v["files"])):
            tx.put("request", k, dict(open_reqs[k], hints=open_reqs[k]["hints"] + [f"conflict:{n}"]),
                   action="hinted", data={"relayId": relay_id})
        tx.put("request", str(n), {
            "state": "open", "from": sender, "relayId": relay_id, "text": text, "files": req_files,
            "what": msg.fields.get("改什么", ""), "why": msg.fields.get("为什么", ""),
            "fullyStopped": doc["fullyStopped"], "hints": hints, "ticket": ticket,
            "closedReason": None, "commit": None, "answer": None,
        }, action="created", data={"relayId": relay_id})
        out.number = n
        out.lines.append(f"已记为公共变更请求 #{n}" + (f"，等待单 #{ticket}" if ticket else ""))
        if hints:
            out.lines.append("提示：" + "、".join(hints))
        out.lines.append("要问用户" if _asks_user(hints) else "可由协调会话判断是否在已批准 Spec 范围内直接办")
        return out


def pending(db: store.Store) -> list[tuple[int, dict]]:
    return sorted(((int(k), v) for k, v in store.records(db, "request").items() if v.get("state") == "open"),
                  key=lambda kv: kv[0])


def _close_ticket(tx, rec: dict) -> None:
    if rec.get("ticket"):
        t = tx.get("ticket", str(rec["ticket"]))
        if t and t.get("state") == "open":
            tx.put("ticket", str(rec["ticket"]), dict(t, state="closed", closedReason=3), action="closed",
                   data={"reason": 3})


def answer(db: store.Store, number: int, original: str) -> Reply:
    """Decline a request with the user's words; the baseline is not touched."""
    with db.transaction(actor="coordinator") as tx:
        rec = tx.get("request", str(number))
        if rec is None:
            raise AnswerRefused(f"没有公共变更请求 #{number}")
        if rec.get("state") != "open":
            raise AnswerRefused(f"公共变更请求 #{number} 已关闭（{rec.get('closedReason')}）")
        answered_at = store.now()
        try:
            text = protocol.render_user_reply(item=number, original=original, answered_at=answered_at,
                                              source_relay_id=rec["relayId"])
        except ValueError as exc:
            raise AnswerRefused(str(exc)) from exc
        body = tx.allocate_number()
        meta = tx.write_body(body, text)
        tx.put("request", str(number), dict(rec, state="closed", closedReason="declined",
                                            answer={"original": original, "answeredAt": answered_at, "body": body}),
               action="declined", data={"body": body})
        _close_ticket(tx, rec)
    return Reply(rec["from"], rec["relayId"], body, db.path / meta["path"])
