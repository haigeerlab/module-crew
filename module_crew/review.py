"""Batch review of 【交审】: record, list, answer, and approve onto the integration baseline
(see spec/crew-review-batch.md).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from module_crew import probe, protocol, store
from module_crew.inbox import AnswerRefused, Outcome, Reply


def _session(db: store.Store, sender: str) -> dict | None:
    rec = store.get(db, "session", sender)
    return rec if rec and rec.get("role") == "dev" and rec.get("status") == "active" else None


def _git(cwd: Path, *args: str):
    return probe._git(cwd, *args)


def _check_files(worktree: Path, files: list[dict]) -> list[str]:
    """Refusal reasons for the submitted files: tracked, committed, fingerprint is a prefix of sha256."""
    reasons = []
    for f in files:
        path = f["path"]
        if (_git(worktree, "ls-files", "--error-unmatch", "--", path).returncode != 0
                or _git(worktree, "diff", "--quiet", "HEAD", "--", path).returncode != 0):
            reasons.append(f"{path} 未提交（交审前要先提交到模块分支）")
            continue
        digest = hashlib.sha256((worktree / path).read_bytes()).hexdigest()
        if not digest.startswith(f["fingerprint"].removeprefix("sha256:")):
            reasons.append(f"{path} 的指纹与文件不符")
    return reasons


def add(db: store.Store, text: str, sender: str, relay_id: int) -> Outcome:
    """Judge one 【交审】 and record it; nothing is written unless the code is 0."""
    msg = protocol.parse(text)
    session = _session(db, sender)
    if session is None:
        return Outcome(msg.kind, 3, lines=[f"发件人 {sender} 不是状态库里登记的在用模块会话，拒收"])
    if msg.kind != "review-request":
        return Outcome(msg.kind, 3, lines=[f"这不是【交审】（{msg.kind}），请用 inbox add"])
    if not msg.ok:
        return Outcome(msg.kind, 3, lines=["消息不合格，请退回：" + "、".join(msg.problems)])
    sub = msg.contract()["submission"]
    if sub["module"] != session.get("module"):
        return Outcome(msg.kind, 3, lines=[f"交审的模块 {sub['module']} 不是 {sender} 负责的模块 {session.get('module')}"])
    worktree = Path(session["worktree"])
    reasons = _check_files(worktree, sub["files"])
    if reasons:
        return Outcome(msg.kind, 3, lines=["拒收，请退回："] + reasons)
    commit = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    with db.transaction(actor=sender) as tx:
        out = Outcome(msg.kind, 0)
        if any(e["actor"] == sender and e["data"].get("relayId") == relay_id for e in store.events(db)):
            out.lines.append(f"已记过：{sender} 的邮箱消息 #{relay_id}，没有重复记账")
            return out
        for key, rec in sorted(tx.records("item").items(), key=lambda kv: int(kv[0])):
            if (rec.get("kind") == "review" and rec.get("state") == "open" and rec.get("module") == sub["module"]
                    and rec.get("node") == sub["node"]):
                tx.put("item", key, dict(rec, state="closed", closedReason="superseded"), action="superseded",
                       data={"relayId": relay_id})
                out.closed.append(int(key))
        n = tx.allocate_number()
        tx.put("item", str(n), {
            "state": "open", "kind": "review", "from": sender, "relayId": relay_id, "text": text,
            "module": sub["module"], "node": sub["node"], "files": sub["files"], "commit": commit,
            "closedReason": None, "answer": None,
        }, action="created", data={"relayId": relay_id})
        out.number = n
        out.lines.append(f"已记为交审事项 #{n}（{sub['module']} 的 {msg.fields.get('节点', '').strip()}）")
        if out.closed:
            out.lines.append("取代了 " + "、".join(f"#{k}" for k in out.closed))
        return out


def _points(text: str) -> str:
    return protocol.parse(text).fields.get("要点", "")


def _approved_nodes(db: store.Store) -> dict[str, set[str]]:
    """Modules -> nodes already approved through a review-approval."""
    items = store.records(db, "item")
    approved: dict[str, set[str]] = {}
    for rec in items.values():
        if rec.get("kind") == "review-approval":
            for n in rec.get("reviews", []):
                r = items.get(str(n)) or {}
                approved.setdefault(r.get("module"), set()).add(r.get("node"))
    return approved


def batch(project: str | os.PathLike) -> dict:
    """Read-only view of the open reviews, their dependency check and relevant conflicts."""
    project = Path(project)
    db = store.open_store(project)
    open_items = sorted(((int(k), v) for k, v in store.records(db, "item").items()
                         if v.get("kind") == "review" and v.get("state") == "open"), key=lambda kv: kv[0])
    report = probe.run(project)
    modules = {m.get("id"): m for m in (report.map or {}).get("modules") or [] if isinstance(m, dict)}
    approved = _approved_nodes(db)
    in_batch = {v["module"] for _, v in open_items if v["node"] in ("spec", "interface")}
    issues = []
    for mod in dict.fromkeys(v["module"] for _, v in open_items):
        missing = [d for d in modules.get(mod, {}).get("dependsOn") or []
                   if modules.get(d, {}).get("status") != "done" and d not in in_batch
                   and not ({"spec", "interface"} & approved.get(d, set()))]
        if missing:
            issues.append({"module": mod, "missing": missing})
    batch_mods = {v["module"] for _, v in open_items}
    conflicts = [c for c in (report.map or {}).get("startable", {}).get("conflicts", [])
                 if batch_mods & set(c.get("modules", []))]
    return {"items": [{"number": n, "module": v["module"], "node": v["node"], "from": v["from"],
                       "files": v["files"], "points": _points(v["text"])} for n, v in open_items],
            "dependencyIssues": issues, "conflicts": conflicts}


def _reply_text(item_no: int, rec: dict, original: str, answered_at: str) -> str:
    try:
        return protocol.render_user_reply(item=item_no, original=original, answered_at=answered_at,
                                          source_relay_id=rec["relayId"])
    except ValueError as exc:
        raise AnswerRefused(str(exc)) from exc


def answer(db: store.Store, number: int, original: str) -> Reply:
    """【用户答复】 for one open review (e.g. changes required); the baseline is not touched."""
    with db.transaction(actor="coordinator") as tx:
        rec = tx.get("item", str(number))
        if rec is None or rec.get("kind") != "review":
            raise AnswerRefused(f"没有交审事项 #{number}")
        if rec.get("state") != "open":
            raise AnswerRefused(f"交审事项 #{number} 已关闭（{rec.get('closedReason')}）")
        answered_at = store.now()
        text = _reply_text(number, rec, original, answered_at)
        body = tx.allocate_number()
        meta = tx.write_body(body, text)
        tx.put("item", str(number), dict(rec, state="closed", closedReason="answered",
                                         answer={"original": original, "answeredAt": answered_at, "body": body}),
               action="answered", data={"body": body})
    return Reply(rec["from"], rec["relayId"], body, db.path / meta["path"])
