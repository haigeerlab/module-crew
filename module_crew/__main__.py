"""CLI entry: python3 -m module_crew."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from module_crew import changes, hooks, inbox, merge, probe, protocol, review, start, store


def _store_init() -> int:
    db, created = store.init_store()
    print(f"{'已建立' if created else '已存在，未改动任何文件'}：{db.path}")
    return 0


def _store_check() -> int:
    db = store.open_store()
    report = store.check(db)
    print(f"状态库：{report['path']}")
    print(f"版本：{report['version']}")
    print(f"事件：{report['events']} 条；下一个编号：#{report['nextNumber']}")
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
_KIND_NAME = {"item": "事项", "request": "请求", "ticket": "等待单"}


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
        for s in report.store["sessions"] or [{"name": "（没有在用的会话）"}]:
            extra = f"（{s.get('role')}{'，' + s['module'] if s.get('module') else ''}）" if s.get("role") else ""
            print(f"  {s['name']}{extra}")
        print("  未关：" + "、".join(f"{_KIND_NAME[k]} {n}" for k, n in report.store["open"].items()))
    m = probe.summarize_map(report.map)
    print("模块进度")
    if m is None:
        print("  读不出（见体检 spec-guard 一项）")
    else:
        print(f"  模块 {m['done']}/{m['total']} 完成；当前：{m['activeModule'] or '无'}；进行中：{'、'.join(m['inProgress']) or '无'}")
    print("第一版只支持 Claude 桌面版")
    return 3 if report.blocked else 0


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
        print("已关闭：" + "、".join(f"#{n}" for n in out.closed))
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
    print(f"replyTo：{reply.reply_to}")
    print(f"正文文件：{reply.path}")
    return 0


def _start_plan(as_json: bool) -> int:
    p = start.plan(".")
    if as_json:
        print(json.dumps({"slots": p.slots, "modules": p.modules, "conflicts": p.conflicts, "blockers": p.blockers},
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
    return 0 if p.modules and not p.blockers else 3


def _start_prepare(modules: list[str], original: str | None, original_file: str | None, short: str | None,
                   max_modules: int | None, as_json: bool) -> int:
    if original_file is not None:
        original = _read(original_file)
        if original is None:
            return 2
    res = start.prepare(".", modules, original, short, max_modules)
    if as_json:
        print(json.dumps({"code": res.code, "approval": res.approval, "lines": res.lines,
                          "prepared": [{k: str(v) if isinstance(v, Path) else v for k, v in p.items()}
                                       for p in res.prepared]}, ensure_ascii=False, indent=2))
        return res.code
    for line in res.lines:
        print(line)
    for p in res.prepared:
        print(f"{p['id']}：worktree {p['worktree']}（分支 {p['branch']}），邮箱名 {p['relayName']}，开工说明 {p['kickoffPath']}")
    return res.code


def _original(original: str | None, original_file: str | None) -> str | None:
    return _read(original_file) if original_file is not None else original


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
        return out.code
    if args.action == "batch":
        b = review.batch(".")
        if args.json:
            print(json.dumps(b, ensure_ascii=False, indent=2))
            return 0 if b["items"] else 3
        if not b["items"]:
            print("没有未答的交审")
            return 3
        for i in b["items"]:
            print(f"#{i['number']} {i['module']} 的 {review.NODE_NAME.get(i['node'], i['node'])}（{i['from']}）："
                  + "、".join(f["path"] for f in i["files"]))
            print("  要点：" + i["points"].replace("\n", "\n        "))
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
        print(f"replyTo：{reply.reply_to}")
        print(f"正文文件：{reply.path}")
        return 0
    res = review.approve(".", args.numbers, original)
    for line in res.lines:
        print(line)
    for x in res.sends:
        kind = "【用户答复】" if x["kind"] == "user-reply" else "【协调通知】"
        reply_to = f"，replyTo：{x['replyTo']}" if x["replyTo"] is not None else ""
        print(f"发送 {kind} → {x['to']}{reply_to}，正文文件：{x['path']}")
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
            print(f"#{n} {r['from']}：{'、'.join(r['files'])}——{r['what']}{'（完全停住）' if r['fullyStopped'] else ''}{hint}")
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
        print(f"replyTo：{reply.reply_to}")
        print(f"正文文件：{reply.path}")
        return 0
    if args.original_file is not None and original is None:
        return 2
    res = changes.land(".", args.number, original)
    for line in res.lines:
        print(line)
    for x in res.sends:
        reply_to = f"，replyTo：{x['replyTo']}" if x["replyTo"] is not None else ""
        print(f"发送 【协调通知】 → {x['to']}{reply_to}，正文文件：{x['path']}")
    return res.code


def _merge(args) -> int:
    if args.action == "queue":
        rows = merge.queue(".")
        if args.json:
            print(json.dumps([{"approval": n, "module": r["module"], "review": r["review"]} for n, r in rows],
                             ensure_ascii=False, indent=2))
        else:
            for n, r in rows:
                print(f"#{n} {r['module']}（最终验收交审 #{r['review']}）")
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
        return res.code
    original = _original(args.original, args.original_file)
    if original is None:
        return 2
    if args.action == "approve":
        try:
            res = merge.approve(store.open_store(), args.number, original)
        except merge.AnswerRefused as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 3
        print(f"合并批准事项 #{res.approval}，已排入本地合并队列")
        print(f"收件人：{res.reply.to}")
        print(f"replyTo：{res.reply.reply_to}")
        print(f"正文文件：{res.reply.path}")
        return 0
    if args.action == "cleanup":
        res = merge.cleanup(".", args.module, original)
    else:
        res = merge.push(".", original)
    for line in res.lines:
        print(line)
    return res.code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="module-crew", description="module-crew 状态库")
    sub = parser.add_subparsers(dest="group")
    st = sub.add_parser("store", help="状态库")
    st.add_argument("action", choices=("init", "check"))
    pr = sub.add_parser("protocol", help="消息自检")
    pr.add_argument("action", choices=("check",))
    pr.add_argument("file")
    stp = sub.add_parser("status", help="体检与全貌（只读）")
    stp.add_argument("--json", action="store_true")
    ib = sub.add_parser("inbox", help="协调会话收件记账")
    ib.add_argument("action", choices=("add",))
    ib.add_argument("file")
    ib.add_argument("--from", dest="sender", required=True)
    ib.add_argument("--relay-id", type=int, required=True)
    an = sub.add_parser("answer", help="转达用户答复")
    an.add_argument("number", type=int)
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
    spr.add_argument("--json", action="store_true")
    rv = sub.add_parser("review", help="交审与批量批准")
    rvs = rv.add_subparsers(dest="action", required=True)
    ra = rvs.add_parser("add")
    ra.add_argument("file")
    ra.add_argument("--from", dest="sender", required=True)
    ra.add_argument("--relay-id", type=int, required=True)
    rb = rvs.add_parser("batch")
    rb.add_argument("--json", action="store_true")
    for name in ("approve", "answer"):
        r = rvs.add_parser(name)
        if name == "approve":
            r.add_argument("numbers", type=int, nargs="+")
        else:
            r.add_argument("number", type=int)
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
        c.add_argument("number", type=int)
        g = c.add_mutually_exclusive_group(required=(name == "answer"))
        g.add_argument("--original")
        g.add_argument("--original-file")
    mg = sub.add_parser("merge", help="本地合并、收尾与远端 PR")
    mgs = mg.add_subparsers(dest="action", required=True)
    for name in ("queue", "push-plan"):
        mgs.add_parser(name).add_argument("--json", action="store_true")
    mr = mgs.add_parser("run")
    mr.add_argument("--check-command")
    mr.add_argument("--replace-check", action="store_true")
    for name, positional in (("approve", ("number", int)), ("cleanup", ("module", str)), ("push", None)):
        c = mgs.add_parser(name)
        if positional:
            c.add_argument(positional[0], type=positional[1])
        g = c.add_mutually_exclusive_group(required=True)
        g.add_argument("--original")
        g.add_argument("--original-file")
    hk = sub.add_parser("hook", help="插件钩子入口（只读，永远退出码 0）")
    hk.add_argument("event", choices=("session-start", "prompt"))
    tk = sub.add_parser("takeover", help="记录用户同意新会话接管邮箱名")
    tk.add_argument("name")
    tg = tk.add_mutually_exclusive_group(required=True)
    tg.add_argument("--original")
    tg.add_argument("--original-file")
    args = parser.parse_args(argv)
    if args.group == "hook":
        try:
            out = hooks.run_hook(args.event, sys.stdin.read() if not sys.stdin.isatty() else "")
        except BaseException:
            out = ""
        if out:
            print(out)
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
            return _start_prepare(args.modules, args.original, args.original_file, args.project_short, args.max, args.json)
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
