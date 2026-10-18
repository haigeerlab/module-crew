"""Batch review of 【交审】: record, list, answer, and approve onto the integration baseline
(see spec/crew-review-batch.md).
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta
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
    if sub["node"] == "final" and not _evidence(msg.fields.get("要点", "")):
        reasons.append(f"最终验收的「要点」里缺「{EVIDENCE}」一节：按 Spec 的验收标准逐条写「<编号或原文>：<证据>」，没有证据写「无」")
    if not reasons and sub.get("disputes"):
        reasons = _disagree_reasons(db, worktree, sub)
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
        rec = {"state": "open", "kind": "review", "from": sender, "relayId": relay_id, "text": text,
               "module": sub["module"], "node": sub["node"], "files": sub["files"], "commit": commit,
               "closedReason": None, "answer": None}
        reviewers = [] if sub.get("disputes") else _reviewers(db)
        if sub.get("disputes"):
            rec["disputes"] = sub["disputes"]
        if reviewers:                      # 送审: the 【交审】 goes to every registered reviewer unchanged
            body = tx.allocate_number()
            meta = tx.write_body(body, text)
            rec.update(sentAt=store.now(), sentTo=reviewers)
            out.sends += [{"kind": "review-forward", "to": r, "replyTo": None, "body": body, "path": db.path / meta["path"]}
                          for r in reviewers]
        tx.put("item", str(n), rec, action="created", data={"relayId": relay_id})
        out.number = n
        out.lines.append(f"已记为交审事项 C{n}（{sub['module']} 的 {msg.fields.get('节点', '').strip()}）")
        if sub.get("disputes"):
            refs = "、".join(d["review"] for d in sub["disputes"])
            out.lines.append(f"模块不同意审查 {refs}：不再返工，作为待用户决定的问题提请批准")
        if out.closed:
            out.lines.append("取代了 " + "、".join(f"C{k}" for k in out.closed))
        return out


REVIEW_TIMEOUT = timedelta(minutes=15)
EVIDENCE = "验收标准与证据"


def _evidence(points: str) -> list[str]:
    """R17: the 「验收标准与证据」 section of a final review's points — its heading and lines up to the next blank line."""
    lines = points.splitlines()
    at = next((k for k, line in enumerate(lines) if line.strip().lstrip("#").strip().startswith(EVIDENCE)), None)
    if at is None:
        return []
    out = [lines[at].strip()]
    for line in lines[at + 1:]:
        if not line.strip():
            break
        out.append(line)
    return out


def _reviewers(db: store.Store) -> list[str]:
    from module_crew import sources
    return [r["name"] for r in sources.listing(db) if r.get("kind") == "lead"]


def _disagree_reasons(db: store.Store, worktree: Path, sub: dict) -> list[str]:
    """「不同意」 must re-send the previous version unchanged: same files, same content as that submission's commit."""
    prev = next((v for _, v in sorted(store.records(db, "item").items(), key=lambda kv: -int(kv[0]))
                 if v.get("kind") == "review" and v.get("state") == "open" and v.get("module") == sub["module"]
                 and v.get("node") == sub["node"]), None)
    if prev is None:
        return ["写了「不同意」，但这个节点没有未答的上一版交审可以不同意"]
    if sorted(f["path"] for f in prev["files"]) != sorted(f["path"] for f in sub["files"]):
        return ["写了「不同意」时，文件要和上一版交审相同（不同意就是不改）"]
    for f in sub["files"]:
        before = subprocess.run(["git", "-C", str(worktree), "show", f"{prev['commit']}:{f['path']}"], capture_output=True)
        now = (worktree / f["path"]).read_bytes()
        if before.returncode != 0 or hashlib.sha256(before.stdout).digest() != hashlib.sha256(now).digest():
            return [f"写了「不同意」时，文件要和上一版交审相同：{f['path']} 改过了（改了就别写「不同意」，按返工重交）"]
    return []


def _rounds(db: store.Store, module: str, node: str) -> int:
    """Rework notices already sent for this module and node."""
    return sum(1 for e in store.events(db, kind="item") if e.get("type") == "item.rework-sent"
               and (e.get("data") or {}).get("module") == module and (e.get("data") or {}).get("node") == node)


def review_state(db: store.Store, number: int, now: datetime | None = None) -> str:
    """none / reviewing / timeout / rework / passed / decide (spec/crew-review-nearby.md key decision 1)."""
    rec = store.get(db, "item", str(number)) or {}
    if rec.get("disputes") or rec.get("overLimit"):
        return "decide"
    rows = rec.get("reviews") or []
    if rows:
        verdict = protocol._conclusion_verdict(rows[-1].get("verdict") or "")
        if rows[-1].get("decisions"):
            return "decide"
        return "rework" if verdict == "changes-required" else "passed"
    if not rec.get("sentAt"):
        return "none"
    now = now or datetime.fromisoformat(store.now())
    return "timeout" if now - datetime.fromisoformat(rec["sentAt"]) > REVIEW_TIMEOUT else "reviewing"


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
    items = []
    for n, v in open_items:
        state = review_state(db, n)
        items.append({"number": n, "ref": f"C{n}", "module": v["module"], "node": v["node"], "from": v["from"],
                      "files": v["files"], "points": _points(v["text"]), "reviews": list(v.get("reviews") or []),
                      "reviewState": state, "round": _rounds(db, v["module"], v["node"]), "ready": state in READY,
                      "reworked": _reworked(db, v["module"], v["node"]), "decisions": _item_decisions(n, v, state)})
    return {"items": items, "groups": groups, "dependencyIssues": issues, "conflicts": conflicts}


READY = ("none", "timeout", "passed", "decide")   # states that may go to the user (key decision 3)
CHOOSE_CURRENT = [{"letter": "A", "text": "按模块现版本批准"}, {"letter": "B", "text": "退回按审查意见改"}]
CAUTIOUS = "取稳妥的一边；模块协调不替你判断，请按你的意见选"
CHOOSE_WAIT = [{"letter": "A", "text": "不等审查直接批"}, {"letter": "B", "text": "等审查结论"}]


def _reworked(db: store.Store, module: str, node: str) -> list[str]:
    """First 须修改 line of every earlier round, for 「经 N 轮审查修改：…」."""
    out = []
    for e in store.events(db, kind="item"):
        if e.get("type") == "item.rework-sent" and (e.get("data") or {}).get("module") == module \
                and (e.get("data") or {}).get("node") == node:
            rec = store.get(db, "item", e["key"]) or {}
            row = next((r for r in reversed(rec.get("reviews") or []) if r.get("changes") or r.get("points")), {})
            out.append(((row.get("changes") or [row.get("points", "")])[0]).splitlines()[0] if row else "")
    return out


def _item_decisions(n: int, v: dict, state: str) -> list[dict]:
    """Questions this submission puts to the user: the reviewer's own, or the coordinator's for a deadlock or timeout."""
    what = f"C{n} {v['module']} 的 {NODE_NAME.get(v['node'], v['node'])}"
    rows = v.get("reviews") or []
    last = rows[-1] if rows else {}
    asked = (last.get("changes") or [last.get("points", "")])
    if v.get("disputes"):
        reasons = "；".join(f"{d['review']}：{d['reason']}" for d in v["disputes"])
        return [{"source": "coordinator", "kind": "disagree", "lean": "B", "leanReason": CAUTIOUS, "options": CHOOSE_CURRENT,
                 "question": f"{what}：模块不同意审查——审查要求：{'；'.join(asked) or '见审查结论'}；模块理由：{reasons}"}]
    if v.get("overLimit"):
        return [{"source": "coordinator", "kind": "over-limit", "lean": "B", "leanReason": CAUTIOUS, "options": CHOOSE_CURRENT,
                 "question": f"{what}：返工 {REWORK_LIMIT} 轮后审查仍要求修改——{'；'.join(asked)}"}]
    if state == "timeout":
        return [{"source": "coordinator", "kind": "timeout", "lean": "B", "leanReason": CAUTIOUS, "options": CHOOSE_WAIT,
                 "question": f"{what}：审查者 {'、'.join(v.get('sentTo') or [])} 15 分钟没有给出结论"}]
    return [{"source": last["from"], "kind": "reviewer", "lean": d["lean"], "leanReason": d.get("leanReason"),
             "options": d["options"], "question": d["question"]}
            for d in last.get("decisions") or []]


class NoteRefused(Exception):
    """The review conclusion cannot be recorded; nothing was written."""


REWORK_LIMIT = 3


@dataclass
class NoteResult:
    rows: list[dict] = field(default_factory=list)
    sends: list[dict] = field(default_factory=list)    # rework notices for the coordinator to send
    lines: list[str] = field(default_factory=list)


def note(db: store.Store, number: int | None, sender: str, text: str) -> NoteResult:
    """Record a whitelisted reviewer's 【审查结论】 (one or several sections) and turn 「有须修改项」 into rework.

    Every section is checked before anything is written; one bad section refuses the whole message.
    A section matches `number` when it is the only one, otherwise the open review of its module and node."""
    from module_crew import sources
    if not any(r.get("name") == sender and r.get("kind") == "lead" for r in sources.listing(db)):
        raise NoteRefused(f"{sender} 没有登记为审查会话（先请用户 source add {sender} --kind lead）")
    sections = protocol.split_sections(text or "")
    items = store.records(db, "item")
    picked: list[tuple[int, protocol.Message]] = []
    for i, section in enumerate(sections, 1):
        where = f"第 {i} 段：" if len(sections) > 1 else ""
        msg = protocol.parse(section)
        if msg.kind != "review-conclusion" or not msg.ok:
            raise NoteRefused(f"{where}不是合格的【审查结论】：" + ("、".join(msg.problems) or msg.kind))
        c = msg.contract()["conclusion"]
        if number is not None and len(sections) == 1:
            n = number
        else:
            hits = [int(k) for k, v in items.items() if v.get("kind") == "review" and v.get("state") == "open"
                    and v.get("module") == c["module"] and v.get("node") == c["node"]]
            if len(hits) != 1:
                raise NoteRefused(f"{where}{c['module']} 的 {NODE_NAME.get(c['node'], c['node'])} 没有唯一一条未答的交审")
            n = hits[0]
        rec = items.get(str(n))
        if rec is None or rec.get("kind") != "review" or rec.get("state") != "open":
            raise NoteRefused(f"{where}C{n} 不是未答的交审")
        if c["module"] != rec["module"] or c["node"] != rec["node"]:
            raise NoteRefused(f"{where}审查结论说的是 {msg.fields.get('模块')} 的 {msg.fields.get('节点')}，"
                              f"对不上 C{n}（{rec['module']} 的 {NODE_NAME.get(rec['node'], rec['node'])}）")
        picked.append((n, msg, section))
    res = NoteResult()
    with db.transaction(actor="coordinator") as tx:
        for n, msg, section in picked:
            c = msg.contract()["conclusion"]
            rec = tx.get("item", str(n))
            row = {"from": sender, "ref": c["ref"], "verdict": msg.fields.get("结论"), "at": store.now(),
                   "points": (msg.fields.get("要点") or "").strip(), "text": section}
            if msg.contract().get("decisions"):
                row["decisions"] = msg.contract()["decisions"]
            if c.get("changes"):
                row["changes"] = c["changes"]
            rec = dict(rec, reviews=list(rec.get("reviews") or []) + [row])
            tx.put("item", str(n), rec, action="review-noted")
            res.rows.append(row)
            res.lines.append(f"已记下 C{n} 的审查结论：{sender} {row['verdict']}")
            if c["verdict"] != "changes-required":
                continue
            done = _rounds(db, rec["module"], rec["node"])
            if done >= REWORK_LIMIT:
                tx.put("item", str(n), dict(rec, overLimit=True), action="rework-over-limit")
                res.lines.append(f"C{n} 返工已满 {REWORK_LIMIT} 次：不再返工，作为待用户决定的问题进合批")
                continue
            todo = "\n".join(f"{i}. {x}" for i, x in enumerate(c.get("changes") or [], 1)) or row["points"] or "按审查意见修改"
            body = tx.allocate_number()
            meta = tx.write_body(body, protocol.render_coordination_notice(
                "rework", f"审查 {c['ref']}（交审 C{n}）", todo + "\n改完重新发【交审】；不同意就在【交审】里写「不同意：<审查编号>：<理由>」",
                round=done + 1))
            tx.put("item", str(n), rec, action="rework-sent",
                   data={"module": rec["module"], "node": rec["node"], "round": done + 1, "body": body})
            res.sends.append({"kind": "rework", "to": rec["from"], "replyTo": None, "body": body, "path": db.path / meta["path"]})
            res.lines.append(f"C{n} 返工第 {done + 1} 轮：通知 {rec['from']} 按审查意见修改")
    return res


def waiting(project: str | os.PathLike) -> list[str]:
    """Open reviews a batch still waits for: under review (not timed out) or in rework."""
    db = store.open_store(Path(project))
    out = []
    for k, v in sorted(store.records(db, "item").items(), key=lambda kv: int(kv[0])):
        if v.get("kind") == "review" and v.get("state") == "open":
            state = review_state(db, int(k))
            if state in ("reviewing", "rework"):
                out.append(f"C{k}（{v['module']} 的 {NODE_NAME.get(v['node'], v['node'])}，{STATE_TEXT[state]}）")
    return out


STATE_TEXT = {"reviewing": "审查中", "rework": "返工中", "timeout": "审查者无响应", "passed": "审查通过",
              "decide": "待你决定", "none": "未审查"}


def _advice(row: dict) -> str:
    """First line of a passed-with-advice conclusion's points ('' otherwise)."""
    if protocol._review_line(row.get("verdict") or "")["status"] != "passed-with-advice":
        return ""
    return ((row.get("points") or "").splitlines() or [""])[0].lstrip("- ").strip()


def _review_text(item: dict) -> str:
    rows = item.get("reviews") or []
    if item.get("reviewState") == "timeout":
        return "未审查（审查者无响应）"
    if not rows:
        return "未审查"
    advice = _advice(rows[-1])
    return f"{rows[-1]['from']} {rows[-1]['verdict']}" + (f"：{advice}" if advice else "")


SUMMARY_MAX = 60


def for_hub(project: str | os.PathLike, parallel_with: int | None = None) -> list[tuple[int, Path, str]]:
    """One 【等待用户】 per module for the decision inbox (decision 47), shown as it is (R12); [] when nothing is ready.

    `separate` cadence: one node per item; `combined`: a module's ready Spec and Plan share an item."""
    from module_crew import start
    project = Path(project)
    db = store.open_store(project)
    b = batch(project)
    ready = {i["number"]: i for i in b["items"] if i["ready"]}
    combined = start.review_cadence(project) == "combined"
    out = []
    for g in b["groups"]:
        mine = [ready[n] for n in g["items"] if n in ready]
        if not mine:
            continue
        for part in ([mine] if combined else [[i] for i in mine]):
            out.append(_hub_item(project, db, b, g, part, parallel_with))
    return out


def _hub_item(project: Path, db: store.Store, b: dict, g: dict, part: list[dict], parallel_with: int | None):
    from module_crew import sources
    coord = next((n for n, s in sorted(store.records(db, "session").items())
                  if s.get("role") == "coordinator" and s.get("status") == "active"), "模块协调")
    refs = "、".join(f"C{i['number']}" for i in part)
    nodes = "、".join(NODE_NAME.get(i["node"], i["node"]) for i in part)
    numbered = [(f"D{k}", (i["number"], j), d) for k, (i, j, d) in
                enumerate(((i, j, d) for i in part for j, d in enumerate(i["decisions"])), 1)]
    points, artifacts, subs, revs = [], [], [], []
    for i in part:
        rec = store.get(db, "item", str(i["number"]))
        wt = Path((store.get(db, "session", rec["from"]) or {}).get("worktree", ""))
        prev = _previous_commit(db, rec)
        artifacts += [f"{g['module']}：{wt / f['path']} ＠ {rec['commit']}" + (f"（上一版 {prev}）" if prev else "")
                      for f in rec["files"]]
        subs.append(_original_line(db, g["module"], f"C{i['number']}-submission.txt", rec["text"]))
        last = (rec.get("reviews") or [{}])[-1]
        if last.get("text"):
            revs.append(_original_line(db, g["module"], f"C{i['number']}-review-{last['ref']}.txt", last["text"]))
        evidence = _evidence(i["points"]) if i["node"] == "final" else []
        if evidence:                                     # R17: evidence per acceptance criterion goes first
            points[:0] = [_safe(line) for line in evidence] + [""]
        points.append(f"C{i['number']} {g['module']} 的 {NODE_NAME.get(i['node'], i['node'])}（审查：{_review_text(i)}）：")
        points += [_safe(line) for line in i["points"].splitlines()]
        if i["round"]:
            points.append(f"经 {i['round']} 轮审查修改，上次须修改：")
            points += [_safe(line) for line in _last_changes(db, rec)]
    for d in b["dependencyIssues"]:
        if d["module"] == g["module"]:
            points.append(f"依赖未就绪：依赖的 {'、'.join(d['missing'])}")
    points += ["", "批准会发生什么："] + _what_happens(part)
    lines = [f"【与 #{parallel_with} 并行】"] if parallel_with is not None else []
    top = Path(probe._git(project, "rev-parse", "--show-toplevel").stdout.strip() or project)
    lines += ["【等待用户】", "结束：无", f"来自：{coord}", f"项目：{top.name}",
              f"要你决定：批准 {g['module']} 的 {nodes}（{refs}）吗", "要点："] + points
    lines += ["产物："] + artifacts + ["交审原文："] + subs + (["审查原文："] + revs if revs else [])
    if numbered:
        lines += ["待用户决定："] + question_lines(numbered)
    if any(r.get("kind") == "lead" for r in sources.listing(db)):
        lines.append("架构审查：" + _review_summary(part))
    lines += ["选项与我的建议：",
              "推荐 A：批准",
              f"  选了会怎样：{_consequence(part)}",
              "B：退回修改（请写修改意见）",
              "  选了会怎样：模块按你的意见改完再交审，集成分支不变",
              "你该回：A" + "".join(f"；{k} {d['lean'] or 'A'}" for k, _, d in numbered),
              "是否完全停住：否"]
    text = "\n".join(lines) + "\n"
    msg = protocol.parse(text)
    if not msg.ok or msg.kind != "wait-user":
        raise ValueError("生成的【等待用户】不合格：" + "、".join(msg.problems))
    mapping = {k: {"review": n, "index": j, "kind": d["kind"], "letters": [o["letter"] for o in d["options"]]}
               for k, (n, j), d in numbered}
    with db.transaction(actor="coordinator") as tx:
        n = tx.allocate_number()
        meta = tx.write_body(n, text)
        tx.put("item", str(tx.allocate_number()), {
            "state": "closed", "kind": "hub-batch", "body": n, "closedReason": "recorded", "module": g["module"],
            "reviews": [i["number"] for i in part], "decisions": mapping}, action="hub-batch")
    return n, db.path / meta["path"], text


_WAIT_USER_FIELD = re.compile(r"^\s*(" + "|".join(map(re.escape, protocol.FIELDS["wait-user"])) + r")\s*[：:]")


def _safe(line: str) -> str:
    """A points line that would read as another field gets a leading 「＞」; the word-for-word copy is the 交审原文 file."""
    return "＞" + line if _WAIT_USER_FIELD.match(line) else line


def _original_line(db: store.Store, module: str, name: str, text: str) -> str:
    """Write a message word for word under <store>/originals/ (never rewritten) and give its 「路径 sha256」 line."""
    folder = db.path / "originals"
    folder.mkdir(exist_ok=True)
    data = text.encode("utf-8")
    path = folder / name
    if path.exists() and path.read_bytes() != data:
        path = folder / f"{path.stem}-{hashlib.sha256(data).hexdigest()[:12]}{path.suffix}"
    if not path.exists():
        path.write_bytes(data)
    return f"{module}：{path} sha256:{hashlib.sha256(data).hexdigest()}"


def _previous_commit(db: store.Store, rec: dict) -> str | None:
    """Commit of the version this submission replaced after rework, for showing the difference."""
    olds = [v for _, v in sorted(store.records(db, "item").items(), key=lambda kv: int(kv[0]))
            if v.get("kind") == "review" and v.get("closedReason") == "superseded" and v.get("module") == rec["module"]
            and v.get("node") == rec["node"] and v.get("commit") != rec["commit"]]
    return olds[-1]["commit"] if olds else None


def _last_changes(db: store.Store, rec: dict) -> list[str]:
    """The 须修改 of the last rework round on this module and node, numbered as written."""
    for _, v in sorted(store.records(db, "item").items(), key=lambda kv: -int(kv[0])):
        if v.get("kind") == "review" and v.get("module") == rec["module"] and v.get("node") == rec["node"]:
            row = next((r for r in reversed(v.get("reviews") or []) if r.get("changes")), None)
            if row:
                return [f"{k}. {x}" for k, x in enumerate(row["changes"], 1)]
    return []


def _what_happens(part: list[dict]) -> list[str]:
    out = []
    if any(i["node"] != "final" for i in part):
        out.append("- 在集成分支记批准标记并提交这些文件；Spec 与 Plan 都批了的模块收到开工通知开始构建")
        out.append("- 不授权合并代码；批准后要改，模块重新交审再批")
    if any(i["node"] == "final" for i in part):
        out.append("- 排进本地合并队列，完整检查通过后合并进集成分支；不推送远端")
        out.append("- 合并前可以撤回批准（merge revoke）；合并后只能另走回退")
    return out


def numbered_decisions(b: dict) -> list[tuple[str, tuple[int, int], dict]]:
    """(D号, (交审号, 序号), 问题) for the reviews that may go to the user, in the order the batch shows them."""
    by_number = {i["number"]: i for i in b["items"] if i["ready"]}
    out, k = [], 0
    for g in b["groups"]:
        for n in g["items"]:
            for j, d in enumerate(by_number[n]["decisions"] if n in by_number else []):
                k += 1
                out.append((f"D{k}", (n, j), d))
    return out


def question_lines(numbered: list) -> list[str]:
    lines = []
    for k, _, d in numbered:
        lines.append(f"{k}：{d['question']}")
        lines += [f"  {o['letter']}. {o['text']}" for o in d["options"]]
        if d["lean"]:
            lines.append(f"  倾向：{d['lean']}（{d.get('leanReason') or d['source']}）")
    return lines


def _consequence(ready: list[dict]) -> str:
    """R4: what approving really does for the nodes in this batch."""
    parts = []
    if any(i["node"] != "final" for i in ready):
        parts.append("Spec、Plan 记评审标记，两份都批了的模块开工")
    if any(i["node"] == "final" for i in ready):
        parts.append("最终验收排进合并队列，检查通过后合并进集成分支")
    return "；".join(parts)


def _review_summary(items: list[dict]) -> str:
    """The 架构审查 line for the whole batch (contract v1.4 forms).

    A deadlock (module disagrees, or rework over the limit) is a question for the user, not a review state, so it is left out."""
    items = [i for i in items if not any(d["kind"] in ("disagree", "over-limit") for d in i.get("decisions") or [])]
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
NODE_NAME = {"spec": "Spec", "plan": "Plan", "interface": "接口提案", "final": "最终验收"}


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
