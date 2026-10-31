"""Move an unfinished batch from Codex to Claude Code in one step (see spec/crew-live-rehost.md).

The user starts it from a new, unregistered Claude conversation in the integration checkout, without the old Codex
coordinator's help. `--check` shows what moves and a confirmation code; `--to claude` needs the user's words with
that code. Open items, requests and waits stay keyed by relay name, so they carry over untouched.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from module_crew import store
from module_crew.handover import Check, ready

FROM, TO = "codex-desktop", "claude-desktop"
OFFLOAD_OPEN = ("running", "needs-input", "stopped", "timeout")
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"     # no 0/O/1/I
DIRTY_SHOWN = 50
GIT_TIMEOUT = 30


def _git(cwd: str | os.PathLike, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=GIT_TIMEOUT)


def movers(db: store.Store) -> list[tuple[str, dict]]:
    """The coordinator and every module or task session in use: all of them move together."""
    return [(n, r) for n, r in sorted(store.records(db, "session").items())
            if r.get("status") == "active" and r.get("role") in ("coordinator", "dev", "task")]


def snapshot(worktree: str | None) -> dict:
    """HEAD and the uncommitted files of a worktree, as git prints them (sorted, so the code does not wobble)."""
    if not worktree or not Path(worktree).is_dir():
        return {"head": None, "dirty": []}
    try:
        head = _git(worktree, "rev-parse", "HEAD")
        status = _git(worktree, "status", "--porcelain=v1", "-uall")
    except (OSError, subprocess.TimeoutExpired):
        return {"head": None, "dirty": []}
    return {"head": (head.stdout.strip() or None) if head.returncode == 0 else None,
            "dirty": sorted(l for l in status.stdout.splitlines() if l.strip()) if status.returncode == 0 else []}


def integration(db: store.Store, project: str | os.PathLike) -> Path | None:
    from module_crew import probe
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch")
    found = probe._checkout_of(Path(project), branch) if branch else None
    return Path(os.path.realpath(found)) if found else None


def caller_host() -> str | None:
    """'claude-desktop', 'codex-desktop', or None for the user at a terminal."""
    if (os.environ.get("CLAUDE_CODE_SESSION_ID") or "").strip():
        return TO
    return FROM if (os.environ.get("CODEX_THREAD_ID") or "").strip() else None


def _inside(path: str, root: Path) -> bool:
    here = os.path.realpath(path)
    return here == str(root) or here.startswith(str(root) + os.sep)


def start_dir(db: store.Store, session_id: str | None) -> str | None:
    """Where the calling conversation was started, as the SessionStart hook recorded it (S56); None if never seen."""
    seen = store.get(db, "sighting", session_id) if session_id else None
    return (seen or {}).get("cwd")


def _where_check(db: store.Store, home: Path | None, cwd: str | os.PathLike, session_id: str | None) -> Check:
    """A conversation is judged by its start directory too, so a `cd` in the command is not enough; a terminal by its cwd."""
    need = f"要在集成 checkout {home or '（集成分支没有被检出）'} 里"
    if home is None or not _inside(str(cwd), home):
        return Check("cwd", False, need + "运行")
    if not session_id:
        return Check("cwd", True, f"当前目录在集成 checkout {home}")
    start = start_dir(db, session_id)
    if start is None:
        return Check("cwd", False, f"钩子没有记下本会话的启动目录：{need}新开一个 Claude 会话再发起")
    ok = _inside(start, home)
    return Check("cwd", ok, f"当前目录与会话启动目录都在集成 checkout {home}" if ok else
                 f"会话启动目录是 {start}：{need}新开一个 Claude 会话再发起（命令里 cd 过去不算）")


def readiness(db: store.Store, project: str | os.PathLike, cwd: str | os.PathLike,
              session_id: str | None) -> list[Check]:
    """Decision 1: the fixed list `rehost --check` and `rehost --to` share."""
    from module_crew import hooks, mergelock, probe
    moving = movers(db)
    coord = next(((n, r) for n, r in moving if r.get("role") == "coordinator"), None)
    coord_host = None if coord is None else coord[1].get("host", TO)
    on_claude = sorted(n for n, r in moving if r.get("role") != "coordinator" and r.get("host", TO) != FROM)
    lock = mergelock.read(db)
    offloads = sorted(f"{m}（{r.get('state')}）" for m, r in store.records(db, "offload").items()
                      if r.get("state") in OFFLOAD_OPEN)
    found = probe.find_plugin("spec-guard", project)
    host = caller_host()
    bound = hooks.registration_of(db, session_id)
    home = integration(db, project)
    caller_reason = ("Codex 会话不能发起：迁到 Claude 要在 Claude 会话里做" if host == FROM else
                     f"本会话已登记为 {bound[0]}：要在还没登记的 Claude 会话里发起" if bound else
                     "调用者是还没登记的 Claude 会话" if host == TO else "调用者在终端（读不到会话编号）")
    return [
        Check("coordinator-host", coord_host == FROM,
              "模块协调登记在 Codex" if coord_host == FROM else
              "本项目没有在用的模块协调" if coord is None else
              "模块协调登记在 Claude：批次内迁移只做 Codex→Claude（空档换宿主用 coordinator handover）"),
        Check("all-codex", not on_claude,
              "在用的模块会话、轻任务会话都在 Codex" if not on_claude else
              "有登记在 Claude 的会话，混搭不迁：" + "、".join(on_claude)),
        Check("merge", lock is None,
              "没有进行中的合并" if lock is None else f"合并正在进行（批准事项 C{lock.get('approval', '?')}）：等它结束再迁"),
        Check("offload", not offloads,
              "没有未结的外包" if not offloads else "外包没结：" + "、".join(offloads)),
        Check("spec-guard", not isinstance(found, str),
              "本机 Claude 装着 spec-guard" if not isinstance(found, str) else f"找不到 spec-guard（{found}）：迁过去的会话离不开它"),
        Check("caller", host != FROM and bound is None, caller_reason),
        _where_check(db, home, cwd, session_id),
    ]


def state_of(db: store.Store) -> dict:
    """What the confirmation code is taken over: who moves, where they are bound, and each worktree's state."""
    from module_crew import mergelock
    rows = []
    for name, rec in movers(db):
        row = {"name": name, "role": rec.get("role"), "host": rec.get("host", TO),
               "session": (rec.get("hostSession") or {}).get("sessionId")}
        if rec.get("role") != "coordinator":
            row.update(worktree=rec.get("worktree"), **snapshot(rec.get("worktree")))
        rows.append(row)
    return {"sessions": rows, "merge": mergelock.read(db) is not None,
            "offload": {m: r.get("state") for m, r in sorted(store.records(db, "offload").items())}}


def confirm_code(state: dict) -> str:
    """Decision 3: six characters from the state's hash; nothing is stored."""
    digest = hashlib.sha256(json.dumps(state, sort_keys=True, ensure_ascii=False).encode("utf-8")).digest()
    return "".join(CODE_ALPHABET[b % len(CODE_ALPHABET)] for b in digest[:6])


def _who(row: dict, rec: dict) -> str:
    return ("模块协调" if row["role"] == "coordinator" else
            f"模块 {rec.get('module')}" if row["role"] == "dev" else f"轻任务 T{rec.get('task')}")


def session_lines(db: store.Store, state: dict) -> list[str]:
    sessions = store.records(db, "session")
    lines = ["要迁的会话（邮箱名不变）："]
    for row in state["sessions"]:
        rec = sessions.get(row["name"]) or {}
        lines.append(f"  {row['name']}（{_who(row, rec)}）")
        if row["role"] == "coordinator":
            continue
        head = (row.get("head") or "读不到")[:7]
        dirty = row.get("dirty") or []
        lines.append(f"    worktree：{row.get('worktree')}，HEAD {head}，未提交改动 {len(dirty)} 个（原样带过去，盘点时由用户定留还是丢）")
        lines += [f"      {l}" for l in dirty[:DIRTY_SHOWN]]
        if len(dirty) > DIRTY_SHOWN:
            lines.append(f"      另有 {len(dirty) - DIRTY_SHOWN} 个")
    return lines


def check(project: str | os.PathLike, cwd: str | os.PathLike, session_id: str | None) -> tuple[int, dict, list[str]]:
    """`coordinator rehost --check`: read only. 0 ready (with a code), 3 not ready (no code)."""
    db = store.open_store(Path(project))
    checks = readiness(db, project, cwd, session_id)
    state = state_of(db)
    ok = ready(checks)
    code = confirm_code(state) if ok else None
    start = start_dir(db, session_id)
    doc = {"ready": ok, "code": code, "from": FROM, "to": TO, "startDir": start,
           "checks": [{"id": c.id, "ok": c.ok, "reason": c.reason} for c in checks],
           "sessions": [{"name": r["name"], "role": r["role"],
                         "module": (store.get(db, "session", r["name"]) or {}).get("module"),
                         "task": (store.get(db, "session", r["name"]) or {}).get("task"),
                         "worktree": r.get("worktree"), "head": r.get("head"), "dirty": r.get("dirty")}
                        for r in state["sessions"]]}
    lines = ["批次内迁移：Codex → Claude Code"] + [f"  {'✅' if c.ok else '❌'} {c.id}：{c.reason}" for c in checks]
    if session_id:
        lines.append(f"发起会话的启动目录：{start or '钩子没有记下'}")
    lines += session_lines(db, state)
    lines.append("未结的事项、公共变更请求、等待记录、轻任务都按邮箱名原样带过去，不用处理；"
                 "决策收件箱侧的待决事项 module-crew 看不全，请用 decision-inbox 的 waits 再看一眼")
    if ok:
        lines += [f"确认码：{code}",
                  "把上面整段给用户看。用户同意时，原话里要有这个确认码，并写明 Codex 里的旧会话（上面每一个）已亲手停下并归档；"
                  f"再运行 module-crew coordinator rehost --to claude --code {code} --original-file <原话文件>。状态一变确认码就变，要重新 --check"]
    else:
        lines.append("还不能迁：先处理上面打 ❌ 的项")
    return (0 if ok else 3), doc, lines


STOPPED_WORDS = ("已停", "停了")      # Q2 A: the user says the old Codex sessions are stopped


def may_start(db: store.Store, project: str | os.PathLike, cwd: str | os.PathLike, session_id: str | None) -> str | None:
    """Decision 2: the narrow gap in the write-command guard. None, or why this caller may not start a move (exit 7)."""
    by_id = {c.id: c for c in readiness(db, project, cwd, session_id)}
    for cid in ("caller", "cwd", "coordinator-host"):
        if not by_id[cid].ok:
            return by_id[cid].reason
    return None


def words_problem(original: str, code: str) -> str | None:
    if not original or not original.strip():
        return "用户原话不能为空：迁移要用户在本会话明说"
    if code not in original:
        return f"用户原话里没有确认码 {code}：请把 --check 的预览给用户看，用户同意时原话要带上确认码"
    if not any(w in original for w in STOPPED_WORDS):
        return "用户原话没说 Codex 里的旧会话已停：请用户先在 Codex 里亲手停下并归档它们，再在原话里写明「已停」"
    return None


def rehost(project: str | os.PathLike, original: str, code: str, session_id: str | None,
           cwd: str | os.PathLike) -> tuple[int, list[str]]:
    """Decision 4: check, then move every registration in one transaction. Nothing is written on refusal."""
    from module_crew import hooks
    db = store.open_store(Path(project))
    refused = may_start(db, project, cwd, session_id)
    if refused:
        return 7, ["没有执行，什么都没写，原因：", refused]
    problem = words_problem(original, code or "")
    if problem:
        return 3, ["没有执行，什么都没写，原因：", problem]
    checks = readiness(db, project, cwd, session_id)
    if not ready(checks):
        return 3, ["没有执行，什么都没写，原因：还不能迁"] + [f"  ❌ {c.id}：{c.reason}" for c in checks if not c.ok]
    state = state_of(db)
    if confirm_code(state) != code:
        return 3, ["没有执行，什么都没写，原因：", "预览之后状态变了（确认码对不上），请重新 --check 给用户看"]
    rows = {r["name"]: r for r in state["sessions"]}
    at = store.now()
    with db.transaction(actor="rehost") as tx:
        batch = tx.allocate_number()
        for name, rec in movers(db):
            cur = tx.get("session", name)
            old = (cur.get("hostSession") or {}).get("sessionId")
            moved = {k: v for k, v in cur.items() if k != "hostSession"}
            moved["host"] = TO
            if old:
                moved["previousSessions"] = (list(cur.get("previousSessions") or [])
                                             + [{"sessionId": old, "at": at, "reason": "rehost"}])[-hooks.PREVIOUS_KEPT:]
            mark = {"from": FROM, "at": at, "original": original, "batch": batch}
            new_id = None
            if cur.get("role") == "coordinator":
                moved["hostHandover"] = {"from": FROM, "to": TO, "at": at, "original": original, "pending": False}
                if session_id:
                    moved["hostSession"] = hooks.identity(session_id)
                    new_id = session_id
            else:
                row = rows[name]
                mark.update(snapshot={"head": row.get("head"), "dirty": row.get("dirty") or []}, inventory="pending")
            mark["before"] = cur                 # decision 7: --undo puts this back exactly
            moved["rehost"] = mark
            tx.put("session", name, moved, action="rehosted",
                   data={"original": original, "batch": batch, "oldSessionId": old, "newSessionId": new_id})
            if new_id:
                hooks._clear_sighting(tx, new_id, name)
    return 0, after(db, project, batch, original, session_id)


GUIDE_DIR = "rehost-guide"


def kit_note(name: str, rec: dict, batch: int, original_file: str) -> list[str]:
    """Decision 9: what a moved session does first; the move's words are the user's consent to every takeover."""
    snap = (rec.get("rehost") or {}).get("snapshot") or {}
    dirty = snap.get("dirty") or []
    task = rec.get("task")
    lines = [f"这是批次内迁移（Codex→Claude，迁移 #{batch}）的恢复：Codex 里原来的会话已被用户停下归档，你在原 worktree 里接着做。",
             f"用户这次迁移的原话就是对接管 {name} 的同意（原话文件 {original_file}）。依次：",
             f'① 调 agent-relay 的 bridge_register：{{agent:"{name}", takeover:true, wake:"auto"}}'
             "（提示无法确认之前的 Codex 会话是否已停时，用户已在原话里确认停了，继续）；",
             f"② 运行 `module-crew bind {name}`；",
             f"③ 运行 `module-crew rehost show {name}`，对照下面的快照：HEAD 或未提交文件对不上就停下，"
             "发【等待其他会话】给模块协调，说 Codex 里的旧会话可能没停；",
             "④ 对照已批的 Spec 与 Plan 盘点：做对了哪些、要返工哪些、每个未提交文件留还是丢，"
             "作为【等待用户】「类型：中途检查点」发给模块协调；用户的答复到之前不写代码、不提交；",
             "⑤ 用户选「丢」的未提交改动用 `git stash push -u -m \"rehost-" + name + "\"` 收起（找得回来），不删文件。",
             "", f"迁移时的快照：HEAD {(snap.get('head') or '读不到')[:12]}，未提交改动 {len(dirty)} 个（原样带过来，没动过）"]
    lines += [f"  {l}" for l in dirty[:DIRTY_SHOWN]]
    if len(dirty) > DIRTY_SHOWN:
        lines.append(f"  另有 {len(dirty) - DIRTY_SHOWN} 个（rehost show 里有全部）")
    if task is not None:
        lines.append(f"轻任务 T{task}：任务单用 `module-crew task show T{task}` 看；盘点对照任务单的完成标准。")
    return lines


def _rules(project: str | os.PathLike, db: store.Store) -> list[str]:
    """Decision 4 ③: Claude rules for the integration checkout and every moved worktree; a failure never rolls back."""
    from module_crew import permissions
    if not ((store.get(db, "config", "main") or {}).get("permissions") or {}).get("applied"):
        return ["项目没有 permissions apply 过：没写 Claude 规则，开会话后会多弹确认；要预配就凭用户原话运行 module-crew permissions apply"]
    lines = [permissions.follow_integration(project) or "集成 checkout：没有要写的规则"]
    for name, rec in movers(db):
        if rec.get("role") != "coordinator":
            lines.append(permissions.follow(project, name) or f"{name}：没有要写的规则")
    return lines


def guide(coord: str, kits: list, integration_dir: str, original_file: str, rules: list[str], bound: bool) -> str:
    from module_crew.handover import _step
    lines = [f"# 批次内迁移说明：模块协调 {coord} 与 {len(kits)} 个会话从 Codex 迁到 Claude Code", "",
             f"集成 checkout：`{integration_dir}`。邮箱名都不变。用户这次的原话（已存为 `{original_file}`）就是对下面每一次接管的同意。", ""]
    lines += _step(1, "Codex（ChatGPT 应用）", "核对旧会话都已停下并归档：" + "、".join([coord] + [k.name for k in kits]),
                   "Codex 里这些任务都已归档，不再在里面发话")
    lines += _step(2, "本会话（新的模块协调）" if bound else "Claude 桌面版新会话（目录选集成 checkout，不用 worktree）",
                   ("" if bound else f"运行 `module-crew bind {coord} --takeover --original-file {original_file}`；")
                   + f'调 bridge_register {{agent:"{coord}", takeover:true, wake:"auto"}}，加载 crew-coordinator skill，运行 `module-crew status`',
                   f"status 显示模块协调 {coord} 在 Claude Code，收件箱里没读的消息照常读到")
    lines += _step(3, f"模块协调 {coord}",
                   "按 crew-coordinator 的开会话做法，为下面每个会话开一个 Claude 会话：工作目录选它原来的 worktree（不新建 worktree），"
                   "首条消息贴它的恢复说明",
                   "每个新会话按恢复说明接管邮箱名、bind、rehost show")
    lines += ["恢复说明：", *[f"- {k.name}（{k.module}）：worktree `{k.worktree}`，正文 #{k.body}（{k.path}）" for k in kits], ""]
    lines += _step(4, "每个迁来的会话", "对照已批 Spec、Plan 盘点，作为【等待用户】「类型：中途检查点」发给模块协调；用户点头前不写代码",
                   "模块协调收到每个会话的盘点")
    lines += _step(5, f"模块协调 {coord}", "把盘点照常交用户；用户的答复到了，转达并运行 "
                   "`module-crew rehost release <邮箱名> --original-file <答复原话>` 解除盘点闸",
                   "status 里不再有「迁来待盘点」")
    lines += _step(6, f"模块协调 {coord}", "看下面的权限规则；开会话后按 crew-coordinator 跑 permissions verify 实测",
                   "每个会话的权限实测记录都在")
    lines += ["## 权限规则", "", *rules, "",
              "## 撤回", "", "迁来的会话一个都还没 bind 之前，可以凭用户原话运行 `module-crew coordinator rehost --undo --original-file <原话文件>` 撤回；"
              "有会话 bind 之后不能撤回。", ""]
    return "\n".join(lines)


def after(db: store.Store, project: str | os.PathLike, batch: int, original: str, session_id: str | None) -> list[str]:
    """Decision 4 ③④: rules, one recovery kit per moved session, and the guide (printed and kept in the store)."""
    from datetime import datetime
    from module_crew import failure
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = db.path / GUIDE_DIR
    folder.mkdir(exist_ok=True)
    original_file = folder / f"{stamp}-original.txt"
    original_file.write_text(original, encoding="utf-8")
    rules = _rules(project, db)
    sessions = movers(db)
    coord = next(n for n, r in sessions if r.get("role") == "coordinator")
    kits = [failure.session_kit(db, n, kit_note(n, r, batch, str(original_file))) for n, r in sessions if r.get("role") != "coordinator"]
    home = integration(db, project)
    text = guide(coord, kits, str(home or project), str(original_file), rules, bool(session_id))
    path = folder / f"{stamp}.md"
    path.write_text(text, encoding="utf-8")
    return [f"已迁到 Claude Code（迁移 #{batch}）：{len(sessions)} 个登记改为 Claude，旧的 Codex 会话从现在起不能再执行 module-crew 写命令",
            (f"本会话已绑为模块协调 {coord}" if session_id else
             f"模块协调 {coord} 还没绑会话：在 Claude 新会话里运行 module-crew bind {coord} --takeover --original-file {original_file}"),
            *rules, f"迁移说明已存到 {path}，全文如下；请照着一步步做：", "", text]


def _marker(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "没有这个文件"
    line = next((l.strip() for l in text.splitlines() if l.strip().startswith("<!-- spec-guard: review")), None)
    return line or "没有批准标记"


def _todo(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "没有 todo"
    done = sum(1 for l in text.splitlines() if l.lstrip().startswith("- [x]"))
    total = done + sum(1 for l in text.splitlines() if l.lstrip().startswith("- [ ]"))
    return f"todo 勾了 {done}／{total}"


def show_one(name: str, rec: dict) -> list[str]:
    """Decision 6: the snapshot taken at the move against the worktree now, and what was approved."""
    mark = rec.get("rehost") or {}
    snap = mark.get("snapshot") or {}
    wt = rec.get("worktree")
    now = snapshot(wt)
    who = f"模块 {rec.get('module')}" if rec.get("role") == "dev" else f"轻任务 T{rec.get('task')}"
    lines = [f"{name}（{who}，迁移 #{mark.get('batch')}，盘点：{'待盘点' if mark.get('inventory') == 'pending' else '已解除'}）",
             f"  worktree：{wt}"]
    then, head = snap.get("head"), now.get("head")
    ahead = None
    if then and head and then != head:
        try:
            out = _git(wt, "rev-list", "--count", f"{then}..{head}")
            ahead = int(out.stdout.strip()) if out.returncode == 0 else None
        except (OSError, ValueError, subprocess.TimeoutExpired):
            ahead = None
    old, new = set(snap.get("dirty") or []), set(now.get("dirty") or [])
    same = then == head and old == new
    lines.append(f"  HEAD：迁移时 {(then or '读不到')[:12]}，现在 {(head or '读不到')[:12]}"
                 + ("" if then == head else f"（快照之后多了 {ahead} 个提交）" if ahead is not None else "（不是快照的后续）"))
    lines.append(f"  未提交改动：迁移时 {len(old)} 个，现在 {len(new)} 个")
    lines += [f"    新出现：{l}" for l in sorted(new - old)[:DIRTY_SHOWN]]
    lines += [f"    已不在：{l}" for l in sorted(old - new)[:DIRTY_SHOWN]]
    lines += [f"    {l}" for l in sorted(old & new)[:DIRTY_SHOWN]]
    lines.append("  与迁移时的快照一致" if same else
                 "  ⚠️ 与迁移时的快照对不上：Codex 里的旧会话可能没停。停下，发【等待其他会话】给模块协调，请用户去 Codex 停掉它，再定这些改动留不留")
    if rec.get("role") == "dev" and wt:
        m = rec.get("module")
        lines.append(f"  已批：spec/{m}.md {_marker(Path(wt) / 'spec' / f'{m}.md')}；"
                     f"tasks/{m}/plan.md {_marker(Path(wt) / 'tasks' / m / 'plan.md')}；{_todo(Path(wt) / 'tasks' / m / 'todo.md')}")
    elif rec.get("task") is not None:
        lines.append(f"  任务单：module-crew task show T{rec.get('task')}（盘点对照它的完成标准）")
    return lines


def show(db: store.Store, name: str | None = None) -> tuple[int, list[str]]:
    """`rehost show [<name>]`: read only. Without a name, every session still waiting for its inventory."""
    sessions = store.records(db, "session")
    if name is not None:
        rec = sessions.get(name)
        if rec is None or rec.get("status") != "active" or not (rec.get("rehost") or {}).get("snapshot"):
            return 3, [f"{name} 不是迁来的在用会话"]
        return 0, show_one(name, rec)
    rows = [(n, r) for n, r in sorted(sessions.items()) if r.get("status") == "active"
            and (r.get("rehost") or {}).get("inventory") == "pending"]
    if not rows:
        return 0, ["没有待盘点的迁来会话"]
    return 0, [l for n, r in rows for l in show_one(n, r)]


def release(db: store.Store, name: str, original: str) -> tuple[int, list[str]]:
    """Decision 6: the user nodded at the inventory; the coordinator lifts the gate for `name`."""
    if not original or not original.strip():
        return 3, ["没有执行，原因：", "用户原话不能为空：解除盘点闸要用户看过盘点后的答复"]
    with db.transaction(actor="coordinator") as tx:
        rec = tx.get("session", name)
        mark = (rec or {}).get("rehost") or {}
        if rec is None or rec.get("status") != "active" or mark.get("inventory") != "pending":
            return 3, ["没有执行，原因：", f"{name} 没有待盘点的迁移"]
        tx.put("session", name, {**rec, "rehost": {**mark, "inventory": "released", "releasedAt": store.now(), "releaseOriginal": original}},
               action="rehost-released", data={"original": original, "batch": mark.get("batch")})
    return 0, [f"已解除 {name} 的盘点闸：它可以按用户的答复接着做，最终验收照常收"]


def undo(project: str | os.PathLike, original: str) -> tuple[int, list[str]]:
    """Decision 7 (Q1 A): put the latest move back exactly, only while none of its sessions has bound in Claude."""
    if not original or not original.strip():
        return 3, ["没有执行，原因：", "用户原话不能为空：撤回迁移要用户明说"]
    db = store.open_store(Path(project))
    sessions = store.records(db, "session")
    batches = [r["rehost"]["batch"] for r in sessions.values() if r.get("status") == "active"
               and isinstance((r.get("rehost") or {}).get("before"), dict)]
    if not batches:
        return 3, ["没有执行，原因：", "没有可撤回的迁移"]
    batch = max(batches)
    moved = {n: r for n, r in sessions.items() if (r.get("rehost") or {}).get("batch") == batch and r.get("status") == "active"}
    bound = sorted(n for n, r in moved.items() if r.get("role") != "coordinator" and (r.get("hostSession") or {}).get("sessionId"))
    if bound:
        return 3, ["没有执行，原因：", f"迁来的会话已经 bind：{'、'.join(bound)}——它们可能已经动了 worktree，迁移 #{batch} 不能再撤回"]
    with db.transaction(actor="rehost") as tx:
        for name, rec in sorted(moved.items()):
            tx.put("session", name, rec["rehost"]["before"], action="rehost-undone", data={"original": original, "batch": batch})
    return 0, [f"已撤回迁移 #{batch}：{len(moved)} 个登记恢复为迁移前（Codex）；写上的 Claude 权限规则保留（只追加），恢复说明留着不用",
               "请用户回到 Codex 里重新打开原来的会话接着做"]
