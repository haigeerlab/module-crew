"""Switch the whole crew between Claude Code and Codex in the gap between batches (see spec/crew-host-handover.md).

Only when a batch is closed: no module or task session in use, no merge queued or running, nothing waiting on the
user. Whether to switch, and to which side, is the user's call; module-crew never looks at quotas.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from module_crew import store

HOST_IDS = {"claude": "claude-desktop", "codex": "codex-desktop"}
HOST_NAMES = {"claude-desktop": "Claude Code", "codex-desktop": "Codex"}
BUSY_TASK_STATES = ("dispatched", "working", "returned", "escalated")
PLUGIN_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Check:
    id: str
    ok: bool
    reason: str


def codex_coordinator_skill() -> Path:
    """Where the Codex coordinator skill (module B, not this module) lives once it ships."""
    return PLUGIN_ROOT / "codex-skills" / "crew-coordinator" / "SKILL.md"


def _open(kind: str, db: store.Store) -> dict:
    return {k: v for k, v in store.records(db, kind).items() if v.get("state") != "closed"}


def readiness(db: store.Store, to: str | None = None) -> list[Check]:
    """Decision 1: the fixed list `handover --check` and `handover --to` share; `to` adds the module-B check."""
    sessions = store.records(db, "session")
    busy = sorted(f"{n}（{'模块 ' + str(r.get('module')) if r.get('role') == 'dev' else '轻任务 T' + str(r.get('task'))}）"
                  for n, r in sessions.items() if r.get("status") == "active" and r.get("role") in ("dev", "task"))
    tasks = sorted(f"T{r.get('number', k)}（{r.get('state')}）" for k, r in store.records(db, "task").items()
                   if r.get("state") in BUSY_TASK_STATES)
    items = _open("item", db)
    approvals = sorted(f"C{k}" for k, v in items.items() if v.get("kind") == "merge-approval")
    from module_crew import mergelock
    lock = mergelock.read(db)
    others = sorted(f"C{k}" for k, v in items.items() if v.get("kind") != "merge-approval")
    requests = sorted(_open("request", db))
    tickets = sorted(f"W{k}" for k in _open("ticket", db))
    coord = next((n for n, r in sessions.items() if r.get("role") == "coordinator" and r.get("status") == "active"), None)
    clears = sorted(n for n, h in store.records(db, "handover").items()
                    if h.get("state") == "open" and n != coord and (sessions.get(n) or {}).get("status") == "active")
    merge_reason = "；".join(x for x in (
        f"合并正在进行（批准事项 C{lock.get('approval')}）" if lock else "",
        "已批准未合并：" + "、".join(approvals) if approvals else "") if x)
    pending = "；".join(x for x in (
        "未结的事项：" + "、".join(others) if others else "",
        "未结的公共变更请求：" + "、".join(requests) if requests else "",
        "未结的等待记录：" + "、".join(tickets) if tickets else "") if x)
    checks = [
        Check("sessions", not busy, "还有在用的会话：" + "、".join(busy) if busy else "没有在用的模块会话与轻任务会话"),
        Check("tasks", not tasks, "还有没做完的任务：" + "、".join(tasks) if tasks else "没有派出或交回中的轻任务"),
        Check("merge", not merge_reason, merge_reason or "没有排队或进行中的合并"),
        Check("pending", not pending, pending or "module-crew 侧没有待用户批的事项"),
        Check("clear-handover", not clears,
              "还有没取走的清空交接：" + "、".join(clears) if clears else "没有未取走的清空交接"),
    ]
    if to == "codex":
        ok = codex_coordinator_skill().is_file()
        checks.append(Check("codex-coordinator-skill", ok, "插件里有 Codex 版模块协调规矩" if ok else
                            "Codex 版模块协调规矩还没发版（待定模块 B）：换到 Codex 后没人管合并与派活，先不换"))
    return checks


def ready(checks: list[Check]) -> bool:
    return all(c.ok for c in checks)


def check_lines(checks: list[Check], frm: str | None, to: str | None) -> list[str]:
    head = (f"换宿主：{HOST_NAMES.get(frm, '?')} → {HOST_NAMES.get(HOST_IDS.get(to, ''), '?')}" if to
            else f"换宿主：当前模块协调在 {HOST_NAMES.get(frm, '?')}")
    lines = [head] + [f"  {'✅' if c.ok else '❌'} {c.id}：{c.reason}" for c in checks]
    lines.append("  决策收件箱侧的待决事项 module-crew 看不全：请模块协调用 decision-inbox 的 waits 再看一眼")
    lines.append("具备换宿主的条件" if ready(checks) else "还不具备换宿主的条件：先处理上面打 ❌ 的项")
    return lines


def coordinator_host(db: store.Store) -> str | None:
    rec = next((r for r in store.records(db, "session").values()
                if r.get("role") == "coordinator" and r.get("status") == "active"), None)
    return None if rec is None else rec.get("host", "claude-desktop")


def ready_line(db: store.Store) -> str | None:
    """Decision 8: once a batch has merged and nothing is left in use, say the crew may switch hosts. Only a hint."""
    merged = any(v.get("kind") == "merge-approval" and v.get("closedReason") == "merged"
                 for v in store.records(db, "item").values())
    if not merged or not ready(readiness(db)):
        return None
    other = "claude" if coordinator_host(db) == "codex-desktop" else "codex"
    return (f"本批已收尾，具备换宿主的条件：要换到 {HOST_NAMES[HOST_IDS[other]]} 请用户明说，"
            f"再运行 module-crew coordinator handover --to {other}（换不换由用户决定）")


def pick_host(db: store.Store | None, host: str | None) -> tuple[str | None, str | None]:
    """Decision 5: `--host` defaults to the coordinator's host; a Codex coordinator takes no Claude sessions."""
    coord = coordinator_host(db) if db is not None else None
    if host is None:
        return None, "codex" if coord == "codex-desktop" else "claude"
    if host == "claude" and coord == "codex-desktop":
        return "模块协调在 Codex：Codex 叫不醒停掉的 Claude 会话，只能开 Codex 会话（不写 --host，或换回 Claude 后再开）", None
    return None, host


def check(project: str | os.PathLike, to: str | None = None) -> tuple[int, dict, list[str]]:
    """`coordinator handover --check`: read only. 0 ready, 3 not ready."""
    db = store.open_store(Path(project))
    checks = readiness(db, to)
    frm = coordinator_host(db)
    doc = {"ready": ready(checks), "from": frm, "to": HOST_IDS.get(to) if to else None,
           "checks": [{"id": c.id, "ok": c.ok, "reason": c.reason} for c in checks]}
    return (0 if doc["ready"] else 3), doc, check_lines(checks, frm, to)


GUIDE_DIR = "handover-guide"


def _step(n: int, where: str, what: str, done: str) -> list[str]:
    return [f"### 第 {n} 步", f"- 去哪个会话：{where}", f"- 做什么：{what}", f"- 做完的样子：{done}", ""]


def guide(to: str, name: str, entry: str, integration: str, original_file: str) -> str:
    """Decision 3: the step-by-step handover, every step says where to go, what to do and what done looks like."""
    bind = f"`{entry} bind {name} --takeover --original-file {original_file}`"
    lines = [f"# 换宿主交接说明：模块协调 {name} 换到 {HOST_NAMES[HOST_IDS[to]]}", "",
             f"集成 checkout：`{integration}`。邮箱名不变，仍是 {name}。",
             f"下面的接管（takeover）就是用户同意的接管，原话即本次 handover 的原话，已存成文件 `{original_file}`。", ""]
    if to == "codex":
        opening = (f"你是 module-crew 的模块协调 {name}，从 Claude Code 接手。依次：① 调 agent-relay 的 bridge_register："
                   f'{{agent:"{name}", takeover:true, wake:{{app:"codex", sessionId:<CODEX_THREAD_ID>}}}}'
                   "（takeover 与 wake 都要带：只带 host 时唤醒仍绑在旧的 Claude 会话上；被拒 holder-still-running 就请用户先归档原 Claude 会话）；"
                   f"② 运行 {bind}（写 .git 会弹提权，请用户在本线程批准）；③ 加载 Codex 版 crew-coordinator skill；"
                   f"④ 运行 `{entry} status`。之后每轮开头先 bridge_register "
                   f'{{agent:"{name}", wake:{{app:"codex", sessionId:<CODEX_THREAD_ID>}}}}（不带 takeover）：Codex 每轮重启 MCP。')
        lines += _step(1, f"Claude 上原来的模块协调 {name}（那个会话）", "让它停手，不再运行 module-crew 命令；然后在 Claude 桌面版侧栏归档这个会话",
                       "侧栏里这个会话已归档（agent-relay 才允许新线程接管邮箱名）")
        lines += _step(2, "Codex（ChatGPT 应用）", f"新建任务，工作目录选集成 checkout `{integration}`，把下面「开场文字」整段贴进去发出",
                       "新任务开始按开场文字做事")
        lines += _step(3, "刚开的 Codex 任务", "它运行 bind 时会弹提权：点「批准（Approve）」；能选本会话一直允许就选",
                       f"它报「已接管：本会话就是模块协调 {name}」，status 显示模块协调在 Codex")
        lines += _step(4, "Codex（ChatGPT 应用）", "在 Codex 里信任这个项目（项目的 .codex/rules 规则只在受信任时生效；module-crew 不替你改全局配置）",
                       "项目显示为受信任")
        lines += _step(5, "这个 Codex 协调任务", "以后每轮开头它先用自己的线程 id 重新 bridge_register（不带 takeover）；应用重启后要你点开它",
                       "别的会话发来的消息它能收到")
    else:
        opening = (f"你是 module-crew 的模块协调 {name}，从 Codex 接手。依次：① 调 agent-relay 的 bridge_register："
                   f'{{agent:"{name}", takeover:true, wake:"auto"}}（返回里会提示「无法确认之前的 Codex 会话是否已停」，用户已确认停了就继续）；'
                   f"② 运行 {bind}；③ 加载 crew-coordinator skill；④ 运行 `{entry} status`。")
        lines += _step(1, f"原 Codex 模块协调任务（{name}）", "让它停手，不再运行 module-crew 命令；之后不要再在那个任务里发话，确认它已停",
                       "你确认那个 Codex 任务已停（agent-relay 判断不了，它被接走后也收不到通知）")
        lines += _step(2, "Claude 桌面版", f"新开会话，目录选集成 checkout `{integration}`，把下面「开场文字」整段贴进去发出",
                       "新会话开始按开场文字做事")
        lines += _step(3, "刚开的 Claude 会话", "等它跑完接管与 bind；弹权限确认就点「允许（Yes）」，不要选本会话都允许",
                       f"它报「已接管：本会话就是模块协调 {name}」，status 显示模块协调在 Claude Code")
    lines += ["## 开场文字（整段贴进新会话）", "", opening, "",
              "## 下一批怎么开", "",
              f"start prepare 与 task dispatch 默认用新宿主（{HOST_NAMES[HOST_IDS[to]]}）。"
              + ("Codex 模块会话要你手动在 Codex 里开任务、工作目录选模块 worktree、贴开工说明；第一次提交会弹提权。" if to == "codex"
                 else "模块会话由模块协调照常开。"), ""]
    return "\n".join(lines)


def handover(project: str | os.PathLike, to: str, original: str, session_id: str | None = None) -> tuple[int, list[str]]:
    """Decision 2: check, move the registration, write the integration rules, write the guide. Nothing on refusal."""
    project = Path(project)
    if to not in HOST_IDS:
        return 2, ["没有执行，原因：", f"--to 只能是 {'／'.join(HOST_IDS)}"]
    if not original or not original.strip():
        return 3, ["没有执行，原因：", "用户原话不能为空：换宿主要用户在本会话明说"]
    db = store.open_store(project)
    from module_crew.hooks import active_coordinator
    coord = active_coordinator(db)
    if coord is None:
        return 3, ["没有执行，原因：", "本项目没有在用的模块协调"]
    name, rec = coord
    frm, target = rec.get("host", "claude-desktop"), HOST_IDS[to]
    if frm == target:
        return 3, ["没有执行，原因：", f"模块协调已经在 {HOST_NAMES[target]}"]
    checks = readiness(db, to)
    if not ready(checks):
        return 3, ["没有执行，原因：还不具备换宿主的条件"] + check_lines(checks, frm, to)[1:-1]
    from datetime import datetime
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = db.path / GUIDE_DIR
    folder.mkdir(exist_ok=True)
    original_file = folder / f"{stamp}-original.txt"
    original_file.write_text(original, encoding="utf-8")
    with db.transaction(actor=name) as tx:
        cur = tx.get("session", name)
        tx.put("session", name, {**cur, "host": target,
                                 "hostHandover": {"from": frm, "to": target, "at": store.now(), "original": original, "pending": True}},
               action="coordinator-handover", data={"original": original, "from": frm, "to": target, "sessionId": session_id})
    from module_crew import launcher, probe
    cfg = store.get(db, "config", "main") or {}
    integration = probe._checkout_of(project, cfg.get("integrationBranch", "")) or project
    from module_crew import permissions
    rules = permissions.follow_integration(project)
    if rules and rules.startswith("⚠️"):
        rules = "⚠️ 权限规则没写上：" + rules.split("：", 1)[1].split("（不影响开工")[0] + "（登记已改；处理后重跑 permissions apply）"
    text = guide(to, name, str(launcher.entry(db.path)), str(integration), str(original_file))
    if rules:
        text += f"\n## 权限规则\n\n{rules}\n"
    path = folder / f"{stamp}.md"
    path.write_text(text, encoding="utf-8")
    return 0, [f"已换宿主：模块协调 {name} 登记为 {HOST_NAMES[target]}（{HOST_NAMES[frm]} 的会话在新宿主接管前仍登记着，请它停手）",
               *([rules] if rules else []),
               f"交接说明已存到 {path}，全文如下；请把它给用户，照着一步步做：", "", text]
