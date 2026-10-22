"""CLI entry: python3 -m module_crew."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from module_crew import changes, failure, hooks, inbox, merge, probe, protocol, refs, review, sources, start, store


def _store_init() -> int:
    db, created = store.init_store()
    print(f"{'已建立' if created else '已存在，未改动任何文件'}：{db.path}")
    return 0


def _store_check() -> int:
    db = store.open_store()
    report = store.check(db)
    print(f"状态库：{report['path']}")
    print(f"版本：{report['version']}")
    print(f"事件：{report['events']} 条；下一个编号：C{report['nextNumber']}")
    print("记录：" + "、".join(f"{k} {n}" for k, n in report["counts"].items()))
    for line in report["warnings"]:
        print(f"⚠️ {line}")
    for line in report["problems"]:
        print(f"❌ {line}")
    if not report["warnings"] and not report["problems"]:
        print("✅ 一致")
    return 3 if report["problems"] else 0


def _protocol_check(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as exc:
        print(f"❌ 读不到文件：{path}（{exc}）", file=sys.stderr)
        return 2
    msg = protocol.parse(text)
    print(f"类型：{msg.kind}")
    for code in msg.hints:
        print(f"⚠️ {code}")
    for code in msg.problems:
        print(f"❌ {code}")
    if not msg.supported:
        print(f"❌ {msg.kind} 第一版不处理")
        return 3
    if not msg.ok:
        return 3
    print("✅ 合格")
    return 0


_STATE_ICON = {"ok": "✅", "warning": "⚠️", "blocker": "❌"}
_KIND_NAME = {"item": "事项", "request": "请求", "ticket": "等待记录"}


def _stall_facts(row: dict | None) -> str:
    """crew-stall-signals: facts on a module session's status line; no thresholds."""
    if row is None:
        return ""
    c, parts = row["commits"], []
    if c["last"]:
        parts.append(f"最近提交 {failure._ago(c['last']['at'], datetime.now().astimezone())}")
    elif c["ahead"] == 0:
        parts.append("开工以来没有提交")
    most = max((a["count"] for a in row["asks"]), default=0)
    if most:
        parts.append(f"同一节点最多问过你 {most} 次")
    return "　" + "，".join(parts) if parts else ""


def _status(as_json: bool) -> int:
    report = probe.run()
    if as_json:
        print(json.dumps(report.to_json(), ensure_ascii=False, indent=2))
        return 3 if report.blocked else 0
    print("体检")
    for c in report.checks.values():
        line = f"  {_STATE_ICON[c.state]} {c.id}：{c.reason}"
        if c.state != "ok" and c.fix:
            line += f"；怎么办：{c.fix}"
        print(line)
    print("会话与待办")
    if report.store is None:
        print("  未建库")
    else:
        from module_crew import permissions
        facts = {r["name"]: r for r in failure.sessions(store.open_store())}
        perm = permissions.read_record(store.open_store())
        for s in report.store["sessions"] or [{"name": "（没有在用的会话）"}]:
            extra = f"（{s.get('role')}{'，' + s['module'] if s.get('module') else ''}）" if s.get("role") else ""
            perm_fact = ("　" + permissions.status_fact(perm, s["name"])) if s.get("role") == "dev" else ""
            unbound = "　未登记身份（该会话运行 module-crew bind）" if s.get("role") and not s.get("bound") else ""
            me = "　← 本会话" if s.get("self") else ""
            print(f"  {s['name']}{extra}{me}{unbound}{_stall_facts(facts.get(s['name']))}{perm_fact}")
        coord_row = next((s for s in report.store["sessions"] if s.get("role") == "coordinator" and s.get("bound")), None)
        if coord_row and report.store.get("selfIsCoordinator") is False and not any(s.get("self") for s in report.store["sessions"]):
            print(f"  本会话不是登记的模块协调 {coord_row['name']}（它登记在另一个会话上）：模块协调的写命令在这里会被拒；"
                  f"要由本会话接手，请用户同意后运行 module-crew bind {coord_row['name']} --takeover --original-file <原话文件>")
        print("  未关：" + "、".join(f"{_KIND_NAME[k]} {n}" for k, n in report.store["open"].items()))
        own = inbox.own_waits(store.open_store())
        if own:
            print("  模块协调自开的等待记录：" + "、".join(f"W{n}（等 {r['about']}）" for n, r in own))
        for mod, r in review.progress(store.open_store()).items():
            print(f"  {mod} " + (f"返工中（审查第 {r['round']} 轮）" if r["state"] == "rework" else
                                 "审查中" + (f"（第 {r['round'] + 1} 轮）" if r["round"] else "")))
    print("模块协调")
    coord = (report.store or {}).get("coordinator")
    if coord is None:
        print("  没有（module-crew 对本项目的会话不注入任何规矩；要用就在想当模块协调的会话里 coordinator up）")
    else:
        state = ("已关闭" if coord["state"] != "active" else "已绑定会话" if coord["bound"]
                 else "未绑定会话（该会话运行 module-crew bind）")
        print(f"  {coord['name']}：在 {coord['home'] or '（集成分支没有被检出）'}，分支 {coord['branch'] or '?'}；{state}")
    stale = (report.store or {}).get("permissionsStale")
    if stale:
        print(f"  ⚠️ 权限规则只放行别的 module-crew 路径，当前入口会弹权限框：{'、'.join(stale)}；"
              "经用户原话再跑 module-crew permissions apply 补放行当前入口")
    lock = (report.store or {}).get("mergeLock")
    if lock:
        took = f"已跑 {lock['minutes']} 分钟" if lock["minutes"] is not None else "开始时间读不出"
        print(f"  合并 C{lock['approval']}（{lock['unit']}）" + ("的锁已失效（进程不在了；下一个写命令会在集成 checkout 干净时清掉）"
              if lock["stale"] else f"正在后台跑（{took}）：别的写命令会被挡住，等它结束"))
    unq = (report.store or {}).get("unqueued")
    if unq and unq["missingSeen"]:
        print("  集成分支：还没有记下认得的顶端（下次 merge run 或 module-crew unqueued 时记下）")
    elif unq and (unq["count"] or unq["notInHistory"]):
        print(f"  集成分支上有 {unq['count']} 个不经合并队列的提交：告诉用户一次，module-crew unqueued --notify 通知各模块同步"
              + ("（认得的顶端已不在集成分支上，请用户核对）" if unq["notInHistory"] else ""))
    seen = (report.store or {}).get("sightings") or {"count": 0, "recent": []}
    print(f"没登记的会话：{seen['count']} 个" + ("（最近 10 个）" if seen["count"] > len(seen["recent"]) else ""))
    for r in seen["recent"]:
        print(f"  {r['cwd']}（分支 {r['branch']}），首次 {r['firstSeen']}" + ("" if r["told"] else "，还没告诉用户"))
    rows = (report.store or {}).get("tasks")
    if rows is not None:
        from module_crew import tasks as task_mod
        print("任务")
        if not (rows["active"] or rows["queued"] or rows["recent"]):
            print("  没有（模块协调用 module-crew task add 记下要派的单个需求或 bug）")
        for t in rows["active"] + rows["queued"]:
            who = f"，派给 {t['assignee']}" if t.get("assignee") else ""
            line = f"  {t['label']}（{'bug' if t['type'] == 'bug' else '需求'}）{t['title']}：{task_mod.STATE_NAMES[t['state']]}{who}"
            if t.get("clashes"):
                line += "；和 " + "、".join(t["clashes"]) + " 重叠"
            print(line)
        if rows["recent"]:
            print("  最近完成：" + "、".join(f"{t['label']} {task_mod.STATE_NAMES[t['state']]}" for t in rows["recent"]))
    m = probe.summarize_map(report.map)
    print("模块进度")
    if m is None:
        print("  读不出（见体检 spec-guard 一项）")
    else:
        print(f"  模块 {m['done']}/{m['total']} 完成；spec-guard 当前：{m['activeModule'] or '无'}；spec-guard 进行中：{'、'.join(m['inProgress']) or '无'}")
        print("  （这是 spec-guard 按能力图算出的进度；由 module-crew 开工的模块见上面的「会话与待办」）")
    print("模块协调：Claude 桌面版；模块会话：Claude 或 Codex 桌面版")
    cadence, source, via_map = start.cadence_info(".", report.map)
    if via_map:
        print(f"评审节奏：{cadence}（来源：{source}，读自 spec-guard /map）")
    elif source == "default":
        print(f"评审节奏：{cadence}（项目没有设置 reviewCadence，按默认）")
    else:
        print(f"评审节奏：{cadence}（来源：{source}）")
    return 3 if report.blocked else 0


def _unqueued(args) -> int:
    from module_crew import unqueued
    db = store.open_store()
    found = unqueued.find(db, ".")
    if found.missing_seen:
        unqueued.mark_integration(db, ".", "unqueued")
        print("还没有记下 module-crew 认得的集成分支顶端：现在记下，以后的提交从这里算")
        return 0
    if args.json and not args.notify:
        print(json.dumps({"seen": found.seen, "head": found.head, "notInHistory": found.not_in_history,
                          "commits": found.commits}, ensure_ascii=False, indent=2))
        return 3 if found.commits else 0
    if found.not_in_history:
        print(f"module-crew 认得的顶端 {found.seen[:7]} 不在集成分支上（历史可能被改写过）：只列出当前顶端，请用户核对")
    print(unqueued.describe(found))
    for c in found.commits:
        print(f"  {c['short']} {c['at']} {c['author']}：{c['subject']}")
    if not found.commits:
        return 0
    if not args.notify:
        print("告诉用户一次；要通知各模块同步就加 --notify")
        return 3
    for x in unqueued.notify(db, "."):
        print(f"发送 同步基线通知 → {x['to']}，正文文件：{x['path']}")
    print("已记下当前顶端，这些提交不会再报")
    return 0


def _task_line(n: int, t: dict) -> str:
    from module_crew import tasks
    who = f"，派给 {t['assignee']}" if t.get("assignee") else ""
    return f"T{n}（{'bug' if t['type'] == 'bug' else '需求'}）{t['title']}：{tasks.STATE_NAMES[t['state']]}{who}"


def _task(args) -> int:
    from module_crew import tasks
    db = store.open_store()
    if args.action in ("add", "cancel", "scope"):
        original = _original(args.original, args.original_file)
        if original is None:
            return 2
    try:
        if args.action == "add":
            r = tasks.add(db, ".", args.type, args.title, args.what, args.expect.split(","), args.done, original,
                          caused_by=args.caused_by)
            if args.json:
                print(json.dumps({"number": r.number, "state": r.state, "clashes": r.clashes, "notes": r.notes},
                                 ensure_ascii=False, indent=2))
                return 0
            print(f"已记下任务 T{r.number}：{tasks.STATE_NAMES[r.state]}")
            for c in r.clashes:
                print(f"  重叠：{c}")
            for note in r.notes:
                print(f"  注意：{note}")
            return 0
        if args.action == "cancel":
            tasks.cancel(db, args.number, original)
            print(f"已取消 T{args.number}；已派出的话，告诉做事的会话停下")
            return 0
        if args.action == "scope":
            r = tasks.scope(db, args.number, args.expect.split(","), args.done, original)
            print(f"T{r.number} 的任务单已缩小，回到在做；把正文发给做事的会话：{r.path}")
            return 0
        if args.action == "dispatch":
            d = tasks.dispatch(db, ".", args.number)
            if args.json:
                print(json.dumps({"number": d.number, "worktree": d.worktree, "branch": d.branch, "relay": d.relay,
                                  "kickoff": d.kickoff, "kickoffPath": d.kickoff_path, "lines": d.lines},
                                 ensure_ascii=False, indent=2))
                return 0
            print(f"已派出 T{d.number}：worktree {d.worktree}（分支 {d.branch}），邮箱名 {d.relay}")
            print(f"开工说明：{d.kickoff_path}")
            print("下一步：用桌面版在这个 worktree 开新会话，第一条消息用开工说明全文；"
                  "这一轮是被别的会话消息叫醒的就只能出卡片，等用户点开")
            for line in d.lines:
                print(line)
            return 0
        if args.action == "next":
            promoted = tasks.next_ready(db, ".")
            if args.json:
                print(json.dumps({"ready": promoted}, ensure_ascii=False))
            else:
                print("提为可开：" + ("、".join(f"T{n}" for n in promoted) or "无"))
            return 0
    except tasks.TaskRefused as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 3
    records = {int(k): v for k, v in store.records(db, "task").items()}
    if args.action == "show":
        t = records.get(args.number)
        if t is None:
            print(f"❌ T{args.number} 不是任务", file=sys.stderr)
            return 3
        if args.json:
            print(json.dumps({"number": args.number, **t}, ensure_ascii=False, indent=2))
            return 0
        print(_task_line(args.number, t))
        print(f"  做什么：{t['what']}")
        print(f"  预计文件：{'、'.join(t['expectedFiles'])}")
        print(f"  完成标准：{t['done']}")
        if t.get("causedBy"):
            print(f"  由 {t['causedBy']} 带进来")
        if t.get("worktree"):
            print(f"  worktree：{t['worktree']}（分支 {t.get('branch')}）")
        if t.get("state") == "queued":
            clashes, _ = tasks.overlaps(db, ".", t["expectedFiles"], exclude=args.number)
            for c in clashes:
                print(f"  重叠：{c}")
        return 0
    rows = sorted((n, t) for n, t in records.items() if args.all or t["state"] not in tasks.FINAL)
    if args.json:
        print(json.dumps([{"number": n, **t} for n, t in rows], ensure_ascii=False, indent=2))
        return 0
    for n, t in rows:
        print(_task_line(n, t))
    if not rows:
        print("没有任务" if args.all else "没有在做或排队的任务")
    return 0


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as exc:
        print(f"❌ 读不到文件：{path}（{exc}）", file=sys.stderr)
        return None


def _inbox_add(path: str, sender: str, relay_id: int) -> int:
    text = _read(path)
    if text is None:
        return 2
    out = inbox.add(store.open_store(), text, sender, relay_id)
    print(f"类型：{out.kind}")
    for line in out.lines:
        print(line)
    if out.closed:
        print("已关闭：" + "、".join(refs.wait(n) if n in out.closed_waits else refs.fmt(n) for n in out.closed))
    if out.unmatched:
        print("没对上：" + "、".join(f"#{n}" for n in out.unmatched))
    for line in out.tell_sender:
        print(f"转告发件人：{line}")
    return out.code


def _answer(number: int, original: str | None, original_file: str | None, option: str | None) -> int:
    if original_file is not None:
        original = _read(original_file)
        if original is None:
            return 2
    try:
        reply = inbox.answer(store.open_store(), number, original, option)
    except inbox.AnswerRefused as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 3
    print(f"收件人：{reply.to}")
    _sent(reply.to)
    print(f"replyTo：{reply.reply_to}")
    print(f"正文文件：{reply.path}")
    for note in reply.notes:
        print(note)
    src = store.source_field().get("source")
    for x in inbox.resume_own_waits_now(store.open_store(), [f"C{number}"] + ([f"#{src['item']}"] if src else [])):
        print(f"你开的等待记录 W{x['wait']} 等的事已发生：发送 【已恢复】 → {x['to']}，正文文件：{x['path']}")
        _sent(x['to'])
    return 0


def _start_plan(as_json: bool) -> int:
    p = start.plan(".")
    if as_json:
        print(json.dumps({"slots": p.slots, "modules": p.modules, "conflicts": p.conflicts, "blockers": p.blockers,
                          "reasons": p.reasons},
                         ensure_ascii=False, indent=2))
    else:
        print(f"空位：{p.slots}")
        for b in p.blockers:
            print(f"❌ {b}")
        for m in p.modules:
            print(f"  {m['id']}（{m['responsibility']}）")
        for c in p.conflicts:
            print(f"⚠️ 冲突：{'、'.join(c.get('modules', []))} 在 {'、'.join(c.get('paths', []))}")
        if p.modules and not p.blockers:
            print(f"提议：开这 {len(p.modules)} 个吗？（问用户一次，答应后运行 start prepare）")
        elif not p.blockers:
            print("没有可开的模块：" if p.reasons else "没有可开的模块（能力图上的模块都已完成）")
            for r in p.reasons:
                print(f"  {r['module']}：{r['reason']}")
    return 0 if p.modules and not p.blockers else 3


def _start_prepare(modules: list[str], original: str | None, original_file: str | None, short: str | None,
                   max_modules: int | None, as_json: bool, host: str = "claude", commit_prefix: str | None = None) -> int:
    if original_file is not None:
        original = _read(original_file)
        if original is None:
            return 2
    res = start.prepare(".", modules, original, short, max_modules, host, commit_prefix)
    if as_json:
        print(json.dumps({"code": res.code, "approval": res.approval, "lines": res.lines,
                          "prepared": [{k: str(v) if isinstance(v, Path) else v for k, v in p.items()}
                                       for p in res.prepared]}, ensure_ascii=False, indent=2))
        return res.code
    for line in res.lines:
        print(line)
    for p in res.prepared:
        print(f"{p['id']}：worktree {p['worktree']}（分支 {p['branch']}），邮箱名 {p['relayName']}，开工说明 {p['kickoffPath']}，{p.get('role', '角色标记未设')}")
        if p.get("host") == "codex-desktop":
            print(f"  宿主：Codex 桌面版（用户手动在 Codex 里开任务，工作目录选 {p['worktree']}，第一条消息用开工说明全文）")
    return res.code


def _original(original: str | None, original_file: str | None) -> str | None:
    return _read(original_file) if original_file is not None else original


def _failure(args) -> int:
    db = store.open_store()
    if args.group == "sessions":
        rows = failure.sessions(db)
        if args.json:
            print(json.dumps({"schemaVersion": failure.SESSIONS_SCHEMA, "sessions": rows}, ensure_ascii=False, indent=2))
        else:
            print("\n".join(failure.render_sessions(rows)))
            own = inbox.own_waits(db)
            if own:
                print("模块协调自开的等待记录：" + "、".join(f"W{n}（等 {r['about']}，邮箱 #{r['relayId']} → {r['to']}）" for n, r in own))
        return 0
    if args.group == "resume-kit":
        kit = failure.resume_kit(db, args.module)
        print(f"模块：{kit.module}")
        print(f"邮箱名：{kit.name}")
        print(f"worktree：{kit.worktree}")
        print(f"恢复说明（正文 C{kit.body}）：{kit.path}")
        print("用户同意后：module-crew takeover " + kit.name + " --original-file <原话文件>，再在这个 worktree 开新会话，第一条消息用恢复说明全文")
        return 0
    original = _original(args.original, args.original_file)
    if original is None:
        return 2
    if args.group in ("suspend", "resume"):
        if args.group == "suspend":
            out = failure.suspend(db, args.module, args.reason, original)
            print(f"已挂起：{out.name}（不占名额；spec-guard 的挂起由模块会话在自己的 worktree 里做）")
        else:
            out = failure.resume(db, args.module, original)
            print(f"已取消挂起：{out.name}（重新占名额）")
        for x in out.sends:
            print(f"发送 【协调通知】 → {x['to']}：bridge_send bodyFile={x['path']}")
            _sent(x['to'])
        return 0
    failure.set_mode(db, not args.off, original)
    print("已改回并行：可以再开新模块" if args.off
          else "已退回串行：不再开新模块，已开的模块照常推进；提醒用户用 /spec-guard:config 关掉 moduleConcurrency")
    return 0


def _review(args) -> int:
    db = store.open_store()
    if args.action == "add":
        text = _read(args.file)
        if text is None:
            return 2
        out = review.add(db, text, args.sender, args.relay_id)
        print(f"类型：{out.kind}")
        for line in out.lines:
            print(line)
        for x in out.sends:
            print(f"发送 【交审】 → {x['to']}（送审），正文文件：{x['path']}")
            _sent(x['to'])
        return out.code
    if args.action == "show":
        try:
            print("\n".join(review.show(db, args.number, args.submission, args.spec_diff)))
        except review.ShowRefused as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 3
        return 0
    if args.action == "note":
        text = _read(args.file)
        if text is None:
            return 2
        try:
            res = review.note(db, args.number, args.sender, text)
        except review.NoteRefused as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 3
        for line in res.lines:
            print(line)
        for x in res.sends:
            print(f"发送 【协调通知】（返工） → {x['to']}，正文文件：{x['path']}")
            _sent(x['to'])
        if args.then_batch:
            wait = review.waiting(".")
            if wait:
                print("还在等：" + "、".join(wait) + "；提请批准的正文等它们有结论后再生成")
            elif args.for_hub:
                made = review.for_hub(".")
                if not made:
                    print("没有可以提请批准的交审")
                for n, path, _ in made:
                    print(f"提请批准正文（一个模块一条，正文 C{n}）：{path}")
            else:
                print("都有结论了：运行 module-crew review batch 交用户审")
        return 0
    if args.action == "batch" and args.for_hub:
        made = review.for_hub(".", args.parallel_with)
        held = review.held_for_old_hub(store.open_store(), ".")
        if held:        # crew-light-task: an inbox older than v2.5 may read T numbers as item numbers
            print("轻任务的提请批准没有交给决策收件箱（它的契约低于 v2.5）：在本会话直接问用户 "
                  + "、".join(f"C{n}" for n in held))
        if not made:
            print("没有可以提请批准的交审（审查中、返工中的不算）")
            return 3
        for n, path, text in made:
            print(text, end="")
            print(f"正文文件（正文 C{n}）：{path}\n")
        print(f"共 {len(made)} 条，一个模块一条：逐条用 bodyFile 原样发给决策收件箱")
        return 0
    if args.action == "batch":
        b = review.batch(".")
        if args.json:
            print(json.dumps(b, ensure_ascii=False, indent=2))
            return 0 if b["items"] else 3
        if not b["items"]:
            print("没有未答的交审")
            return 3
        by_number = {i["number"]: i for i in b["items"]}
        for g in b["groups"]:
            print(f"## {g['module']}（{g['responsibility']}）" if g["responsibility"] else f"## {g['module']}")
            for num in g["items"]:
                i = by_number[num]
                print(f"C{i['number']} {i['module']} 的 {review.NODE_NAME.get(i['node'], i['node'])}（{i['from']}）："
                      + "、".join(f["path"] for f in i["files"]))
                print("  要点：" + i["points"].replace("\n", "\n        "))
                print("  审查：" + review._review_text(i))
                if not i["ready"]:
                    print(f"  审查状态：{review.STATE_TEXT[i['reviewState']]}（不进提请批准，等它有结论）")
                elif i["round"]:
                    print(f"  经 {i['round']} 轮审查修改：{'；'.join(x for x in i['reworked'] if x)}")
        questions = review.question_lines(review.numbered_decisions(b))
        if questions:
            print("待你决定（没有决策收件箱时直接问你；批准时每个 D 都要答到）：")
            print("\n".join(questions))
        if not b["dependencyIssues"]:
            print("依赖：全部就绪")
        if not b["conflicts"]:
            print("并行边界重叠：无")
        for d in b["dependencyIssues"]:
            print(f"⚠️ 依赖未就绪：{d['module']} 依赖的 {'、'.join(d['missing'])} 既未完成、也没有 Spec 在本批或已批准")
        for c in b["conflicts"]:
            print(f"⚠️ 并行边界重叠：{'、'.join(c.get('modules', []))} 在 {'、'.join(c.get('paths', []))}")
        return 0
    original = _original(args.original, args.original_file)
    if original is None:
        return 2
    if args.action == "answer":
        try:
            reply = review.answer(db, args.number, original)
        except review.AnswerRefused as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 3
        print(f"收件人：{reply.to}")
        _sent(reply.to)
        print(f"replyTo：{reply.reply_to}")
        print(f"正文文件：{reply.path}")
        return 0
    res = review.approve(".", args.numbers, original)
    for line in res.lines:
        print(line)
    for x in res.sends:
        if x.get("wait"):
            print(f"你开的等待记录 W{x['wait']} 等的事已发生：发送 【已恢复】 → {x['to']}，正文文件：{x['path']}")
            _sent(x['to'])
            continue
        kind = {"user-reply": "【用户答复】", "resumed": "【已恢复】"}.get(x["kind"], "【协调通知】")
        reply_to = f"，replyTo：{x['replyTo']}" if x["replyTo"] is not None else ""
        also = f"，alsoAnswers：{'、'.join(map(str, x['alsoAnswers']))}" if x.get("alsoAnswers") else ""
        print(f"发送 {kind} → {x['to']}{reply_to}{also}，正文文件：{x['path']}")
        _sent(x['to'])
    return res.code


def _change(args) -> int:
    db = store.open_store()
    if args.action == "add":
        text = _read(args.file)
        if text is None:
            return 2
        out = changes.add(db, text, args.sender, args.relay_id)
        print(f"类型：{out.kind}")
        for line in out.lines:
            print(line)
        return out.code
    if args.action == "list":
        rows = changes.pending(db)
        if args.json:
            print(json.dumps([{"number": n, **{k: r[k] for k in ("from", "files", "what", "why", "fullyStopped", "hints")}}
                              for n, r in rows], ensure_ascii=False, indent=2))
        for n, r in rows if not args.json else []:
            hint = f"；提示：{'、'.join(r['hints'])}" if r["hints"] else ""
            print(f"C{n} {r['from']}：{'、'.join(r['files'])}——{r['what']}{'（完全停住）' if r['fullyStopped'] else ''}{hint}")
        if not rows and not args.json:
            print("没有未处理的公共变更请求")
        return 0 if rows else 3
    original = _original(args.original, args.original_file)
    if args.action == "answer":
        if original is None:
            return 2
        try:
            reply = changes.answer(db, args.number, original)
        except changes.AnswerRefused as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 3
        print(f"收件人：{reply.to}")
        _sent(reply.to)
        print(f"replyTo：{reply.reply_to}")
        print(f"正文文件：{reply.path}")
        return 0
    if args.original_file is not None and original is None:
        return 2
    res = changes.land(".", args.number, original, partial=getattr(args, "partial", False))
    for line in res.lines:
        print(line)
    for x in res.sends:
        reply_to = f"，replyTo：{x['replyTo']}" if x["replyTo"] is not None else ""
        print(f"发送 【协调通知】 → {x['to']}{reply_to}，正文文件：{x['path']}")
        _sent(x['to'])
    return res.code


def _merge(args) -> int:
    if args.action == "queue":
        rows = merge.queue(".")
        if args.json:
            print(json.dumps([{"approval": n, "module": r["module"], "review": r["review"]} for n, r in rows],
                             ensure_ascii=False, indent=2))
        else:
            for n, r in rows:
                print(f"C{n} {r['module']}（最终验收交审 C{r['review']}）")
            if not rows:
                print("合并队列是空的")
        return 0 if rows else 3
    if args.action == "push-plan":
        plan = merge.push_plan(".")
        if args.json:
            print(json.dumps({"code": plan.code, "remote": plan.remote, "branch": plan.branch, "base": plan.base,
                              "commits": plan.commits, "title": plan.title, "body": plan.body}, ensure_ascii=False, indent=2))
        else:
            for line in plan.lines:
                print(line)
            if plan.code == 0:
                print(f"PR 标题：{plan.title}")
                print(plan.body)
        return plan.code
    if args.action == "run":
        res = merge.run(".", args.check_command, args.replace_check)
        for line in res.lines:
            print(line)
        for x in res.sends:
            print(f"发送 【协调通知】（{x['kind']}）→ {x['to']}，正文文件：{x['path']}")
            _sent(x['to'])
        return res.code
    if args.action == "renotice":
        try:
            note = merge.renotice(store.open_store(), args.number, args.kind)
        except merge.AnswerRefused as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 3
        print(f"发送 退回通知（{'检查环境出了问题' if args.kind == 'env' else '模块需要修改'}）→ {note.to}，正文文件：{note.path}")
        _sent(note.to)
        return 0
    original = _original(args.original, args.original_file)
    if original is None:
        return 2
    if args.action == "approve":
        split = review.split_decisions(".", args.numbers, original)
        if split.missing:
            print("\n".join(review.chase_lines(split)))
            return 3
        try:
            for n in split.back:
                reply = review.answer(store.open_store(), n, original)
                print(f"C{n} 按用户的答复退回（没有批准）：发送 【用户答复】 → {reply.to}，replyTo：{reply.reply_to}，正文文件：{reply.path}")
                _sent(reply.to)
            for n in split.hold:
                print(f"C{n} 等审查结论：保持未答，没有批准")
            done = merge.approve_many(store.open_store(), split.approve, original) if split.approve else []
        except (merge.AnswerRefused, review.AnswerRefused) as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 3
        for res in done:
            print(f"合并批准事项 C{res.approval}，已排入本地合并队列")
            for n in res.superseded:
                print(f"合并批准 C{n} 被 C{res.approval} 取代，合并队列不再取它")
            print(f"收件人：{res.reply.to}")
            _sent(res.reply.to)
            print(f"replyTo：{res.reply.reply_to}")
            print(f"正文文件：{res.reply.path}")
        for closing in (merge.closing_all(store.open_store(), [r.reply.to for r in done], list(split.approve)) if done else []):
            if closing.get("wait"):
                print(f"你开的等待记录 W{closing['wait']} 等的事已发生：发送 【已恢复】 → {closing['to']}，正文文件：{closing['path']}")
            else:
                print(f"发送 【已恢复】 → {closing['to']}，正文文件：{closing['path']}（这个事项涉及的模块都转完后再发）")
            _sent(closing['to'])
        return 0
    if args.action == "revoke":
        try:
            note = merge.revoke(store.open_store(), args.number, original)
        except merge.AnswerRefused as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 3
        if note.superseded_by is None:
            print(f"已撤回合并批准 C{args.number}：交审重新打开，等用户新的答复")
        else:
            print(f"已撤回合并批准 C{args.number}；交审已被 C{note.superseded_by} 取代，不重开")
        print(f"发送 撤销批准通知 → {note.to}，正文文件：{note.path}")
        _sent(note.to)
        return 0
    if args.action == "tick":
        try:
            print(merge.tick(".", args.module, original))
        except merge.AnswerRefused as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 3
        return 0
    if args.action == "cleanup":
        res = merge.cleanup(".", args.module, original)
    else:
        res = merge.push(".", original)
    for line in res.lines:
        print(line)
    return res.code


_SENT: list[str] = []


def _sent(to: str) -> None:
    """Remember a recipient so main() can remind the coordinator to check it for a permission prompt (MC-8)."""
    _SENT.append(to)


def _remind() -> None:
    try:
        db = store.open_store()
    except store.StoreError:
        return
    devs = [n for n in dict.fromkeys(_SENT)
            if (store.get(db, "session", n) or {}).get("role") == "dev"]
    if devs:
        print(f"发完核对 {'、'.join(devs)} 是否停在权限弹窗：看 agent-relay 的会话状态或应用侧栏「需要用户」；"
              "卡住就按「去会话操作」报给决策收件箱（没有收件箱就告诉用户去哪个会话点）")


# crew-background-checks: commands that write the integration checkout wait while a merge runs in the background
_LOCKED = {("change", "land"), ("review", "approve"), ("merge", "tick"), ("merge", "cleanup"), ("coordinator", "down")}


# crew-session-handover decision 3: commands any session may run (read-only, the module side, hooks); every other
# command is the coordinator's and is refused (exit 7) when it comes from a conversation that is not the bound one.
# (group, action); action None = the whole group.
_ANY_SESSION = {("status", None), ("sessions", None), ("protocol", None), ("hook", None), ("bind", None), ("sync", None),
                ("host-check", None), ("store", "check"), ("start", "plan"), ("review", "batch"), ("review", "show"),
                ("change", "list"), ("merge", "queue"), ("merge", "push-plan"), ("source", "list"), ("source", "map"),
                ("task", "list"), ("task", "show"), ("task", "next"), ("permissions", "plan"), ("coordinator", "up")}


def _session_guard(args) -> int | None:
    key = (args.group, getattr(args, "action", None))
    if (args.group, None) in _ANY_SESSION or key in _ANY_SESSION:
        return None
    if args.group == "unqueued" and not getattr(args, "notify", False):
        return None
    if key == ("permissions", "verify") and not getattr(args, "record", None):
        return None
    caller = hooks.own_session_id()
    if not caller:
        return None                         # no session id: the user at a terminal
    try:
        coord = hooks.active_coordinator(store.open_store())
    except store.StoreError:
        return None
    if coord is None:
        return None
    name, rec = coord
    bound = (rec.get("hostSession") or {}).get("sessionId")
    if not bound or bound == caller:
        return None
    print(f"❌ 本会话不是登记的模块协调 {name}（登记的是另一个会话）：没有执行，什么都没写。"
          f"要由本会话接手，请用户同意后运行 module-crew bind {name} --takeover --original-file <原话文件>", file=sys.stderr)
    return 7


def _merge_lock_guard(args) -> int | None:
    key = (args.group, getattr(args, "action", None))
    if key not in _LOCKED and not (args.group == "unqueued" and getattr(args, "notify", False)):
        return None
    from module_crew import mergelock
    try:
        db = store.open_store()
    except store.StoreError:
        return None
    reason, note = mergelock.guard(db, ".")
    if note:
        print(note)
    if reason:
        print(f"❌ {reason}", file=sys.stderr)
        return 6
    return None


def main(argv: list[str] | None = None) -> int:
    _SENT.clear()
    code = _main(argv)
    if _SENT and "--json" not in (argv if argv is not None else sys.argv[1:]):
        _remind()
    return code


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="module-crew", description="module-crew 状态库")
    sub = parser.add_subparsers(dest="group")
    st = sub.add_parser("store", help="状态库")
    st.add_argument("action", choices=("init", "check"))
    pr = sub.add_parser("protocol", help="消息自检")
    pr.add_argument("action", choices=("check",))
    pr.add_argument("file")
    stp = sub.add_parser("status", help="体检与全貌（只读）")
    stp.add_argument("--json", action="store_true")
    ib = sub.add_parser("inbox", help="模块协调收件记账")
    ib.add_argument("action", choices=("add",))
    ib.add_argument("file")
    ib.add_argument("--from", dest="sender", required=True)
    ib.add_argument("--relay-id", type=int, required=True)
    an = sub.add_parser("answer", help="转达你的答复")
    an.add_argument("number", type=refs.parse)
    src = an.add_mutually_exclusive_group(required=True)
    src.add_argument("--original")
    src.add_argument("--original-file")
    an.add_argument("--option")
    sp = sub.add_parser("start", help="扩张点开工")
    sps = sp.add_subparsers(dest="action", required=True)
    spp = sps.add_parser("plan")
    spp.add_argument("--json", action="store_true")
    spr = sps.add_parser("prepare")
    spr.add_argument("modules", nargs="+")
    orig = spr.add_mutually_exclusive_group(required=True)
    orig.add_argument("--original")
    orig.add_argument("--original-file")
    spr.add_argument("--project-short")
    spr.add_argument("--max", type=int)
    spr.add_argument("--host", choices=("claude", "codex"), default="claude")
    spr.add_argument("--commit-prefix", help="module-crew 提交信息的前缀（项目配置；不设按 chore(crew): ，空字符串表示不加）")
    spr.add_argument("--json", action="store_true")
    rv = sub.add_parser("review", help="交审与批量批准")
    rvs = rv.add_subparsers(dest="action", required=True)
    ra = rvs.add_parser("add")
    ra.add_argument("file")
    ra.add_argument("--from", dest="sender", required=True)
    ra.add_argument("--relay-id", type=int, required=True)
    rb = rvs.add_parser("batch")
    rb.add_argument("--json", action="store_true")
    rb.add_argument("--for-hub", action="store_true", help="生成交给决策收件箱的【等待用户】正文（提请批准）")
    rb.add_argument("--parallel-with", type=int, help="与待决事项 #H 并行")
    rn = rvs.add_parser("note", help="记下审查者的【审查结论】")
    rn.add_argument("number", type=refs.parse, nargs="?", help="交审编号；一条消息有多段时可省略，按模块与节点对上")
    rn.add_argument("--then-batch", action="store_true", help="记完后接着看能不能提请批准")
    rn.add_argument("--for-hub", action="store_true", help="和 --then-batch 一起用：都有结论时直接生成交给决策收件箱的正文")
    rn.add_argument("--from", dest="sender", required=True)
    rn.add_argument("--file", required=True)
    rsh = rvs.add_parser("show", help="只读：交审的审查原文全文与 sha256")
    rsh.add_argument("number", type=refs.parse)
    rsh.add_argument("--submission", action="store_true", help="另外输出交审原文")
    rsh.add_argument("--spec-diff", action="store_true", help="只输出最终验收时 Spec 相对集成分支的改动差异")
    for name in ("approve", "answer"):
        r = rvs.add_parser(name)
        if name == "approve":
            r.add_argument("numbers", type=refs.parse, nargs="+")
        else:
            r.add_argument("number", type=refs.parse)
        g = r.add_mutually_exclusive_group(required=True)
        g.add_argument("--original")
        g.add_argument("--original-file")
    ch = sub.add_parser("change", help="公共变更请求")
    chs = ch.add_subparsers(dest="action", required=True)
    ca = chs.add_parser("add")
    ca.add_argument("file")
    ca.add_argument("--from", dest="sender", required=True)
    ca.add_argument("--relay-id", type=int, required=True)
    cl = chs.add_parser("list")
    cl.add_argument("--json", action="store_true")
    for name in ("land", "answer"):
        c = chs.add_parser(name)
        c.add_argument("number", type=refs.parse)
        g = c.add_mutually_exclusive_group(required=(name == "answer"))
        g.add_argument("--original")
        g.add_argument("--original-file")
        if name == "land":
            c.add_argument("--partial", action="store_true", help="清单里还有文件没改时，先落地已改的部分（要用户原话），请求保持打开")
    mg = sub.add_parser("merge", help="本地合并、收尾与远端 PR")
    mgs = mg.add_subparsers(dest="action", required=True)
    for name in ("queue", "push-plan"):
        mgs.add_parser(name).add_argument("--json", action="store_true")
    mr = mgs.add_parser("run")
    mr.add_argument("--check-command")
    mr.add_argument("--replace-check", action="store_true")
    rn2 = mgs.add_parser("renotice", help="按另一种原因重发退回通知（模块协调判断，不需要用户原话）")
    rn2.add_argument("number", type=refs.parse)
    kg = rn2.add_mutually_exclusive_group(required=True)
    kg.add_argument("--env", action="store_const", const="env", dest="kind", help="检查环境出了问题，模块不用改代码")
    kg.add_argument("--module", action="store_const", const="module", dest="kind", help="模块需要修改")
    for name, positional in (("approve", ("numbers", refs.parse)), ("revoke", ("number", refs.parse)),
                             ("cleanup", ("module", str)), ("tick", ("module", str)), ("push", None)):
        c = mgs.add_parser(name)
        if positional:
            c.add_argument(positional[0], type=positional[1], **({"nargs": "+"} if name == "approve" else {}))
        g = c.add_mutually_exclusive_group(required=True)
        g.add_argument("--original")
        g.add_argument("--original-file")
    hk = sub.add_parser("hook", help="插件钩子入口（只读，永远退出码 0）")
    hk.add_argument("event", choices=("session-start", "prompt", "session-end"))
    so = sub.add_parser("source", help="可信批准来源白名单（决策收件箱、指定审查者）")
    sos = so.add_subparsers(dest="action", required=True)
    soa = sos.add_parser("add")
    soa.add_argument("name")
    soa.add_argument("--kind", required=True, choices=sources.KINDS)
    soa.add_argument("--protocol", choices=sources.PROTOCOLS,
                     help="决策收件箱支持的 session-protocol 版本（只对 hub；不写按 2.2）")
    sosc = sos.add_parser("scope", help="补登记或修改审查者的负责范围")
    sosc.add_argument("name")
    for c in (soa, sosc):
        c.add_argument("--modules", help="审查者负责的模块，逗号分隔；全部写「全部」（lead 必填）")
        c.add_argument("--nodes", help=f"审查者负责的节点：{'、'.join(sources.NODES)}，逗号分隔；全部写「全部」（lead 必填）")
    sor = sos.add_parser("remove")
    sor.add_argument("name")
    for c in (soa, sosc, sor):
        g = c.add_mutually_exclusive_group(required=True)
        g.add_argument("--original")
        g.add_argument("--original-file")
    sos.add_parser("list").add_argument("--json", action="store_true")
    som = sos.add_parser("map")
    som.add_argument("ref", help="待决事项号 H，或 #module-crew 编号")
    som.add_argument("--json", action="store_true")
    wt = sub.add_parser("wait", help="模块协调自己发出的【等待其他会话】")
    wts = wt.add_subparsers(dest="action", required=True)
    wta = wts.add_parser("add", help="发出后立刻记账；所等事项的答复转达时会给出要发的【已恢复】")
    wta.add_argument("--file", required=True)
    wta.add_argument("--to", required=True, help="收件会话名（邮箱名）")
    wta.add_argument("--relay-id", type=int, required=True, help="发出那条消息的邮箱消息号")
    wta.add_argument("--about", required=True, help="所等的事项：#N（决策收件箱）或 C<N>")
    tc = sub.add_parser("ticket", help="等待记录（W 编号）")
    tcs = tc.add_subparsers(dest="action", required=True)
    tcc = tcs.add_parser("close", help="模块协调关等待记录（所等的事已发生／你说关）")
    tcc.add_argument("number", type=refs.parse)
    tcc.add_argument("--reason", required=True, choices=tuple(inbox.TICKET_REASONS))
    tcg = tcc.add_mutually_exclusive_group(required=True)
    tcg.add_argument("--original")
    tcg.add_argument("--original-file")
    uq = sub.add_parser("unqueued", help="集成分支上不经合并队列的提交：列出，或 --notify 通知各模块同步")
    uq.add_argument("--notify", action="store_true")
    uq.add_argument("--json", action="store_true")
    ta = sub.add_parser("task", help="模块协调的轻任务记录（单个需求或 bug，T 编号）")
    tas = ta.add_subparsers(dest="action", required=True)
    taa = tas.add_parser("add", help="记下用户要做的一件事；预计文件和在做的活重叠就排队")
    taa.add_argument("--type", required=True, choices=("feature", "bug"))
    taa.add_argument("--title", required=True)
    taa.add_argument("--what", required=True, help="做什么")
    taa.add_argument("--expect", required=True, help="预计改哪些文件，逗号分隔；以 / 结尾表示整个目录")
    taa.add_argument("--done", required=True, help="做到什么程度算完")
    taa.add_argument("--caused-by", help="bug 由哪个任务带进来：T<号> 或 C<号>")
    tal = tas.add_parser("list", help="在做与排队的任务；--all 含已完成")
    tal.add_argument("--all", action="store_true")
    tash = tas.add_parser("show")
    tash.add_argument("number", type=refs.parse)
    tas.add_parser("next", help="把排队里已不重叠的提为可开（bug 在前）")
    tsc = tas.add_parser("scope", help="升格请求选了缩小：改任务单，任务回到在做")
    tsc.add_argument("number", type=refs.parse)
    tsc.add_argument("--expect", required=True)
    tsc.add_argument("--done", required=True)
    tad = tas.add_parser("dispatch", help="派出可开的任务：建 worktree 与分支、登记轻任务会话、生成开工说明")
    tad.add_argument("number", type=refs.parse)
    tac = tas.add_parser("cancel")
    tac.add_argument("number", type=refs.parse)
    for c in (taa, tac, tsc):
        g = c.add_mutually_exclusive_group(required=True)
        g.add_argument("--original")
        g.add_argument("--original-file")
    for c in (taa, tal, tash, tas.choices["next"], tad):
        c.add_argument("--json", action="store_true")
    co = sub.add_parser("coordinator", help="把本会话升级为本项目的模块协调，或关闭它（都要用户原话）")
    cos = co.add_subparsers(dest="action", required=True)
    cou = cos.add_parser("up", help="升级：一个仓库只一个模块协调；前提同开工体检，不要求能力图")
    cou.add_argument("--short", help="项目简称（第一次升级必填）：小写字母、数字、连字符")
    cod = cos.add_parser("down", help="关闭：没有在用的模块会话时才可以；状态库保留")
    for c in (cou, cod):
        g = c.add_mutually_exclusive_group(required=True)
        g.add_argument("--original")
        g.add_argument("--original-file")
        c.add_argument("--json", action="store_true")
    bd = sub.add_parser("bind", help="登记本会话就是状态库里的某个会话（钩子只给登记过的会话注入角色）")
    bd.add_argument("name", help="开工说明或恢复说明里写的邮箱名")
    bg = bd.add_mutually_exclusive_group()
    bg.add_argument("--original", help="用户原话（登记模块协调身份时必填）")
    bg.add_argument("--original-file")
    bd.add_argument("--takeover", action="store_true", help="新会话接手模块协调（要用户原话；同一仓库任一目录）")
    tk = sub.add_parser("takeover", help="记录用户同意新会话接管邮箱名")
    tk.add_argument("name")
    tg = tk.add_mutually_exclusive_group(required=True)
    tg.add_argument("--original")
    tg.add_argument("--original-file")
    ss = sub.add_parser("suspend", help="挂起模块会话（等外部条件，不占名额）")
    ss.add_argument("module")
    ss.add_argument("--reason", required=True)
    sg = ss.add_mutually_exclusive_group(required=True)
    sg.add_argument("--original")
    sg.add_argument("--original-file")
    rs = sub.add_parser("resume", help="撤销挂起（要用户原话）")
    rs.add_argument("module")
    rg = rs.add_mutually_exclusive_group(required=True)
    rg.add_argument("--original")
    rg.add_argument("--original-file")
    sub.add_parser("sessions", help="列出模块会话的事实（只读）").add_argument("--json", action="store_true")
    pm = sub.add_parser("permissions", help="宿主权限预配：预览、凭用户原话写入、实测、撤销")
    pm_sub = pm.add_subparsers(dest="action", required=True)
    pm_sub.add_parser("plan", help="只读：每个 checkout 要写什么、能不能写").add_argument("--json", action="store_true")
    pv = pm_sub.add_parser("verify", help="实测清单；--record 记下模块协调看到的结果")
    pv.add_argument("--host", choices=("claude", "codex"), default="claude")
    pv.add_argument("--record", metavar="会话名")
    pv.add_argument("--allowed", choices=("ok", "prompted"))
    pv.add_argument("--denied", choices=("ok", "ran"))
    for name, text in (("apply", "凭用户原话写规则、装推送守门"), ("remove", "凭用户原话撤掉 module-crew 写的规则与钩子")):
        pa = pm_sub.add_parser(name, help=text)
        pg = pa.add_mutually_exclusive_group(required=True)
        pg.add_argument("--original")
        pg.add_argument("--original-file")
    sub.add_parser("host-check", help="在模块 worktree 里预检宿主能否完成工作（Codex 必跑）").add_argument("--json", action="store_true")
    sub.add_parser("sync", help="在模块 worktree 里把集成分支合进模块分支（本模块 Spec、tasks 冲突取集成分支版本）")
    sub.add_parser("resume-kit", help="生成换会话恢复说明").add_argument("module")
    se = sub.add_parser("serial", help="退回串行／恢复并行")
    se.add_argument("--off", action="store_true")
    seg = se.add_mutually_exclusive_group(required=True)
    seg.add_argument("--original")
    seg.add_argument("--original-file")
    _add_source_options(parser)
    args = parser.parse_args(argv)
    blocked = _session_guard(args)
    if blocked is not None:
        return blocked
    blocked = _merge_lock_guard(args)
    if blocked is not None:
        return blocked
    src = None
    if getattr(args, "source", None):
        if args.source_item is None or args.source_relay_id is None or not args.source_from:
            print("❌ 带 --source 时必须同时给 --source-item、--source-relay-id 与 --source-from", file=sys.stderr)
            return 2
        text = _original(getattr(args, "original", None), getattr(args, "original_file", None))
        if text is None:
            return 2
        try:
            info = sources.check(store.open_store(), args.source, args.source_item, args.source_relay_id, text,
                                 sender=args.source_from)
        except sources.SourceRefused as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 3
        except store.StoreError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
        args.original, args.original_file, src = info.original, None, info.source
        print(f"可信批准来源：{info.source['name']}（{info.source['kind']}）待决事项 #{info.source['item']}；用户原话：{info.original}")
    with store.approval_source(src):
        return _run(args)


def _add_source_options(parser: argparse.ArgumentParser) -> None:
    """Every command that takes the user's words can instead take a whitelisted source's message."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub in action.choices.values():
                _add_source_options(sub)
    if any("--original" in a.option_strings for a in parser._actions) and parser.prog.split()[1:2] != ["source"]:
        g = parser.add_argument_group("可信批准来源（决策收件箱或指定审查者转来的决定）")
        g.add_argument("--source", help="登记过的来源邮箱名；此时 --original(-file) 放对方消息全文")
        g.add_argument("--source-item", type=int, help="来源的事项号 H")
        g.add_argument("--source-relay-id", type=int, help="来源消息的邮箱消息号")
        g.add_argument("--source-from", help="这条消息实际的发件邮箱名（照抄 bridge_inbox）；必须就是来源本身")


def _permissions(args) -> int:
    from module_crew import permissions
    try:
        if args.action == "plan":
            p = permissions.plan(".")
            print(json.dumps(p, ensure_ascii=False, indent=2) if args.json else "\n".join(permissions.render_plan(p)))
            return 0
        if args.action == "verify":
            if args.record:
                if not (args.allowed and args.denied):
                    print("❌ --record 要同时给 --allowed 与 --denied", file=sys.stderr)
                    return 3
                print(permissions.record_verify(".", args.record, args.allowed, args.denied))
            else:
                print("\n".join(permissions.verify_list(".", args.host)))
            return 0
        if args.action in ("apply", "remove"):
            original = _original(args.original, args.original_file)
            if original is None:
                return 2
            print("\n".join(getattr(permissions, args.action)(".", original)))
            return 0
    except permissions.Refused as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 3
    except store.StoreError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    return 2


def _run(args) -> int:
    if args.group in ("suspend", "resume", "sessions", "resume-kit", "serial"):
        try:
            return _failure(args)
        except failure.FailureRefused as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 3
        except store.StoreError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
    if args.group == "permissions":
        return _permissions(args)
    if args.group == "sync":
        from module_crew import sync
        res = sync.run(".")
        print("\n".join(res.lines), file=sys.stderr if res.code == 3 else sys.stdout)
        return res.code
    if args.group == "host-check":
        from module_crew import hostcheck
        rep = hostcheck.run(".")
        if args.json:
            print(json.dumps({"checks": rep.checks, "module": rep.module, "host": rep.host}, ensure_ascii=False, indent=2))
        else:
            print("\n".join(hostcheck.render(rep)))
        return rep.code
    if args.group == "hook":
        try:
            out = hooks.run_hook(args.event, sys.stdin.read() if not sys.stdin.isatty() else "")
        except BaseException:
            out = ""
        if out:
            print(out)
        return 0
    if args.group == "source":
        try:
            db = store.open_store()
            if args.action == "map":
                raw = args.ref.strip()
                ref = raw.lstrip("#Cc")
                if not ref.isdigit():
                    print("❌ 编号要写：待决事项号 H（或 #H），或 module-crew 编号 C<N>", file=sys.stderr)
                    return 2
                if raw[:1] in ("C", "c"):
                    found = sources.map_crew(db, int(ref))
                    out = found if args.json else (f"C{ref} 的可信批准来源：{found['name']}（{found['kind']}）待决事项 #{found['item']}"
                                                   if found else f"C{ref} 没有外部来源（用户在本会话批准或尚未批准）")
                else:
                    rows = sources.map_item(db, int(ref))
                    out = rows if args.json else ("\n".join(f"C{r['number']} {r['kind']} {r['module'] or ''} {r['node'] or ''}".rstrip()
                                                             for r in rows) or f"没有经待决事项 #{ref} 批准的记录")
                print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out)
                return 0
            if args.action == "list":
                rows = sources.listing(db)
                if args.json:
                    print(json.dumps(rows, ensure_ascii=False, indent=2))
                else:
                    for r in rows:
                        ver = ""
                        if r["kind"] == "hub":
                            got = sources.hub_protocol(r)
                            ver = f"，契约 v{got}" + ("" if r.get("protocol") == got else f"（登记为 {r.get('protocol') or '未写'}，按 {got} 发）")
                        scope = f"，{sources.scope_text(r.get('scope'))}" if r["kind"] == "lead" else ""
                        print(f"{r['name']}（{r['kind']}{ver}{scope}）登记于 {r['addedAt']}")
                    if not rows:
                        print("没有登记的来源")
                return 0
            original = _original(args.original, args.original_file)
            if original is None:
                return 2
            if args.action == "add":
                scope = None
                if args.kind == "lead":
                    scope = sources.parse_scope(args.modules, args.nodes)
                elif args.modules is not None or args.nodes is not None:
                    raise sources.SourceRefused("只有审查者（lead）才登记负责范围")
                notes = sources.add(db, args.name, args.kind, original, args.protocol, scope)
                ver = f"，契约 v{args.protocol or sources.OLDEST_HUB}" if args.kind == "hub" else ""
                extra = f"，{sources.scope_text(scope)}" if scope else ""
                print(f"已登记可信批准来源 {args.name}（{args.kind}{ver}{extra}）")
                for line in notes:
                    print(line)
            elif args.action == "scope":
                scope = sources.parse_scope(args.modules, args.nodes)
                notes = sources.set_scope(db, args.name, scope, original)
                print(f"已登记审查者 {args.name} 的负责范围：{sources.scope_text(scope)}")
                for line in notes:
                    print(line)
            else:
                sources.remove(db, args.name, original)
                print(f"已撤掉来源 {args.name}")
            return 0
        except sources.SourceRefused as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 3
        except store.StoreError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
    if args.group == "wait":
        text = _read(args.file)
        if text is None:
            return 2
        try:
            n, again = inbox.add_own_wait(store.open_store(), text, args.to, args.relay_id, args.about)
        except inbox.AnswerRefused as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 3
        print(f"{'已记过' if again else '已记为'}模块协调自开的等待记录 W{n}（等 {args.about}，邮箱 #{args.relay_id}）")
        return 0
    if args.group == "ticket":
        original = _original(args.original, args.original_file)
        if original is None:
            return 2
        try:
            code = inbox.close_ticket(store.open_store(), args.number, args.reason, original)
        except inbox.AnswerRefused as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 3
        except store.StoreError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
        print(f"已关等待记录 {refs.wait(args.number)}（理由 {code}）")
        return 0
    if args.group == "unqueued":
        try:
            return _unqueued(args)
        except store.StoreError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
    if args.group == "task":
        try:
            return _task(args)
        except store.StoreError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
    if args.group == "coordinator":
        original = _original(args.original, args.original_file)
        if original is None:
            return 2
        from module_crew import coordinator
        try:
            code, lines = (coordinator.up(".", args.short, original) if args.action == "up"
                           else coordinator.down(".", original))
        except store.StoreError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps({"code": code, "lines": lines}, ensure_ascii=False, indent=2))
        else:
            print("\n".join(lines))
        return code
    if args.group == "bind":
        try:
            original = None
            if args.original is not None or args.original_file is not None:
                original = _original(args.original, args.original_file)
                if original is None:
                    return 2
            print(hooks.bind(store.open_store(), args.name, hooks.own_session_id(), os.getcwd(), original, takeover=args.takeover))
        except hooks.BindRefused as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 3
        except store.StoreError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
        return 0
    if args.group == "takeover":
        original = _original(args.original, args.original_file)
        if original is None:
            return 2
        try:
            print(hooks.takeover(store.open_store(), args.name, original))
        except hooks.TakeoverRefused as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 3
        except store.StoreError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
        return 0
    if args.group == "merge":
        try:
            return _merge(args)
        except store.StoreError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
    if args.group == "change":
        try:
            return _change(args)
        except store.StoreError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
    if args.group == "review":
        try:
            return _review(args)
        except store.StoreError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
    if args.group == "start":
        try:
            if args.action == "plan":
                return _start_plan(args.json)
            return _start_prepare(args.modules, args.original, args.original_file, args.project_short, args.max, args.json,
                                  args.host, args.commit_prefix)
        except store.StoreError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
    if args.group == "answer":
        try:
            return _answer(args.number, args.original, args.original_file, args.option)
        except store.StoreError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
    if args.group == "inbox":
        try:
            return _inbox_add(args.file, args.sender, args.relay_id)
        except store.StoreError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
    if args.group == "status":
        try:
            return _status(args.json)
        except store.NotInRepo as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 2
    if args.group == "protocol":
        return _protocol_check(args.file)
    if args.group != "store":
        print("用法：module-crew store init|check ／ module-crew protocol check <文件>", file=sys.stderr)
        return 2
    try:
        return _store_init() if args.action == "init" else _store_check()
    except (store.NotInRepo, store.StoreNotFound) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    except store.StoreCorrupt as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
