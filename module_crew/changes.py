"""【公共变更请求】: record, hint, land on the integration baseline, or decline (see spec/crew-shared-changes.md)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from module_crew import commits, probe, protocol, store, sync
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
        out.lines.append(f"已记为公共变更请求 C{n}" + (f"，等待记录 W{ticket}" if ticket else ""))
        if hints:
            out.lines.append("提示：" + "、".join(hints))
        out.lines.append("要问用户" if _asks_user(hints) else "可由模块协调判断是否在已批准 Spec 范围内直接办")
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
            raise AnswerRefused(f"没有公共变更请求 C{number}")
        if rec.get("state") != "open":
            raise AnswerRefused(f"公共变更请求 C{number} 已关闭（{rec.get('closedReason')}）")
        answered_at = store.now()
        try:
            text = protocol.render_user_reply(item=number, original=original, answered_at=answered_at,
                                              source_relay_id=rec["relayId"], crew=True)
        except ValueError as exc:
            raise AnswerRefused(str(exc)) from exc
        body = tx.allocate_number()
        meta = tx.write_body(body, text)
        tx.put("request", str(number), dict(rec, state="closed", closedReason="declined",
                                            answer={"original": original, "answeredAt": answered_at, **store.source_field(), "body": body}),
               action="declined", data={"body": body})
        _close_ticket(tx, rec)
    return Reply(rec["from"], rec["relayId"], body, db.path / meta["path"])


@dataclass
class LandResult:
    code: int                                     # 0 done / 3 refused, nothing changed / 4 commit failed
    lines: list[str] = field(default_factory=list)
    commit: str | None = None
    sends: list[dict] = field(default_factory=list)   # {"to", "replyTo", "body", "path"}


def _changed_paths(checkout: Path) -> list[str]:
    """Every path git reports as changed or untracked, both sides of renames included."""
    raw = probe._git(checkout, "--no-optional-locks", "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    entries = raw.split("\0")
    paths, i = [], 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        paths.append(path)
        if "R" in status or "C" in status:
            paths.append(entries[i])
            i += 1
    return paths


def land(project: str | os.PathLike, number: int, original: str | None = None) -> LandResult:
    """Commit the coordinator's edits for one request on the integration baseline and prepare the notices."""
    project = Path(project)
    db = store.open_store(project)
    rec = store.get(db, "request", str(number))
    if rec is None:
        return LandResult(3, [f"没有公共变更请求 C{number}"])
    if rec.get("state") != "open":
        return LandResult(3, [f"公共变更请求 C{number} 已关闭（{rec.get('closedReason')}）"])
    cfg = store.get(db, "config", "main") or {}
    checkout = probe._checkout_of(project, cfg.get("integrationBranch", "")) if cfg else None
    if checkout is None:
        return LandResult(3, ["找不到集成分支所在的 checkout"])
    changed = _changed_paths(checkout)
    outside = [p for p in changed if p not in rec["files"]]
    if outside:
        return LandResult(3, ["集成 checkout 里有清单外的改动，没有提交：" + "、".join(outside)])
    if not changed:
        return LandResult(3, [f"清单里的文件都没有改动：{'、'.join(rec['files'])}"])
    probe._git(checkout, "add", "-A", "--", *changed)
    done = probe._git(checkout, "commit", "-q", "-m",
                      commits.message(f"公共变更请求 C{number}（{rec['from']}）：{rec['what'][:40]}"))
    if done.returncode != 0:
        return LandResult(4, [commits.failure(checkout, done, "集成分支提交失败"), "已暂存的文件：" + "、".join(changed)])
    commit = probe._git(checkout, "rev-parse", "HEAD").stdout.strip()
    result = LandResult(0, commit=commit)
    result.lines.append(f"公共变更请求 C{number} 已在集成分支提交 {commit[:7]}")
    if original is None and _asks_user(rec.get("hints", [])):
        result.lines.append("提醒：这条请求带「要问用户」提示，但没有记下用户原话")
    basis = f"公共变更请求 C{number} 已在集成分支提交 {commit[:7]}"
    todo = f"{sync.STEP}，跑完整检查后继续"
    with db.transaction(actor="coordinator") as tx:
        answer_rec = {"original": original, "answeredAt": store.now(), **store.source_field()} if original is not None else None
        tx.put("request", str(number), dict(rec, state="closed", closedReason="landed", commit=commit, answer=answer_rec),
               action="landed", data={"commit": commit})
        _close_ticket(tx, rec)
        from module_crew import merge
        waiting = merge.awaiting_final(tx)     # MC-10: they sync after their final acceptance is settled
        for name, sess in sorted(tx.records("session").items()):
            if sess.get("role") != "dev" or sess.get("status") != "active":
                continue
            if sess.get("module") in waiting and name != rec["from"]:
                continue
            text = protocol.render_coordination_notice(kind="sync-baseline", basis=basis, todo=todo)
            reply_to = rec["relayId"] if name == rec["from"] else None
            if reply_to is not None:
                text = f"回复：#{reply_to}\n" + text
                if protocol.parse(text).reply_to != reply_to:
                    raise ValueError("回复行没有被读回")
            body = tx.allocate_number()
            meta = tx.write_body(body, text)
            result.sends.append({"to": name, "replyTo": reply_to, "body": body, "path": db.path / meta["path"]})
    return result
