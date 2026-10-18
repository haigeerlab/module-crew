"""Batch review of 【交审】: record, list, answer, and approve onto the integration baseline
(see spec/crew-review-batch.md).
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from module_crew import commits, probe, protocol, store
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


REQUIRED_FILES = {"spec": ("spec/{m}.md",), "plan": ("tasks/{m}/plan.md", "tasks/{m}/todo.md")}


def _missing_files(module: str, node: str, files: list[dict]) -> list[str]:
    """Files a Spec or Plan review must list; approval only copies listed files to the integration branch."""
    listed = {f["path"] for f in files}
    return [f"{node_file} 没有列在「文件」里（{NODE_NAME[node]} 交审必须列出：{'、'.join(r.format(m=module) for r in REQUIRED_FILES[node])}）"
            for node_file in (r.format(m=module) for r in REQUIRED_FILES.get(node, ())) if node_file not in listed]


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
    reasons = _missing_files(sub["module"], sub["node"], sub["files"]) + _check_files(worktree, sub["files"])
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
        out.lines.append(f"已记为交审事项 C{n}（{sub['module']} 的 {msg.fields.get('节点', '').strip()}）")
        if out.closed:
            out.lines.append("取代了 " + "、".join(f"C{k}" for k in out.closed))
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


NODE_RANK = {"spec": 0, "interface": 1, "plan": 2, "final": 3}


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
    # Present module by module in Build order, and within a module Spec → interface → Plan (user request, 2026-10-18).
    order = [m for group in (report.map or {}).get("buildOrderGroups") or [] for m in group] or list(modules)
    rank = {m: i for i, m in enumerate(order)}
    open_items.sort(key=lambda kv: (rank.get(kv[1]["module"], len(rank)), NODE_RANK.get(kv[1]["node"], 9), kv[0]))
    groups: list[dict] = []
    for n, v in open_items:
        if not groups or groups[-1]["module"] != v["module"]:
            groups.append({"module": v["module"], "responsibility": modules.get(v["module"], {}).get("responsibility", ""),
                           "items": []})
        groups[-1]["items"].append(n)
    return {"items": [{"number": n, "ref": f"C{n}", "module": v["module"], "node": v["node"], "from": v["from"],
                       "files": v["files"], "points": _points(v["text"]), "reviews": list(v.get("reviews") or [])}
                      for n, v in open_items],
            "groups": groups, "dependencyIssues": issues, "conflicts": conflicts}


class NoteRefused(Exception):
    """The review conclusion cannot be recorded; nothing was written."""


def note(db: store.Store, number: int, sender: str, text: str) -> dict:
    """Record a whitelisted reviewer's 【审查结论】 on an open review (shown in batch; never blocks approval)."""
    from module_crew import sources
    if not any(r.get("name") == sender and r.get("kind") == "lead" for r in sources.listing(db)):
        raise NoteRefused(f"{sender} 没有登记为审查会话（先请用户 source add {sender} --kind lead）")
    msg = protocol.parse(text or "")
    if msg.kind != "review-conclusion" or not msg.ok:
        raise NoteRefused("不是合格的【审查结论】：" + ("、".join(msg.problems) or msg.kind))
    with db.transaction(actor="coordinator") as tx:
        rec = tx.get("item", str(number))
        if rec is None or rec.get("kind") != "review" or rec.get("state") != "open":
            raise NoteRefused(f"C{number} 不是未答的交审")
        node = protocol.REVIEW_NODES.get(msg.fields.get("节点", "").strip())
        if msg.fields.get("模块", "").strip() != rec["module"] or node != rec["node"]:
            raise NoteRefused(f"审查结论说的是 {msg.fields.get('模块')} 的 {msg.fields.get('节点')}，"
                              f"对不上 C{number}（{rec['module']} 的 {NODE_NAME.get(rec['node'], rec['node'])}）")
        row = {"from": sender, "ref": msg.fields.get("审查编号"), "verdict": msg.fields.get("结论"), "at": store.now(),
               "points": (msg.fields.get("要点") or "").strip()}
        tx.put("item", str(number), dict(rec, reviews=list(rec.get("reviews") or []) + [row]), action="review-noted")
    return row


def _advice(row: dict) -> str:
    """First line of a passed-with-advice conclusion's points ('' otherwise)."""
    if protocol._review_line(row.get("verdict") or "")["status"] != "passed-with-advice":
        return ""
    return ((row.get("points") or "").splitlines() or [""])[0].lstrip("- ").strip()


def _review_text(item: dict) -> str:
    rows = item.get("reviews") or []
    if not rows:
        return "未审查"
    advice = _advice(rows[-1])
    return f"{rows[-1]['from']} {rows[-1]['verdict']}" + (f"：{advice}" if advice else "")


POINT_LINES = 3      # contract §6: 3–5 lines of points; per review in a batch, keep up to three
SUMMARY_MAX = 60


def for_hub(project: str | os.PathLike, parallel_with: int | None = None) -> tuple[int, Path, str] | None:
    """One 【等待用户】 for the decision inbox covering every open review; None when there is none."""
    from module_crew import sources
    project = Path(project)
    db = store.open_store(project)
    b = batch(project)
    if not b["items"]:
        return None
    coord = next((n for n, s in sorted(store.records(db, "session").items())
                  if s.get("role") == "coordinator" and s.get("status") == "active"), "协调会话")
    numbers = "、".join(f"C{i['number']}" for i in b["items"])
    points = []
    by_number = {i["number"]: i for i in b["items"]}
    for g in b["groups"]:
        points.append(f"- {g['module']}（{g['responsibility']}）：" if g["responsibility"] else f"- {g['module']}：")
        for n in g["items"]:
            i = by_number[n]
            body = [line.strip() for line in i["points"].splitlines() if line.strip()][:POINT_LINES] or [""]
            points.append(f"  C{n} {i['module']} 的 {NODE_NAME.get(i['node'], i['node'])}：{body[0].lstrip('- ').strip()}"
                          f"（审查：{_review_text(i)}）")
            points += [f"    {line}" for line in body[1:]]
    for d in b["dependencyIssues"]:
        points.append(f"- 依赖未就绪：{d['module']} 依赖的 {'、'.join(d['missing'])}")
    for c in b["conflicts"]:
        points.append(f"- 并行边界重叠：{'、'.join(c.get('modules', []))} 在 {'、'.join(c.get('paths', []))}")
    lines = []
    if parallel_with is not None:
        lines.append(f"【与 #{parallel_with} 并行】")
    top = Path(probe._git(project, "rev-parse", "--show-toplevel").stdout.strip() or project)
    lines += ["【等待用户】", "结束：无", f"来自：{coord}", f"项目：{top.name}", f"要你决定：批准下列交审吗（{numbers}）",
              "要点："] + points
    if any(r.get("kind") == "lead" for r in sources.listing(db)):
        lines.append("架构审查：" + _review_summary(b["items"]))
    lines += ["选项与我的建议：",
              "推荐 A：全部批准",
              "  选了会怎样：批准后在集成分支记评审标记，各模块收到开工通知开始构建",
              "B：只批准部分（请写编号）",
              "  选了会怎样：只有写到的交审开工，其余等修改",
              "C：都退回修改",
              "  选了会怎样：各模块按你的意见改完再交审",
              "你该回：A 全部批准",
              "是否完全停住：否"]
    text = "\n".join(lines) + "\n"
    msg = protocol.parse(text)
    if not msg.ok or msg.kind != "wait-user":
        raise ValueError("生成的【等待用户】不合格：" + "、".join(msg.problems))
    with db.transaction(actor="coordinator") as tx:
        n = tx.allocate_number()
        meta = tx.write_body(n, text)
    return n, db.path / meta["path"], text


def _review_summary(items: list[dict]) -> str:
    """The 架构审查 line for the whole batch (contract v1.4 forms)."""
    rows = [(i.get("reviews") or [None])[-1] for i in items]
    if any(r is None for r in rows):
        return "进行中，请勿先批"
    advice = 0
    for r in rows:
        line = protocol._review_line(r["verdict"])
        if line["status"] not in ("passed", "passed-with-advice"):
            return "进行中，请勿先批"
        advice += line["adviceCount"] or 0
    if not advice:
        return "通过"
    summary = "；".join(a for a in (_advice(r) for r in rows) if a)
    summary = re.sub(r"[（）()]", "", summary)
    summary = summary if len(summary) <= SUMMARY_MAX else summary[:SUMMARY_MAX - 1] + "…"
    return f"通过，附建议{advice}条" + (f"（{summary}）" if summary else "")


def _reply_groups(picked: list[tuple[int, dict]]) -> list[list[tuple[int, dict]]]:
    """One reply per item; relaying a source's answer (v1.6): one reply per recipient listing all its messages."""
    if not store.source_field():
        return [[pair] for pair in picked]
    groups: dict[str, list] = {}
    for pair in picked:
        groups.setdefault(pair[1]["from"], []).append(pair)
    return list(groups.values())


def _group_reply_text(group: list[tuple[int, dict]], original: str, answered_at: str) -> str:
    src = store.source_field().get("source")
    if not src:
        return _reply_text(group[0][0], group[0][1], original, answered_at)
    from module_crew import sources
    try:
        return protocol.render_user_reply(item=src["item"], original=original, answered_at=answered_at,
                                          originals=[rec["relayId"] for _, rec in group if rec.get("relayId") is not None],
                                          relay=sources.relay_line(src), scope=src.get("scope"))
    except ValueError as exc:
        raise AnswerRefused(str(exc)) from exc


def _closing_send(tx, db: store.Store, sends: list[dict], modules: list[str]) -> None:
    """After relaying a source's answer, the 【已恢复】 that closes the source's item (contract v1.6)."""
    src = store.source_field().get("source")
    if not src:
        return
    text = protocol.render_resumed([src["item"]], f"已把用户对 #{src['item']} 的答复转给 {'、'.join(modules)} 的模块会话。")
    body = tx.allocate_number()
    meta = tx.write_body(body, text)
    sends.append({"kind": "resumed", "to": src["name"], "replyTo": None, "body": body, "path": db.path / meta["path"]})


def closing(db: store.Store, recipients: list[str]) -> dict | None:
    """The 【已恢复】 for the active source's item, written as a body; None when there is no source."""
    if not store.source_field():
        return None
    sends: list[dict] = []
    with db.transaction(actor="coordinator") as tx:
        _closing_send(tx, db, sends, list(dict.fromkeys(recipients)))
    return sends[0]


def _reply_text(item_no: int, rec: dict, original: str, answered_at: str) -> str:
    try:
        src = store.source_field().get("source")
        if src:
            from module_crew import sources
            return protocol.render_user_reply(item=src["item"], original=original, answered_at=answered_at,
                                              originals=[rec["relayId"]] if rec.get("relayId") is not None else None,
                                              relay=sources.relay_line(src), scope=src.get("scope"))
        return protocol.render_user_reply(item=item_no, original=original, answered_at=answered_at,
                                          source_relay_id=rec["relayId"], crew=True)
    except ValueError as exc:
        raise AnswerRefused(str(exc)) from exc


def answer(db: store.Store, number: int, original: str) -> Reply:
    """【用户答复】 for one open review (e.g. changes required); the baseline is not touched."""
    with db.transaction(actor="coordinator") as tx:
        rec = tx.get("item", str(number))
        if rec is None or rec.get("kind") != "review":
            raise AnswerRefused(f"没有交审事项 C{number}")
        if rec.get("state") != "open":
            raise AnswerRefused(f"交审事项 C{number} 已关闭（{rec.get('closedReason')}）")
        answered_at = store.now()
        text = _reply_text(number, rec, original, answered_at)
        body = tx.allocate_number()
        meta = tx.write_body(body, text)
        tx.put("item", str(number), dict(rec, state="closed", closedReason="answered",
                                         answer={"original": original, "answeredAt": answered_at, **store.source_field(), "body": body}),
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


def _record_lead(db: store.Store, picked: list, original: str, reasons: list[str]) -> ApproveResult:
    """A designated lead's relayed approval of a Spec/Plan is only recorded: spec-guard (0.70.0) does not accept it
    as a source for review marks, so nothing lands on the baseline and the reviews stay open for the user."""
    if reasons:
        return ApproveResult(3, ["没有执行，原因："] + reasons)
    with db.transaction(actor="coordinator") as tx:
        n = tx.allocate_number()
        tx.put("item", str(n), {"state": "closed", "kind": "lead-record", "closedReason": "answered", "relayId": None,
                                "from": "coordinator", "reviews": [k for k, _ in picked],
                                "answer": {"original": original, "answeredAt": store.now(), **store.source_field()}},
               action="lead-recorded")
    res = ApproveResult(0, approval=n)
    res.lines += [f"负责人转交的批准只记账（记录 C{n}）：没有写评审标记、没有提交、没有发答复与开工通知，交审事项保持未关",
                  "原因：spec-guard 不认负责人转交为写评审标记的来源；请用户在本会话亲手批准，或经收件枢纽再批准一次"]
    return res


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
            reasons.append(f"没有交审事项 C{n}")
        elif rec.get("state") != "open":
            reasons.append(f"交审事项 C{n} 已关闭（{rec.get('closedReason')}）")
        elif rec.get("node") not in APPROVABLE:
            reasons.append(f"交审事项 C{n} 是最终验收：用 review answer 答复，合并归 crew-merge")
        else:
            picked.append((n, rec))
    src = store.source_field().get("source") or {}
    if src.get("kind") == "lead":
        return _record_lead(db, picked, original, reasons)
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
                reasons.append(f"C{n} 的 {f['path']} 从提交 {rec['commit'][:7]} 里取不出")
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
            return ApproveResult(4, [f"C{n}（{rec['module']}）写评审标记失败，已停下：{ran.stderr.strip()[:200]}",
                                     "集成 checkout 里已改、未提交的文件：" + "、".join(written),
                                     "状态库与集成分支都没有变化；这些文件留着，交用户决定"])
    approval_no = _next_number(db)
    modules = list(dict.fromkeys(rec["module"] for _, rec in picked))
    nodes = "、".join(f"{rec['module']} 的 {NODE_NAME[rec['node']]}" for _, rec in picked)
    _git(checkout, "add", "--", *written)
    hub = f"（收件枢纽事项 #{src['item']}）" if src.get("kind") == "hub" else ""
    commit_run = _git(checkout, "commit", "-q", "-m", commits.message(f"用户批准事项 C{approval_no}{hub}：批准 {nodes}"))
    if commit_run.returncode != 0:
        return ApproveResult(4, [commits.failure(checkout, commit_run, "集成分支提交失败"),
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
            "answer": {"original": original, "answeredAt": answered_at, **store.source_field()}}, action="review-approved")
        for group in _reply_groups(picked):
            body = tx.allocate_number()
            meta = tx.write_body(body, _group_reply_text(group, original, answered_at))
            for n, rec in group:
                tx.put("item", str(n), dict(rec, state="closed", closedReason="answered",
                                            answer={"original": original, "answeredAt": answered_at, **store.source_field(),
                                                    "body": body, "approval": approval}), action="answered", data={"body": body})
            relays = [rec["relayId"] for _, rec in group if rec.get("relayId") is not None]
            result.sends.append({"kind": "user-reply", "to": group[0][1]["from"], "replyTo": group[0][1]["relayId"],
                                 "alsoAnswers": relays[1:],     # one reply answering several requests (agent-relay)
                                 "body": body, "path": db.path / meta["path"]})
        _closing_send(tx, db, result.sends, modules)
        for m in modules:
            nodes_now = approved_before.get(m, set()) | {rec["node"] for _, rec in picked if rec["module"] == m}
            if not {"spec", "plan"} <= nodes_now:
                continue
            sender = next(rec["from"] for _, rec in picked if rec["module"] == m)
            text = protocol.render_coordination_notice(
                kind="start", basis=f"用户批准事项 C{approval}（{m} 的 Spec 与 Plan），已提交到集成基线 {commit[:7]}",
                todo=(f"把集成分支合进你的模块分支（spec/{m}.md、tasks/{m}/ 冲突时取集成分支的版本，它带评审标记），"
                      f"然后按 tasks/{m}/plan.md 开始构建；公共文件只能经【公共变更请求】改"))
            body = tx.allocate_number()
            meta = tx.write_body(body, text)
            result.sends.append({"kind": "coordination-notice", "to": sender, "replyTo": None, "body": body,
                                 "path": db.path / meta["path"]})
    result.approval = approval
    result.lines.append(f"批准事项 C{approval}；集成基线提交 {commit[:7]}")
    if approval != approval_no:
        result.lines.append(f"注意：提交信息里写的是 C{approval_no}，实际批准事项是 C{approval}（期间有其他写入）")
    return result
