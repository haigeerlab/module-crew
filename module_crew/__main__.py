"""CLI entry: python3 -m module_crew."""

from __future__ import annotations

import argparse
import sys

import json

from module_crew import probe, protocol, store


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
    args = parser.parse_args(argv)
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
