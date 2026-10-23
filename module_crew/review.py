"""Batch review of 【交审】: record, list, answer, and approve onto the integration baseline
(see spec/crew-review-batch.md).
"""

from __future__ import annotations

import difflib
import hashlib
import os
from datetime import datetime, timedelta
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from module_crew import commits, probe, protocol, store, sync
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


# spec-guard's layout convention, not module-crew's (boundary review 7, 0.9.7): its interface.json names
# spec/<id>.md and tasks/<id>/todo.md only in descriptions, with no field to read the paths from, so they are
# written here. Re-check when spec-guard changes where a module's Spec, Plan or todo lives.
REQUIRED_FILES = {"spec": ("spec/{m}.md",), "plan": ("tasks/{m}/plan.md", "tasks/{m}/todo.md")}


def _missing_files(module: str, node: str, files: list[dict]) -> list[str]:
    """Files a Spec or Plan review must list; approval only copies listed files to the integration branch."""
    listed = {f["path"] for f in files}
    return [f"{node_file} 没有列在「文件」里（{NODE_NAME[node]} 交审必须列出：{'、'.join(r.format(m=module) for r in REQUIRED_FILES[node])}）"
            for node_file in (r.format(m=module) for r in REQUIRED_FILES.get(node, ())) if node_file not in listed]


def add(db: store.Store, text: str, sender: str, relay_id: int) -> Outcome:
    """Judge one 【交审】 and record it; nothing is written unless the code is 0."""
    msg = protocol.parse(text)
    if msg.kind == "review-request" and msg.contract().get("task"):
        return _add_task(db, msg, text, sender, relay_id)
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
        reasons.append(f"最终验收的「要点」里缺「{EVIDENCE}」一节：按 Spec 的验收标准逐条写结果与证据「<编号或原文>：<结果与证据>」，没有证据写「无」")
    if not reasons and sub.get("disputes"):
        reasons = _disagree_reasons(db, worktree, sub)
    if reasons:
        return Outcome(msg.kind, 3, lines=["拒收，请退回："] + reasons)
    commit = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    carries_spec = sub["node"] == "plan" and any(f["path"] == f"spec/{sub['module']}.md" for f in sub["files"])
    revised = (_spec_revision(db, worktree, sub["module"], commit)          # decision 10 (final), decision 7 (plan)
               if sub["node"] == "final" or carries_spec else None)
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
        if sub["node"] == "final":          # O-stale-approval: a resubmitted final acceptance voids the old approval
            for key, ap in sorted(tx.records("item").items(), key=lambda kv: int(kv[0])):
                if ap.get("kind") == "merge-approval" and ap.get("state") == "open" and ap.get("module") == sub["module"]:
                    tx.put("item", key, dict(ap, state="closed", closedReason="superseded", supersededBy=n),
                           action="superseded", data={"by": n})
                    out.lines.append(f"合并批准 C{key} 因重交审 C{n} 作废，合并队列不再取它；"
                                     "告诉用户：之前批的那次验收作废，新的一份会另外提请")
        rec = {"state": "open", "kind": "review", "from": sender, "relayId": relay_id, "text": text,
               "module": sub["module"], "node": sub["node"], "files": sub["files"], "commit": commit,
               "closedReason": None, "answer": None}
        reviewers = [] if sub.get("disputes") else _reviewers(db, sub["module"], sub["node"])
        if not sub.get("disputes"):
            out.lines += _unrouted(db, sub["module"], sub["node"], reviewers)
        if sub.get("disputes"):
            rec["disputes"] = sub["disputes"]
        if revised:
            rec["specRevised"] = revised
        if reviewers:                      # 送审: the 【交审】 goes unchanged to the reviewers whose scope covers it
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
            out.lines.append(f"模块不同意审查 {refs}：不再返工，作为待你决定（D 编号）的问题提请批准")
        if out.closed:
            out.lines.append("取代了 " + "、".join(f"C{k}" for k in out.closed))
        if revised:
            out.lines.append(f"{revised['path']} 在构建中改过（和集成分支上已批准的不同）：提请用户批准这次最终验收时附上 Spec 的改动差异"
                             f"（review show C{n} --spec-diff），写明一次批准同时批准修订后的 Spec；合入后由 merge run 记下它的批准")
        return out


_MARKER = "<!-- spec-guard: review"


def _restore(checkout: Path) -> list[str]:
    """Decision 4 (0.11.2): put the integration checkout back after a failed approve. It was clean before (baseline
    check), so every tracked change is ours and goes back to the branch; new files are unstaged and kept, never deleted."""
    _git(checkout, "reset", "-q")
    _git(checkout, "checkout", "--", ".")
    new = [line[3:] for line in _git(checkout, "status", "--porcelain", "--untracked-files=all").stdout.splitlines()
           if line.startswith("?? ")]
    return (["状态库与集成分支都没有变化；集成 checkout 里原有的文件已还原成集成分支上的内容"]
            + (["这次新建、没有删除的文件（未暂存，交用户决定）：" + "、".join(new)] if new else []))


def _unmarked(text: str) -> list[str]:
    return [x for x in text.splitlines(keepends=True) if not x.startswith(_MARKER)]


def _same_but_marker(path: Path, data: bytes) -> bool:
    """A listed file already on the integration checkout that differs at most in its review marker line."""
    try:
        here = path.read_text(encoding="utf-8")
        return here.encode("utf-8") != data and _unmarked(here) == _unmarked(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError):
        return False


def _spec_revision(db: store.Store, worktree: Path, module: str, commit: str) -> dict | None:
    """crew-merge decision 10: the module's Spec at the final review differs from the approved one on the integration
    branch (marker lines aside). None when they match, or when the integration branch has no such Spec."""
    rel = f"spec/{module}.md"
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch")
    if not branch:
        return None
    base = _git(worktree, "show", f"refs/heads/{branch}:{rel}")
    mine = _git(worktree, "show", f"{commit}:{rel}")
    if base.returncode != 0 or mine.returncode != 0:
        return None
    strip = lambda s: [x for x in s.splitlines(keepends=True) if not x.startswith(_MARKER)]
    if strip(base.stdout) == strip(mine.stdout):
        return None
    diff = "".join(difflib.unified_diff(base.stdout.splitlines(keepends=True), mine.stdout.splitlines(keepends=True),
                                        f"a/{rel}（集成分支 {branch}）", f"b/{rel}（交审提交 {commit[:7]}）"))
    return {"path": rel, "diff": diff}


def _add_task(db: store.Store, msg, text: str, sender: str, relay_id: int) -> Outcome:
    """crew-light-task: a light task's final acceptance (「模块：无」 + 「任务」, contract v2.5)."""
    from module_crew import tasks
    n = int(msg.contract()["task"][1:])
    session = store.get(db, "session", sender) or {}
    if session.get("role") != "task" or session.get("status") != "active" or session.get("task") != n:
        return Outcome(msg.kind, 3, lines=[f"发件人 {sender} 不是轻任务 T{n} 登记的在用会话，拒收"])
    if not msg.ok:
        return Outcome(msg.kind, 3, lines=["消息不合格，请退回：" + "、".join(msg.problems)])
    sub = msg.contract()["submission"]
    if sub["node"] != "final":
        return Outcome(msg.kind, 3, lines=["轻任务只交最终验收（节点：最终验收）"])
    t = store.get(db, "task", str(n)) or {}
    if t.get("state") != "working":
        return Outcome(msg.kind, 3, lines=[f"T{n} 现在是「{tasks.STATE_NAMES.get(t.get('state'), '?')}」，不在做，拒收"])
    worktree = Path(session["worktree"])
    reasons = _check_files(worktree, sub["files"])
    if reasons:
        return Outcome(msg.kind, 3, lines=["拒收，请退回："] + reasons)
    if any(e["actor"] == sender and e["data"].get("relayId") == relay_id for e in store.events(db)):
        return Outcome(msg.kind, 0, lines=[f"已记过：{sender} 的邮箱消息 #{relay_id}，没有重复记账"])
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch")
    changed = [l for l in _git(worktree, "diff", "--name-only", f"{branch}...HEAD").stdout.splitlines() if l.strip()]
    extra = sorted(f for f in changed if not any(tasks.clash(f, e) for e in t["expectedFiles"]))
    clashes, _ = tasks.overlaps(db, worktree, extra, exclude=n) if extra else ([], [])   # any checkout of the repo
    commit = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    out = Outcome(msg.kind, 0)
    with db.transaction(actor=sender) as tx:
        number = tx.allocate_number()
        for key, ap in sorted(tx.records("item").items(), key=lambda kv: int(kv[0])):
            if ap.get("kind") in ("review", "merge-approval") and ap.get("state") == "open" and ap.get("task") == n:
                tx.put("item", key, dict(ap, state="closed", closedReason="superseded", supersededBy=number),
                       action="superseded", data={"by": number})
                out.closed.append(int(key))
        tx.put("item", str(number), {
            "state": "open", "kind": "review", "from": sender, "relayId": relay_id, "text": text, "module": None,
            "task": n, "node": "final", "files": sub["files"], "commit": commit, "changedFiles": changed,
            "extraFiles": extra, "overlapExtra": clashes, "closedReason": None, "answer": None},
            action="created", data={"relayId": relay_id})
    tasks.advance(db, n, "returned", result={**(t.get("result") or {}), "files": changed, "commit": commit})
    out.number = number
    out.lines.append(f"已记为交审事项 C{number}（轻任务 T{n} 的最终验收）；实际改了 {len(changed)} 个文件")
    if extra:
        out.lines.append("任务单以外多改了：" + "、".join(extra))
    if clashes:
        out.lines.append("越界重叠：多改的文件和在做的活重叠（" + "、".join(clashes) + "），建议走升格，交审时写明")
    if t["type"] == "bug" and "复现测试" not in msg.fields.get("要点", ""):
        out.lines.append("提示：这是 bug，「要点」里没写复现测试；问做事的会话补没补能复现问题的测试")
    if out.closed:
        out.lines.append("取代了 " + "、".join(f"C{k}" for k in out.closed))
    return out


def _unit(v: dict) -> str:
    """A review's group: its module, or 「T<号>」 for a light task (crew-light-task)."""
    return v.get("module") or f"T{v.get('task')}"


def held_for_old_hub(db: store.Store, project: str | os.PathLike) -> list[int]:
    """Ready light-task reviews kept out of for-hub because a registered inbox speaks a contract older than v2.5."""
    from module_crew import sources
    if not _old_hub(db):
        return []
    return [i["number"] for i in batch(project)["items"] if i["ready"] and i.get("task")]


def _old_hub(db: store.Store) -> bool:
    from module_crew import sources
    return any(r.get("kind") == "hub" and sources.hub_protocol(r) < "2.5" for r in sources.listing(db))


REVIEW_TIMEOUT = timedelta(minutes=15)
EVIDENCE = "验收结果"                       # contract v2.6; the older heading is still taken
EVIDENCE_NAMES = (EVIDENCE, "验收标准与证据")


def _evidence(points: str) -> list[str]:
    """R17: the 「验收结果」 (or older 「验收标准与证据」) section of a final review's points — heading and lines up to a blank."""
    lines = points.splitlines()
    at = next((k for k, line in enumerate(lines) if line.strip().lstrip("#").strip().startswith(EVIDENCE_NAMES)), None)
    if at is None:
        return []
    out = [lines[at].strip()]
    for line in lines[at + 1:]:
        if not line.strip():
            break
        out.append(line)
    return out


def _reviewers(db: store.Store, module: str, node: str) -> list[str]:
    """Registered reviewers responsible for this module's node (crew-routing-fixes: no copy to every reviewer)."""
    from module_crew import sources
    return [r["name"] for r in sources.listing(db) if r.get("kind") == "lead" and sources.covers(r, module, node)]


def _unrouted(db: store.Store, module: str, node: str, reviewers: list[str]) -> list[str]:
    from module_crew import sources
    leads = [r for r in sources.listing(db) if r.get("kind") == "lead"]
    lines = [f"审查者 {r['name']} 没登记负责范围，没有送审：请用户确认范围后 source scope {r['name']} --modules … --nodes …"
             for r in leads if not r.get("scope")]
    if leads and not reviewers:
        lines.append(f"没有审查者负责 {module} 的 {node}，未送审：照常等用户批")
    return lines


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
    for mod in dict.fromkeys(v["module"] for _, v in open_items if v.get("module")):
        missing = [d for d in modules.get(mod, {}).get("dependsOn") or []
                   if modules.get(d, {}).get("status") != "done" and d not in in_batch
                   and not ({"spec", "interface"} & approved.get(d, set()))]
        if missing:
            issues.append({"module": mod, "missing": missing})
    from module_crew import present           # crew-review-display: compare the Specs under review, not only the branch's
    over = present.overlap(project, db, open_items, (report.map or {}).get("startable", {}).get("conflicts", []))
    conflicts = over["conflicts"]
    # Present module by module in Build order, and within a module Spec → interface → Plan (user request, 2026-10-18).
    order = [m for group in (report.map or {}).get("buildOrderGroups") or [] for m in group] or list(modules)
    rank = {m: i for i, m in enumerate(order)}
    open_items.sort(key=lambda kv: (rank.get(kv[1]["module"], len(rank)), NODE_RANK.get(kv[1]["node"], 9), kv[0]))
    groups: list[dict] = []
    for n, v in open_items:
        if not groups or groups[-1]["module"] != _unit(v):
            groups.append({"module": _unit(v), "task": v.get("task"),
                           "responsibility": modules.get(v["module"], {}).get("responsibility", "") if v.get("module")
                           else (store.get(db, "task", str(v.get("task"))) or {}).get("title", ""), "items": []})
        groups[-1]["items"].append(n)
    items = []
    for n, v in open_items:
        state = review_state(db, n)
        items.append({"number": n, "ref": f"C{n}", "module": v["module"], "task": v.get("task"), "node": v["node"], "from": v["from"],
                      "files": v["files"], "points": _points(v["text"]), "reviews": list(v.get("reviews") or []),
                      "reviewState": state, "round": _rounds(db, v["module"], v["node"]), "ready": state in READY,
                      "reworked": _reworked(db, v["module"], v["node"]), "decisions": _item_decisions(n, v, state),
                      **({"display": present.final_tables(project, db, v)} if v["node"] == "final" and v.get("module")
                         and not v.get("task") else {})})
    return {"items": items, "groups": groups, "dependencyIssues": issues, "conflicts": conflicts, "overlap": over}


READY = ("none", "timeout", "passed", "decide")   # states that may go to the user (key decision 3)
CHOOSE_CURRENT = [{"letter": "A", "text": "按模块现版本批准"}, {"letter": "B", "text": "退回按审查意见改"}]
# 0.9.5 (boundary review 6): module-crew's own rule, not the contract's — the decision inbox takes the proposer's
# lean as it is and has no rule of its own (spec/crew-review-nearby.md). Each says why B is the cautious side.
WHY_B = {
    "timeout": "审查者没回不等于审查通过；选 B 只是多等，选 A 也能批",
    "disagree": "审查者和模块意见不一，选 B 由模块照审查意见改，现版本不进集成分支",
    "over-limit": "改了 3 轮仍有须修改项，选 B 再改一轮，选 A 现版本照样能用但带着这些问题",
}
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
        return [{"source": "coordinator", "kind": "disagree", "lean": "B", "leanReason": WHY_B["disagree"], "options": CHOOSE_CURRENT,
                 "question": f"{what}：模块不同意审查——审查要求：{'；'.join(asked) or '见审查结论'}；模块理由：{reasons}"}]
    if v.get("overLimit"):
        return [{"source": "coordinator", "kind": "over-limit", "lean": "B", "leanReason": WHY_B["over-limit"], "options": CHOOSE_CURRENT,
                 "question": f"{what}：返工 {REWORK_LIMIT} 轮后审查仍要求修改——{'；'.join(asked)}"}]
    if state == "timeout":
        return [{"source": "coordinator", "kind": "timeout", "lean": "B", "leanReason": WHY_B["timeout"], "options": CHOOSE_WAIT,
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
        raise NoteRefused(f"{sender} 没有登记为审查者（先请用户 source add {sender} --kind lead）")
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
        sent = list(rec.get("sentTo") or [])
        if sender not in sent:          # crew-routing-fixes: only a reviewer this 【交审】 was sent to may conclude it
            raise NoteRefused(f"{where}C{n} 没有送给 {sender} 审（" + (f"送审对象：{'、'.join(sent)}" if sent else "没有送审") + "）")
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
                res.lines.append(f"C{n} 返工已满 {REWORK_LIMIT} 次：不再返工，作为待你决定（D 编号）的问题提请批准")
                continue
            todo = "\n".join(f"{i}. {x}" for i, x in enumerate(c.get("changes") or [], 1)) or row["points"] or "按审查意见修改"
            body = tx.allocate_number()
            meta = tx.write_body(body, protocol.render_coordination_notice(
                "rework", f"审查 {c['ref']}（交审 C{n}）", todo + "\n改完重新发【交审】；不同意就在【交审】里写「不同意：<审查编号>：<理由>」"
                + f"\n审查原文：module-crew review show C{n}",
                round=done + 1))
            tx.put("item", str(n), rec, action="rework-sent",
                   data={"module": rec["module"], "node": rec["node"], "round": done + 1, "body": body})
            res.sends.append({"kind": "rework", "to": rec["from"], "replyTo": None, "body": body, "path": db.path / meta["path"]})
            res.lines.append(f"C{n} 返工第 {done + 1} 轮：通知 {rec['from']} 按审查意见修改")
    return res


def progress(db: store.Store) -> dict[str, dict]:
    """Module → {"state": reviewing|rework, "round": N} for the read-only export and status (spec key decision 11)."""
    out = {}
    for k, v in sorted(store.records(db, "item").items(), key=lambda kv: int(kv[0])):
        if v.get("kind") == "review" and v.get("state") == "open":
            state = review_state(db, int(k))
            if state in ("reviewing", "rework"):
                out[v["module"]] = {"state": state, "round": _rounds(db, v["module"], v["node"])}
    return out


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


class ShowRefused(Exception):
    pass


def show(db: store.Store, number: int, submission: bool = False, spec_diff: bool = False) -> list[str]:
    """Review originals of submission C<number>, oldest round first, each with its sha256 (MC-4); read-only."""
    rec = store.get(db, "item", str(number))
    if rec is None or rec.get("kind") != "review":
        raise ShowRefused(f"C{number} 不是交审事项")
    if spec_diff:
        revised = rec.get("specRevised")
        return [revised["diff"].rstrip("\n")] if revised else [f"C{number} 交审时 Spec 和集成分支上的一样，没有改动差异"]
    out = []
    if submission:
        out += [f"交审原文（C{number}，{rec['module']} 的 {NODE_NAME.get(rec['node'], rec['node'])}）"
                f" sha256:{hashlib.sha256(rec['text'].encode('utf-8')).hexdigest()}：", rec["text"].rstrip("\n"), ""]
    rows = [r for r in rec.get("reviews") or [] if r.get("text")]
    if not rows:
        return out + [f"C{number} 还没有审查结论"]
    for i, r in enumerate(rows, 1):
        out += [f"第 {i} 轮 · {r['ref']} · {r['from']} · {r.get('verdict')} "
                f"sha256:{hashlib.sha256(r['text'].encode('utf-8')).hexdigest()}：", r["text"].rstrip("\n"), ""]
    return out[:-1]


STATE_TEXT = {"reviewing": "审查中", "rework": "返工中", "timeout": "审查者无响应", "passed": "审查通过",
              "decide": "待你决定", "none": "未审查"}


_ADVICE_LINE = re.compile(r"^[-*\s]*建议\s*\d*\s*[：:]")


def _advice(row: dict) -> str:
    """A passed-with-advice conclusion's advice ('' otherwise): every 「建议N：」 line of its points, joined;
    without such lines, the first line (0.9.1: advice written after a summary line never reached the card)."""
    if protocol._review_line(row.get("verdict") or "")["status"] != "passed-with-advice":
        return ""
    lines = [line.strip().lstrip("-* ").strip() for line in (row.get("points") or "").splitlines()]
    advice = [line for line in lines if _ADVICE_LINE.match(line)]
    return "；".join(advice) if advice else (lines or [""])[0]


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
    from module_crew import sources, start
    project = Path(project)
    db = store.open_store(project)
    b = batch(project)
    ready = {i["number"]: i for i in b["items"] if i["ready"]}
    combined = start.review_cadence(project) == "combined"
    out = []
    old_hub = _old_hub(db)
    for g in b["groups"]:
        if g.get("task") and old_hub:       # crew-light-task: T numbers need an inbox on contract v2.5
            continue
        mine = [ready[n] for n in g["items"] if n in ready]
        if not mine:
            continue
        if not combined:
            parts = [[i] for i in mine]
        else:       # contract v2.3: one kind per card, so only a Spec and a Plan share one (「Spec 与 Plan」)
            pair = [i for i in mine if i["node"] in ("spec", "plan")]
            parts = ([pair] if pair else []) + [[i] for i in mine if i not in pair]
        for part in parts:
            out.append(_hub_item(project, db, b, g, part, parallel_with))
    return out


def _hub_item(project: Path, db: store.Store, b: dict, g: dict, part: list[dict], parallel_with: int | None):
    from module_crew import sources
    coord = next((n for n, s in sorted(store.records(db, "session").items())
                  if s.get("role") == "coordinator" and s.get("status") == "active"), "模块协调")
    refs = "、".join(f"C{i['number']}" for i in part)
    nodes = "、".join(NODE_NAME.get(i["node"], i["node"]) for i in part)
    style = decision_style(db)
    numbered = [(decision_id(style, k, i["number"], j), (i["number"], j), d) for k, (i, j, d) in
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
        points.append(f"C{i['number']} {g['module']} 的 {NODE_NAME.get(i['node'], i['node'])}（审查：{_review_text(i)}）：")
        points += [_safe(line) for line in i["points"].splitlines()]   # 做了什么, 验收结果 (crew-review-display)
        if i.get("display"):                             # then 改了哪些文件 and Spec 中途改过吗, from git
            from module_crew import present
            points += [_safe(line) for line in present.table_lines(i["display"])]
        if i["round"]:
            points.append(f"经 {i['round']} 轮审查修改，上次须修改：")
            points += [_safe(line) for line in _last_changes(db, rec)]
    missing = [f"依赖未就绪：依赖的 {'、'.join(d['missing'])}" for d in b["dependencyIssues"] if d["module"] == g["module"]]
    points += _card_fields(db, part, missing)     # 0.9.5: the v2.2 card is gone; every inbox here speaks v2.3+
    lines = [f"【与 #{parallel_with} 并行】"] if parallel_with is not None else []
    top = Path(probe._git(project, "rev-parse", "--show-toplevel").stdout.strip() or project)
    what = f"轻任务 {g['module']}" if g.get("task") else g["module"]
    lines += ["【等待用户】", "结束：无", f"来自：{coord}", f"项目：{top.name}",
              f"要你决定：批准 {what} 的 {nodes}（{refs}）吗", "要点："] + points
    # contract v2.4: 「模块」 right after 要点 (older parsers fold it into 要点, which is harmless; after 类型 it is not);
    # v2.5: a light task writes 「任务」 there instead and no 「模块」
    at = next((k for k, x in enumerate(lines) if x.startswith("类型：")), len(lines))
    lines.insert(at, f"任务：{g['module']}" if g.get("task") else f"模块：{g['module']}")
    lines += ["产物："] + artifacts + ["交审原文："] + subs + (["审查原文："] + revs if revs else [])
    if numbered:
        lines += ["待用户决定："] + question_lines(numbered)
    if any(r.get("kind") == "lead" for r in sources.listing(db)):
        lines.append("架构审查：" + _review_summary(part))
    lines += ["选项与我的建议：",
              "推荐 A：批准",
              f"  选了会怎样：{_effect(part)}",
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


def _effect(part: list[dict]) -> str:
    """v2.3 「批了会怎样」, also option A's 「选了会怎样」 on the same card."""
    effect = "；".join(x.removeprefix("- ") for x in _what_happens(part))
    return effect.replace("合并后只能另走回退", "合了撤不回，只能另走回退").replace("不推送远端", "不推送远端（推送要你另外同意）")


CARD_KIND = {"spec": "Spec", "plan": "Plan", "interface": "接口提案", "final": "最终验收"}


def _card_fields(db: store.Store, part: list[dict], missing: list[str]) -> list[str]:
    """Contract v2.3 lines after 要点: 类型, 注意, 推荐理由 (only when there is a fact to give), 批了会怎样."""
    nodes = {i["node"] for i in part}
    kind = "Spec 与 Plan" if nodes == {"spec", "plan"} else CARD_KIND[part[0]["node"]]
    tag = (lambda i: f"C{i['number']}：") if len(part) > 1 else (lambda i: "")
    notes, passed = [], []
    for i in part:
        rec = store.get(db, "item", str(i["number"]))
        if i["round"]:
            notes.append(f"{tag(i)}经 {i['round']} 轮返工，上一轮须修改（本轮审查已通过）："
                         + "；".join(x.split(". ", 1)[-1] for x in _last_changes(db, rec)))
        rows = i.get("reviews") or []
        if i.get("reviewState") == "timeout":
            notes.append(f"{tag(i)}未审查（审查者无响应）")
        elif rows:
            advice = _advice(rows[-1])
            if advice:
                notes.append(f"{tag(i)}审查建议：{advice}")
            if protocol._conclusion_verdict(rows[-1].get("verdict") or "") != "changes-required":
                passed.append(rows[-1]["ref"])
    notes += missing
    effect = _effect(part)
    lines = [f"类型：{kind}", "注意：" + ("；".join(notes) if notes else "无")]
    if passed and len(passed) == len(part):
        lines.append(f"推荐理由：审查通过（{'、'.join(passed)}）" + ("，建议见「注意」" if any("审查建议" in n for n in notes) else ""))
    else:
        why = [f"{tag(i)}{d['leanReason']}" for i in part for d in i.get("decisions") or []
               if d.get("source") == "coordinator" and d.get("leanReason")]
        if why:                                   # 0.9.5: the coordinator's lean explained where the inbox shows it
            lines.append("推荐理由：" + "；".join(why))
    return lines + [f"批了会怎样：{effect}"]


def _what_happens(part: list[dict]) -> list[str]:
    out = []
    if any(i["node"] != "final" for i in part):
        out.append("- 在集成分支记批准标记并提交这些文件；Spec 与 Plan 都批了的模块收到开工通知开始构建")
        out.append("- 不授权合并代码；批准后要改，模块重新交审再批")
    if any(i["node"] == "final" for i in part):
        out.append("- 排进本地合并队列，完整检查通过后合并进集成分支；不推送远端")
        out.append("- 合并前可以撤回批准（merge revoke）；合并后只能另走回退")
    return out


def decision_style(db: store.Store) -> str:
    """crew-contract-v26 decision 2: "c" (C<交审号>-<序号>, contract v2.6) unless a registered inbox speaks older."""
    from module_crew import sources
    hubs = [r for r in sources.listing(db) if r.get("kind") == "hub"]
    return "d" if any(sources.hub_protocol(r) < "2.6" for r in hubs) else "c"


def decision_id(style: str, k: int, n: int, j: int) -> str:
    """The user-facing number of review n's j-th pending question (k-th in the batch)."""
    return f"C{n}-{j + 1}" if style == "c" else f"D{k}"


def numbered_decisions(b: dict, style: str = "d") -> list[tuple[str, tuple[int, int], dict]]:
    """(待定编号, (交审号, 序号), 问题) for the reviews that may go to the user, in the order the batch shows them."""
    by_number = {i["number"]: i for i in b["items"] if i["ready"]}
    out, k = [], 0
    for g in b["groups"]:
        for n in g["items"]:
            for j, d in enumerate(by_number[n]["decisions"] if n in by_number else []):
                k += 1
                out.append((decision_id(style, k, n, j), (n, j), d))
    return out


def reply_blocks(entries: list[tuple[str, str, list[tuple[str, str]]]]) -> list[str]:
    """Contract v2.6 section 6: one block per thing — 「<编号> <字母>」, its pending questions after 「；」."""
    return [f"{ref} {letter}" + "".join(f"；{q} {a}" for q, a in qs) for ref, letter, qs in entries]


def batch_reply_blocks(b: dict, numbered: list) -> list[str]:
    """The shortest approve reply for each ready review, leaning answers filled in (the user may change a letter)."""
    by_review: dict[int, list] = {}
    for k, (n, _), d in numbered:
        by_review.setdefault(n, []).append((k, d["lean"] or "A"))
    return reply_blocks([(f"C{i['number']}", "A", by_review.get(i["number"], []))
                         for g in b["groups"] for i in (x for x in b["items"] if x["number"] in g["items"]) if i["ready"]])


def question_lines(numbered: list) -> list[str]:
    lines = []
    for k, _, d in numbered:
        lines.append(f"{k}：{d['question']}")
        lines += [f"  {o['letter']}. {o['text']}" for o in d["options"]]
        if d["lean"]:
            lines.append(f"  倾向：{d['lean']}（{d.get('leanReason') or d['source']}）")
    return lines


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


def _closing_send(tx, db: store.Store, sends: list[dict], modules: list[str], answered: list[int] = ()) -> None:
    """After relaying an answer: the 【已恢复】 that closes the source's item (contract v1.6), then the coordinator's
    own wait records on that item or on any answered C<N> (0.9.1: a wait on C<N> closed only through `answer`)."""
    from module_crew import inbox
    src = store.source_field().get("source")
    about = [f"C{n}" for n in answered]
    if src:
        text = protocol.render_resumed([src["item"]], f"已把用户对 #{src['item']} 的答复转给 {'、'.join(modules)} 的模块会话。")
        body = tx.allocate_number()
        meta = tx.write_body(body, text)
        sends.append({"kind": "resumed", "to": src["name"], "replyTo": None, "body": body, "path": db.path / meta["path"]})
        about.append(f"#{src['item']}")
    if about:
        inbox.resume_own_waits(tx, db, sends, about)


def closing_all(db: store.Store, recipients: list[str], answered: list[int] = ()) -> list[dict]:
    """Every 【已恢复】 due after relaying an answer (the source's item, then own wait records on it or on `answered`)."""
    if not store.source_field() and not answered:
        return []
    sends: list[dict] = []
    with db.transaction(actor="coordinator") as tx:
        _closing_send(tx, db, sends, list(dict.fromkeys(recipients)), answered)
    return sends


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


# 「D1 B」「D1：B」「D1 选 B」, and since contract v2.6 the same for 「C15-1 B」
_ANSWER_RE = re.compile(r"(?<![A-Za-z0-9])(D\s*\d+|C\d+-\d+)\s*[：:]?\s*(?:选\s*)?([A-Za-z])(?![A-Za-z])")


@dataclass
class Split:
    """How a user's answer sorts the reviews being approved (spec key decision 4)."""
    approve: list[int] = field(default_factory=list)
    back: list[int] = field(default_factory=list)      # 「退回按审查意见改」: answered, nothing approved
    hold: list[int] = field(default_factory=list)      # 「等审查结论」: left open
    missing: list[str] = field(default_factory=list)   # question lines still to ask


def split_decisions(project: str | os.PathLike, numbers: list[int], original: str) -> Split:
    """Number the open questions of these reviews D1… in batch order (as the item showed them) and read the answers."""
    b = batch(Path(project))
    order = [i for i in b["items"] if i["number"] in numbers]
    known = {i["number"] for i in order}
    answers = {re.sub(r"\s+", "", k): v.upper() for k, v in _ANSWER_RE.findall(original or "")}
    style = decision_style(store.open_store(Path(project)))
    out, k = Split(), 0
    out.approve = [n for n in numbers if n not in known]          # not open reviews: let the caller refuse them
    for i in order:
        verdict = "approve"
        for j, d in enumerate(i["decisions"]):
            k += 1
            letters = [o["letter"] for o in d["options"]]
            got = answers.get(f"C{i['number']}-{j + 1}") or answers.get(f"D{k}")     # either numbering it was shown in
            if got not in letters:
                out.missing += question_lines([(decision_id(style, k, i["number"], j), None, d)])
                continue
            if d["kind"] in ("disagree", "over-limit") and got == "B":
                verdict = "back"
            elif d["kind"] == "timeout" and got == "B" and verdict == "approve":
                verdict = "hold"
        {"approve": out.approve, "back": out.back, "hold": out.hold}[verdict].append(i["number"])
    return out


def chase_lines(split: Split) -> list[str]:
    """What to ask again when a D is unanswered: never fill in the reviewer's lean."""
    ids = [line.split("：", 1)[0] for line in split.missing if line[:1] in "DC" and not line.startswith(" ")]
    missing = list(dict.fromkeys(ids))
    return ([f"待决问题没答全：{'、'.join(missing)}；没有执行。请把下面的问题再问用户一次（有决策收件箱时补发【等待用户】只问这几条），"
             "用户答全后连同原来的答复一起重跑："] + split.missing)


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
    res.lines += [f"审查者转交的批准只记账（记录 C{n}）：没有写批准标记、没有提交、没有发答复与开工通知，交审保持未答",
                  "原因：spec-guard 不认审查者转交为写批准标记的来源；请用户在本会话亲手批准，或经决策收件箱再批准一次"]
    return res


def approve(project: str | os.PathLike, numbers: list[int], original: str) -> ApproveResult:
    """Read the answers to open questions first (all must be there), then approve, return or hold each review."""
    project = Path(project)
    split = split_decisions(project, numbers, original)
    if split.missing:
        return ApproveResult(3, chase_lines(split))
    db = store.open_store(project)
    extra = ApproveResult(0)
    for n in split.back:
        reply = answer(db, n, original)
        extra.sends.append({"kind": "user-reply", "to": reply.to, "replyTo": reply.reply_to, "alsoAnswers": [],
                            "body": reply.body, "path": reply.path})
        extra.lines.append(f"C{n} 按用户的答复退回，按审查意见改后重交（没有批准）")
    extra.lines += [f"C{n} 等审查结论：保持未答，没有批准" for n in split.hold]
    if not split.approve:
        return extra
    res = _approve(project, split.approve, original)
    res.lines += extra.lines
    res.sends += extra.sends
    return res


def _approve(project: Path, numbers: list[int], original: str) -> ApproveResult:
    """Land the approved Spec/Plan files on the integration baseline and prepare all replies and notices."""
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
            elif (rec["node"] == "plan" and f["path"] == f"spec/{rec['module']}.md" and checkout is not None
                  and _same_but_marker(checkout / f["path"], shown.stdout)):
                continue        # decision 7: keep the approved copy on the integration branch, marker and all
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
        target = "both" if rec["node"] == "plan" and rec.get("specRevised") else MARK_TARGET[rec["node"]]   # decision 7
        cmd = probe.safe_command(root, doc, "reviewMark", _mark_fill(checkout, rec["module"], target)) + ["--confirm"]
        ran = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=probe.MAP_TIMEOUT)
        if ran.returncode != 0:
            return ApproveResult(4, [f"C{n}（{rec['module']}）写批准标记失败，已停下：{(ran.stderr.strip() or ran.stdout.strip())[:200]}"]
                                 + _restore(checkout))
    approval_no = _next_number(db)
    modules = list(dict.fromkeys(rec["module"] for _, rec in picked))
    nodes = "、".join(f"{rec['module']} 的 {NODE_NAME[rec['node']]}" for _, rec in picked)
    _git(checkout, "add", "--", *written)
    hub = f"（待决事项 #{src['item']}）" if src.get("kind") == "hub" else ""
    commit_run = _git(checkout, "commit", "-q", "-m", commits.message(f"用户批准事项 C{approval_no}{hub}：批准 {nodes}", commits.prefix_of(db)))
    if commit_run.returncode != 0:
        return ApproveResult(4, [commits.failure(checkout, commit_run, "集成分支提交失败")] + _restore(checkout))
    commit = _git(checkout, "rev-parse", "HEAD").stdout.strip()
    from module_crew import unqueued
    unqueued.mark(db, checkout, "review-approve")    # crew-unqueued-commits: module-crew's own commit
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
        _closing_send(tx, db, result.sends, modules, [n for n, _ in picked])
        for m in modules:
            nodes_now = approved_before.get(m, set()) | {rec["node"] for _, rec in picked if rec["module"] == m}
            if not {MARK_TARGET[n] for n in nodes_now if n in MARK_TARGET} >= {"spec", "plan"}:   # interface counts as Spec
                continue
            sender = next(rec["from"] for _, rec in picked if rec["module"] == m)
            text = protocol.render_coordination_notice(
                kind="start", basis=f"用户批准事项 C{approval}（{m} 的 Spec 与 Plan），已提交到集成分支 {commit[:7]}",
                todo=(f"{sync.STEP}（spec/{m}.md、tasks/{m}/ 冲突时 sync 自动取集成分支的版本，它带批准标记），"
                      f"然后按 tasks/{m}/plan.md 开始构建；公共文件只能经【公共变更请求】改"
                      + "".join(f"\n审查原文：module-crew review show C{k}（写 Plan、构建时吸收遗留建议）"
                                for k, rec in picked if rec["module"] == m and rec.get("reviews"))))
            body = tx.allocate_number()
            meta = tx.write_body(body, text)
            result.sends.append({"kind": "coordination-notice", "to": sender, "replyTo": None, "body": body,
                                 "path": db.path / meta["path"]})
    result.approval = approval
    result.lines.append(f"批准记录 C{approval}；集成分支提交 {commit[:7]}")
    if approval != approval_no:
        result.lines.append(f"注意：提交信息里写的是 C{approval_no}，实际批准事项是 C{approval}（期间有其他写入）")
    return result
