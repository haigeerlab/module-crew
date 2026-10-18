"""Batch review of 【交审】: record, list, answer, and approve onto the integration baseline
(see spec/crew-review-batch.md).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass, field
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


APPROVABLE = ("spec", "plan", "interface")
MARK_TARGET = {"spec": "spec", "interface": "spec", "plan": "plan"}
NODE_NAME = {"spec": "Spec", "plan": "Plan", "interface": "接口提案"}


@dataclass
class ApproveResult:
    code: int                                     # 0 done / 3 refused, nothing changed / 4 stopped part-way
    lines: list[str] = field(default_factory=list)
    approval: int | None = None
    commit: str | None = None
    sends: list[dict] = field(default_factory=list)   # {"kind", "to", "replyTo", "body", "path"}


def _next_number(db: store.Store) -> int:
    return max((int(e["key"]) for e in store.events(db)
                if e["type"].split(".")[0] in store.NUMBERED and e["key"].isdigit()), default=0) + 1


def _mark_command(project: Path) -> tuple[Path, dict] | str:
    found = probe.find_plugin("spec-guard", project)
    if isinstance(found, str):
        return found
    doc = probe.read_interface(found.root, probe.SPEC_GUARD_MAJOR)
    if isinstance(doc, str):
        return doc
    if "reviewMark" not in doc:
        return "spec-guard 的 interface.json 没有 reviewMark 入口（需要 interface 1.1）"
    probe_cmd = probe.safe_command(found.root, doc, "reviewMark", _mark_fill(Path("."), "m", "spec"))
    if isinstance(probe_cmd, str):
        return probe_cmd
    left = [x for x in probe_cmd if x.startswith("<") and x.endswith(">")]
    if left:
        return f"reviewMark.command 有不认识的占位符 {'、'.join(left)}（按 interface 1.1 应为 <spec|plan|both>、<pending|approved>），没有运行"
    return found.root, doc


def _mark_fill(checkout: Path, module: str, target: str) -> dict[str, str]:
    """Placeholders of interface 1.1 reviewMark.command."""
    return {"<project-root>": str(checkout), "<module-id>": module,
            "<spec|plan|both>": target, "<pending|approved>": "approved"}


def approve(project: str | os.PathLike, numbers: list[int], original: str) -> ApproveResult:
    """Land the approved Spec/Plan files on the integration baseline and prepare all replies and notices."""
    project = Path(project)
    db = store.open_store(project)
    items = store.records(db, "item")
    reasons = []
    if not original or not original.strip():
        reasons.append("用户原话不能为空：只记用户在本会话亲手输入的话")
    picked = []
    for n in numbers:
        rec = items.get(str(n))
        if rec is None or rec.get("kind") != "review":
            reasons.append(f"没有交审事项 #{n}")
        elif rec.get("state") != "open":
            reasons.append(f"交审事项 #{n} 已关闭（{rec.get('closedReason')}）")
        elif rec.get("node") not in APPROVABLE:
            reasons.append(f"交审事项 #{n} 是最终验收：用 review answer 答复，合并归 crew-merge")
        else:
            picked.append((n, rec))
    baseline = probe.check_baseline(project)
    if baseline.state != "ok":
        reasons.append(baseline.reason)
    mark = _mark_command(project)
    if isinstance(mark, str):
        reasons.append(mark)
    cfg = store.get(db, "config", "main") or {}
    checkout = probe._checkout_of(project, cfg.get("integrationBranch", "")) if cfg else None
    if checkout is None:
        reasons.append("找不到集成分支所在的 checkout（还没有 start prepare？）")
    contents = []
    for n, rec in picked:
        wt = Path((store.get(db, "session", rec["from"]) or {}).get("worktree", "/nonexistent"))
        for f in rec["files"]:
            shown = subprocess.run(["git", "-C", str(wt), "show", f"{rec['commit']}:{f['path']}"], capture_output=True)
            if shown.returncode != 0:
                reasons.append(f"#{n} 的 {f['path']} 从提交 {rec['commit'][:7]} 里取不出")
            else:
                contents.append((f["path"], shown.stdout))
    if reasons:
        return ApproveResult(3, ["没有执行，原因："] + reasons)

    root, doc = mark
    written = []
    for path, data in contents:
        target = checkout / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written.append(path)
    for n, rec in picked:
        cmd = probe.safe_command(root, doc, "reviewMark", _mark_fill(checkout, rec["module"], MARK_TARGET[rec["node"]])) + ["--confirm"]
        ran = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=probe.MAP_TIMEOUT)
        if ran.returncode != 0:
            return ApproveResult(4, [f"#{n}（{rec['module']}）写评审标记失败，已停下：{ran.stderr.strip()[:200]}",
                                     "集成 checkout 里已改、未提交的文件：" + "、".join(written),
                                     "状态库与集成分支都没有变化；这些文件留着，交用户决定"])
    approval_no = _next_number(db)
    modules = list(dict.fromkeys(rec["module"] for _, rec in picked))
    nodes = "、".join(f"{rec['module']} 的 {NODE_NAME[rec['node']]}" for _, rec in picked)
    _git(checkout, "add", "--", *written)
    commit_run = _git(checkout, "commit", "-q", "-m", f"协调会话：批准 {nodes}（用户批准事项 #{approval_no}）")
    if commit_run.returncode != 0:
        return ApproveResult(4, [f"集成分支提交失败：{commit_run.stderr.strip()[:200]}",
                                 "已改、已暂存的文件：" + "、".join(written)])
    commit = _git(checkout, "rev-parse", "HEAD").stdout.strip()
    result = ApproveResult(0, commit=commit)
    answered_at = store.now()
    approved_before = _approved_nodes(db)
    with db.transaction(actor="coordinator") as tx:
        approval = tx.allocate_number()
        tx.put("item", str(approval), {
            "state": "closed", "kind": "review-approval", "closedReason": "answered", "relayId": None,
            "from": "coordinator", "reviews": [n for n, _ in picked], "baselineCommit": commit,
            "answer": {"original": original, "answeredAt": answered_at}}, action="review-approved")
        for n, rec in picked:
            body = tx.allocate_number()
            meta = tx.write_body(body, _reply_text(n, rec, original, answered_at))
            tx.put("item", str(n), dict(rec, state="closed", closedReason="answered",
                                        answer={"original": original, "answeredAt": answered_at, "body": body,
                                                "approval": approval}), action="answered", data={"body": body})
            result.sends.append({"kind": "user-reply", "to": rec["from"], "replyTo": rec["relayId"], "body": body,
                                 "path": db.path / meta["path"]})
        for m in modules:
            nodes_now = approved_before.get(m, set()) | {rec["node"] for _, rec in picked if rec["module"] == m}
            if not {"spec", "plan"} <= nodes_now:
                continue
            sender = next(rec["from"] for _, rec in picked if rec["module"] == m)
            text = protocol.render_coordination_notice(
                kind="start", basis=f"用户批准事项 #{approval}（{m} 的 Spec 与 Plan），已提交到集成基线 {commit[:7]}",
                todo=(f"把集成分支合进你的模块分支（spec/{m}.md、tasks/{m}/ 冲突时取集成分支的版本，它带评审标记），"
                      f"然后按 tasks/{m}/plan.md 开始构建；公共文件只能经【公共变更请求】改"))
            body = tx.allocate_number()
            meta = tx.write_body(body, text)
            result.sends.append({"kind": "coordination-notice", "to": sender, "replyTo": None, "body": body,
                                 "path": db.path / meta["path"]})
    result.approval = approval
    result.lines.append(f"批准事项 #{approval}；集成基线提交 {commit[:7]}")
    if approval != approval_no:
        result.lines.append(f"注意：提交信息里写的是 #{approval_no}，实际批准事项是 #{approval}（期间有其他写入）")
    return result
