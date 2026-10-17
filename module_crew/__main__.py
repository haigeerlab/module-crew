"""CLI entry: python3 -m module_crew."""

from __future__ import annotations

import argparse
import sys

from module_crew import protocol, store


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="module-crew", description="module-crew 状态库")
    sub = parser.add_subparsers(dest="group")
    st = sub.add_parser("store", help="状态库")
    st.add_argument("action", choices=("init", "check"))
    pr = sub.add_parser("protocol", help="消息自检")
    pr.add_argument("action", choices=("check",))
    pr.add_argument("file")
    args = parser.parse_args(argv)
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
