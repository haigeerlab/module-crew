"""Expansion point: propose which modules to open, then prepare worktrees, registrations and kickoffs
(see spec/crew-start.md). Opening the sessions themselves is done by the coordinator with the desktop tools.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from module_crew import probe, role, store

DEFAULT_MAX = 2   # crew-coordinator-switch: the plugin is new, two modules at a time is the safer default


@dataclass
class Proposal:
    slots: int
    modules: list[dict] = field(default_factory=list)      # {"id", "responsibility", "dependsOn"}
    conflicts: list[dict] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    reasons: list[dict] = field(default_factory=list)      # {"module", "reason"} when nothing can be started
    cadence: str = "separate"                                 # effective reviewCadence (from /map when it has one)
    reopen: dict = field(default_factory=dict)              # module -> {"round", "branch", "review", "info"} (prepare only)


def _open_store(project: Path) -> store.Store | None:
    try:
        return store.open_store(project)
    except store.StoreNotFound:
        return None


def _config(db: store.Store | None) -> dict:
    return (store.get(db, "config", "main") or {}) if db else {}


def _active_devs(db: store.Store | None) -> dict[str, dict]:
    if db is None:
        return {}
    return {k: v for k, v in store.records(db, "session").items()
            if v.get("role") == "dev" and v.get("status") == "active"}


def _merged_modules(db: store.Store | None) -> set[str]:
    if db is None:
        return set()
    sessions = store.records(db, "session")
    return {v.get("module") for k, v in store.records(db, "item").items()
            if v.get("kind") == "merge-approval" and v.get("closedReason") == "merged"
            and int(k) > store.round_since(sessions, v.get("module"))}


def _counted_devs(db: store.Store | None) -> dict[str, dict]:
    """Module sessions that take a slot: suspended ones (waiting on an outside condition) and merged ones do not."""
    merged = _merged_modules(db)
    return {k: v for k, v in _active_devs(db).items() if not v.get("suspended") and v.get("module") not in merged}


def _why_not(m: dict, sessions: dict[str, dict], merged: set[str], done: set[str], slots: int,
             db: store.Store | None = None) -> str | None:
    """Why a capability-map module cannot be started now, or None when it is done."""
    mid = m.get("id")
    if m.get("status") == "done":
        return None
    own = sessions.get(mid)
    if own is not None:
        if mid in merged:
            return "已合入，等 merge cleanup 收回"
        if own.get("suspended"):
            return f"挂起中（{own['suspended'].get('reason')}）"
        return "已有模块会话"
    status = m.get("status")
    if status == "in_progress" and _reopenable(m) is None:   # crew-reopen-module decision 6
        return f"已重开（第 {_reopen_round(db, mid)} 轮待开），要用户点名：start prepare {mid}"
    if status == "in_progress":
        return f"spec-guard 的当前模块（{m.get('step') or '进行中'}），不在可开工列表"
    if status == "suspended":
        return f"在 spec-guard 里挂起（{m.get('suspendedReason') or '未记原因'}）"
    if status == "blocked":
        return f"等被挂起的 {m.get('blockedOn') or '模块'}"
    waiting = m.get("missingDeps") or [d for d in m.get("dependsOn") or [] if d not in done]
    if waiting:
        return "等 " + "、".join(waiting)
    return "没有空位" if slots == 0 else "不在 spec-guard 的可开工列表"


def _related(mapped: dict[str, dict], module: str) -> set[str]:
    """crew-declared-scope decision 8: every module upstream or downstream of `module` in the capability map."""
    up = {mid: set(m.get("dependsOn") or []) for mid, m in mapped.items()}
    down: dict[str, set[str]] = {}
    for mid, deps in up.items():
        for d in deps:
            down.setdefault(d, set()).add(mid)

    def walk(edges: dict[str, set[str]]) -> set[str]:
        seen, todo = set(), [module]
        while todo:
            for nxt in edges.get(todo.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        return seen
    return (walk(up) | walk(down)) - {module}


def _held(db: store.Store | None, mapped: dict[str, dict], modules: list[str]) -> dict[str, str]:
    """Decision 8: with the switch on, modules related to one whose session is in use and not merged this round."""
    from module_crew import declared
    if not declared.enabled(db):
        return {}
    merged = _merged_modules(db)
    busy = {v.get("module") for v in _active_devs(db).values()} - merged
    held = {}
    for mid in modules:
        hit = sorted(_related(mapped, mid) & busy)
        if hit:
            held[mid] = f"和在用的 {'、'.join(hit)} 有依赖关系，等它合入再开"
    return held


def plan(project: str | os.PathLike, max_modules: int | None = None) -> Proposal:
    """Read-only: free slots and the first startable modules in Build order."""
    project = Path(project)
    report = probe.run(project)
    cadence = review_cadence(project, report.map)
    db = _open_store(project)
    limit = _config(db).get("maxModules") or max_modules or DEFAULT_MAX
    slots = max(limit - len(_counted_devs(db)), 0)
    blockers = [f"{c.id}：{c.reason}" for c in report.checks.values() if c.state == "blocker"]
    if _config(db).get("mode") == "serial":
        from module_crew.failure import SERIAL_BLOCKER
        blockers.append(SERIAL_BLOCKER)
    if blockers:
        return Proposal(slots, blockers=blockers, cadence=cadence)
    modules = {m.get("id"): m for m in report.map.get("modules") or [] if isinstance(m, dict)}
    sessions = {v.get("module"): v for v in _active_devs(db).values()}
    held = _held(db, modules, [mid for mid in (report.startable or {}).get("modules", []) if mid not in sessions])
    picked = [{"id": mid, "responsibility": modules.get(mid, {}).get("responsibility", ""),
               "dependsOn": list(modules.get(mid, {}).get("dependsOn") or [])}
              for mid in (report.startable or {}).get("modules", []) if mid not in sessions and mid not in held][:slots]
    reasons = []
    if not picked:
        merged, done = _merged_modules(db), {k for k, m in modules.items() if m.get("status") == "done"}
        for mid, m in modules.items():
            why = held.get(mid) or _why_not(m, sessions, merged, done, slots, db)
            if why:
                reasons.append({"module": mid, "reason": why})
    else:
        reasons = [{"module": mid, "reason": why} for mid, why in held.items()]   # shown as 暂不提议
    return Proposal(slots, picked, list((report.startable or {}).get("conflicts", [])), reasons=reasons, cadence=cadence)


HOSTS = {"claude": "claude-desktop", "codex": "codex-desktop"}
def codex_lines(relay: str, store_dir: str | os.PathLike) -> list[str]:
    """What a Codex desktop module session does on top of the Claude kickoff (crew-codex-host). Codex has no hooks, so
    it gets the store's fixed entry, which always hands over to the installed module-crew (crew-command-entry)."""
    from module_crew import launcher
    BIN = launcher.entry(store_dir)
    return [
        "",
        "你开在 Codex 桌面版里，另外要做这几件事：",
        f"- 加载 module-crew 插件的 Codex 版 crew-dev skill；命令 module-crew 不在 PATH 上，一律用这个固定入口（升级后不用换）：{BIN}",
        f"- 先运行 {BIN} host-check，有不通过的项就把输出原样发给模块协调，等它回复再继续。",
        "- 第一次提交时 Codex 会要求提权写 .git（worktree 的 git 目录在仓库外），请用户在本会话批准；有「本会话一直允许」就选它。"
        "提权弹窗只有用户能点，别的会话转来的批准不算。",
        f"- 注册邮箱名时带上宿主：bridge_register agent={relay}，host:{{app:\"codex\", sessionId:<CODEX_THREAD_ID>}}，wake 用同样的 app 与 sessionId；"
        "读不到自己的消息时用原名重新注册（这是正常恢复，不是接管）。",
        f"- Codex 没有 module-crew 的钩子：压缩、中断或应用重启后，先运行 {BIN} status，以状态库为准，不按记忆重做。",
    ]


SHORT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,18}[a-z0-9]$")


@dataclass
class PrepareResult:
    code: int                                   # 0 done / 3 refused, nothing written / 4 stopped part-way
    lines: list[str] = field(default_factory=list)
    approval: int | None = None
    prepared: list[dict] = field(default_factory=list)   # {"id", "worktree", "branch", "relayName", "kickoff"}


def _git(cwd: Path, *args: str):
    return probe._git(cwd, *args)


def _toplevel(project: Path) -> Path:
    return Path(_git(project, "rev-parse", "--show-toplevel").stdout.strip())


CADENCES = ("separate", "combined")


def cadence_info(project: str | os.PathLike, map_doc: dict | None = None) -> tuple[str, str, bool]:
    """(value, source, read from /map). spec-guard 0.73.0+ puts the effective reviewCadence in /map --json; use it when
    the caller already has the map, otherwise read .agent/config.json (same source, same value); `separate` by default."""
    given = (map_doc or {}).get("reviewCadence")
    if isinstance(given, dict) and given.get("value") in CADENCES:
        return given["value"], str(given.get("source") or "default"), True
    try:
        top = _toplevel(Path(project))
        value = json.loads((top / ".agent" / "config.json").read_text(encoding="utf-8")).get("reviewCadence")
    except (OSError, ValueError, AttributeError):
        return "separate", "default", False
    if value is None:
        return "separate", "default", False
    return (value, ".agent/config.json", False) if value in CADENCES else ("separate", "default (config invalid)", False)


def review_cadence(project: str | os.PathLike, map_doc: dict | None = None) -> str:
    """The project's spec-guard reviewCadence, read only; `separate` when unset or unreadable."""
    return cadence_info(project, map_doc)[0]


def _settings(project: Path, db: store.Store | None, short: str | None, max_modules: int | None) -> tuple[dict, list[str]]:
    """Run configuration to use, plus refusal reasons about it."""
    cfg = _config(db)
    reasons = []
    if "crewDir" in cfg:  # settled by the first prepare; sources/check command alone don't settle it
        if short is not None and short != cfg.get("projectShort"):
            reasons.append(f"项目简称已定为 {cfg.get('projectShort')}，不能改成 {short}")
        if max_modules is not None and max_modules != cfg.get("maxModules"):
            reasons.append(f"上限已定为 {cfg.get('maxModules')}，不能在这里改")
        return cfg, reasons
    if short is None or not SHORT_RE.match(short):
        reasons.append("项目简称必须给出：小写字母、数字、连字符，2～20 位，不以连字符开头或结尾")
    top = _toplevel(project)
    branch = _git(project, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    return {"projectShort": short, "integrationBranch": branch, "maxModules": max_modules or DEFAULT_MAX,
            "crewDir": str(top.parent / f"{top.name}-crew")}, reasons


def _reopenable(m: dict | None) -> str | None:
    """crew-reopen-module decision 1: why a capability-map module is not a reopened one, or None when it is.
    The caller checks separately that no module session is in use for it."""
    if not m:
        return "能力图里没有这个模块"
    progress = m.get("progress") or {}
    if m.get("status") != "in_progress":
        return f"状态是 {m.get('status')}，不是 in_progress"
    if m.get("worktree"):
        return f"已被 checkout {m['worktree']} 领走"
    if not (isinstance(progress.get("done"), int) and isinstance(progress.get("total"), int)
            and progress["done"] < progress["total"]):
        return "todo 没有未勾的项"
    if not m.get("firstTickAt"):
        return "以前没勾过任何项，不是做完后重开的模块"
    return None


def _reopen_round(db: store.Store | None, module: str) -> int:
    """r<round>: every module session this module ever had, plus one; at least 2 (assumption 6)."""
    seen = sum(1 for v in (store.records(db, "session").values() if db else [])
               if v.get("role") == "dev" and v.get("module") == module)
    return max(seen + 1, 2)


def _reopen_branch(project: Path, module: str, integration: str) -> tuple[str | None, str | None]:
    """(how, refusal) for the old module branch (decision 2): created / fast-forward, or why not."""
    if _git(project, "rev-parse", "--verify", "--quiet", f"refs/heads/{module}").returncode != 0:
        return "created", None
    listing = _git(project, "worktree", "list", "--porcelain").stdout.splitlines()
    if f"branch refs/heads/{module}" in listing:
        return None, f"{module} 的旧分支正被别的 worktree 检出，先收回那个 worktree"
    if _git(project, "merge-base", "--is-ancestor", module, integration).returncode != 0:
        extra = _git(project, "rev-list", "--count", f"{integration}..{module}").stdout.strip()
        return None, (f"{module} 的旧分支有 {extra} 个提交没合进集成分支 {integration}；"
                      "交用户决定：合进集成分支、换名保留，或确认丢弃后再重开")
    return "fast-forward", None


def validate(project: Path, modules: list[str], original: str, short: str | None,
             max_modules: int | None) -> tuple[list[str], dict, Proposal]:
    reasons = []
    if not original or not original.strip():
        reasons.append("用户原话不能为空：只记用户在本会话亲手输入的话")
    db = _open_store(project)
    cfg, cfg_reasons = _settings(project, db, short, max_modules)
    reasons += cfg_reasons
    proposal = plan(project, cfg.get("maxModules"))
    reasons += proposal.blockers
    if proposal.blockers:
        return reasons, cfg, proposal
    report = probe.run(project)
    startable = (report.startable or {}).get("modules", [])
    active = {v.get("module"): k for k, v in _active_devs(db).items()}
    merged = _merged_modules(db)
    mapped = {m.get("id"): m for m in report.map.get("modules") or [] if isinstance(m, dict)}
    if len(set(modules)) != len(modules) or not modules:
        reasons.append("模块清单为空或有重复")
    if len(modules) > proposal.slots:
        reasons.append(f"空位只有 {proposal.slots} 个，要开 {len(modules)} 个")
    for m in modules:
        if m in active:
            reasons.append(f"旧会话 {active[m]} 还在用，先 merge cleanup {m}" if m in merged
                           else f"{m} 已有在用的模块会话")
        elif m not in startable:
            why = _reopenable(mapped.get(m))
            if why:
                reasons.append(f"{m} 不在可开工列表（startable.modules）里，也不能按重开处理：{why}")
            else:
                info = {"id": m, "responsibility": mapped[m].get("responsibility", ""),
                        "dependsOn": list(mapped[m].get("dependsOn") or [])}
                proposal.reopen[m] = {"round": _reopen_round(db, m), "info": info,
                                      "review": {k: str((mapped[m].get("review") or {}).get(k)) for k in ("spec", "plan")}}
    held = _held(db, mapped, [m for m in modules if m in mapped])
    reasons += [f"{m} {why}" for m, why in held.items()]
    from module_crew import declared
    if declared.enabled(db):
        for i, a in enumerate(modules):
            for b in modules[i + 1:]:
                if a in mapped and b in _related(mapped, a):
                    reasons.append(f"同一次要开的 {a} 和 {b} 有依赖关系，不能同时开")
    for m in modules:
        if (Path(cfg["crewDir"]) / m).exists():
            reasons.append(f"{m} 的 worktree 目录已存在：{Path(cfg['crewDir']) / m}")
        if m in proposal.reopen:
            how, refused = _reopen_branch(project, m, cfg["integrationBranch"])
            if refused:
                reasons.append(refused)
            proposal.reopen[m]["branch"] = how
        elif _git(project, "rev-parse", "--verify", "--quiet", f"refs/heads/{m}").returncode == 0:
            reasons.append(f"{m} 的分支已存在")
    return reasons, cfg, proposal


def launcher_line(db: store.Store) -> str:
    """crew-command-entry decisions 3 and 6: (re)write the fixed entry Claude and Codex sessions use, and say so."""
    from module_crew import launcher
    path, changed = launcher.install(db.path)
    return f"module-crew 固定入口：{path}（{'已写入' if changed else '没有变化'}）"


def prepare(project: str | os.PathLike, modules: list[str], original: str, short: str | None = None,
            max_modules: int | None = None, host: str | None = None, commit_prefix: str | None = None) -> PrepareResult:
    project = Path(project)
    from module_crew import handover
    refused, host = handover.pick_host(_open_store(project), host)   # crew-host-handover: follow the coordinator
    if refused:
        return PrepareResult(2, ["没有执行，原因：", refused])
    if host not in HOSTS:
        return PrepareResult(3, ["没有执行，原因：", f"宿主只能是 {'／'.join(HOSTS)}，不是 {host!r}"])
    host_id = HOSTS[host]
    reasons, cfg, proposal = validate(project, modules, original, short, max_modules)
    if reasons:
        return PrepareResult(3, ["没有执行，原因："] + reasons)
    info = {m["id"]: m for m in plan(project, len(modules) + len(_counted_devs(_open_store(project)))).modules}
    info.update({m: r["info"] for m, r in proposal.reopen.items()})
    db = _open_store(project) or store.init_store(project)[0]
    short = cfg["projectShort"]
    coord = f"{short}-coord"
    with db.transaction(actor=coord) as tx:
        if "crewDir" not in (tx.get("config", "main") or {}):
            from module_crew.hostcheck import plugin_version
            tx.put("config", "main", {**(tx.get("config", "main") or {}), **cfg, "pluginVersion": plugin_version(),
                                      "reviewCadence": proposal.cadence},
                   action="set")
        if commit_prefix is not None:       # 0.9.4: project configuration, '' means no prefix
            tx.put("config", "main", {**(tx.get("config", "main") or {}), "commitPrefix": commit_prefix}, action="set",
                   data={"commitPrefix": commit_prefix})
        if not any(v.get("role") == "coordinator" and v.get("status") == "active" for v in tx.records("session").values()):
            from module_crew.hooks import identity, own_session_id
            sid = own_session_id()          # crew-routing-fixes: the coordinator running start binds itself
            ident = {"hostSession": identity(sid)} if sid else {}
            tx.put("session", coord, {"role": "coordinator", "host": "claude-desktop", "status": "active", **ident},
                   action="registered")
        approval = tx.allocate_number()
        tx.put("item", str(approval), {
            "state": "closed", "kind": "start", "from": coord, "relayId": None, "modules": list(modules),
            "closedReason": "answered", "answer": {"original": original, "answeredAt": store.now(), **store.source_field()},
            **({"host": host_id} if host_id != "claude-desktop" else {}),
            **({"reopened": [m for m in modules if m in proposal.reopen]} if proposal.reopen else {}),
        }, action="start-approved")
    from module_crew import unqueued
    unqueued.mark_integration(db, project, "start-prepare", only_if_unset=True)
    result = PrepareResult(0, approval=approval)
    result.lines.append(f"开工批准事项 C{approval}：{'、'.join(modules)}")
    result.lines.append(launcher_line(db))
    for m in modules:
        path = Path(cfg["crewDir"]) / m
        if path.exists():  # checked again: git would create the branch before refusing a busy directory
            result.code = 4
            result.lines.append(f"{m}：worktree 目录在校验之后被占用（{path}），已停下")
            break
        reopen = proposal.reopen.get(m)
        if reopen and reopen["branch"] == "fast-forward":
            # the old branch is an ancestor of the integration branch: moving it there loses no commit
            added = _git(project, "branch", "-f", m, cfg["integrationBranch"])
            if added.returncode == 0:
                added = _git(project, "worktree", "add", str(path), m)
        else:
            added = _git(project, "worktree", "add", "-b", m, str(path), cfg["integrationBranch"])
        if added.returncode != 0:
            result.code = 4
            left = _git(project, "rev-parse", "--verify", "--quiet", f"refs/heads/{m}").returncode == 0
            result.lines.append(f"{m}：建 worktree 失败，已停下（{added.stderr.strip()[:200]}）"
                                + ("；git 已留下分支 " + m + "，请决定是否删除" if left else ""))
            break
        relay = f"{short}-{m}" + (f"-r{reopen['round']}" if reopen else "")
        text = render_kickoff(m, info.get(m, {}), path, {**cfg, "reviewCadence": proposal.cadence}, relay, coord,
                              approval, host_id, reopen=reopen)
        extra = {"reopen": {"round": reopen["round"], "since": approval, "review": reopen["review"]}} if reopen else {}
        with db.transaction(actor=coord) as tx:
            tx.put("session", relay, {"role": "dev", "host": host_id, "status": "active",
                                      "module": m, "worktree": str(path), **extra}, action="registered")
            body = tx.allocate_number()
            tx.write_body(body, text)
        result.prepared.append({"id": m, "worktree": path, "branch": m, "relayName": relay, "kickoff": body, "host": host_id,
                                "kickoffPath": db.path / "bodies" / f"{body}.txt",
                                **({"reopen": {"round": reopen["round"], "branch": reopen["branch"]}} if reopen else {})})
        if reopen:
            head = _git(project, "rev-parse", "--short", m).stdout.strip()
            result.lines.append(f"{m}：按重开处理（第 {reopen['round']} 轮）；"
                                + (f"旧分支已快进到 {head}" if reopen["branch"] == "fast-forward" else "没有旧分支，从集成分支新切"))
        from module_crew import permissions
        line = permissions.follow(project, relay)       # crew-host-permissions: same rules for a new worktree
        if line:
            result.lines.append(line)
    done = [p["id"] for p in result.prepared]
    if result.code == 4:
        result.lines.append(f"已完成：{'、'.join(done) or '无'}；未完成的模块请处理原因后单独重跑")
    roles = _role_commands(project)
    for p in result.prepared:
        p["role"] = _set_role(roles, "setModule", p["worktree"], p["id"])
    checkout = probe._checkout_of(project, cfg["integrationBranch"])
    if checkout is None:
        result.lines.append("集成 checkout 角色标记未设：找不到集成分支所在的 checkout")
    else:
        kind, module = role.read(Path(checkout))
        if kind == "none":
            result.lines.append("集成 checkout " + _set_role(roles, "setCoordinator", Path(checkout), None))
        elif kind == "coordinator":
            result.lines.append("集成 checkout 角色标记：已是 coordinator")
        else:
            result.lines.append(f"集成 checkout 角色标记已是 {('module ' + module) if module else kind}，没有覆盖，请用户决定")
    if result.prepared:
        result.lines.append(f"开会话之前：模块协调先用 agent-relay bridge_register 注册邮箱名 {coord}（wake: \"auto\"），模块只和这个名字说话")
        if not (store.get(db, "session", coord) or {}).get("hostSession"):
            result.lines.append(f"模块协调还没登记身份：请用户在本会话同意后运行 module-crew bind {coord} --original-file <原话文件>，钩子才认本会话")
    return result


def _role_commands(project: Path) -> tuple[Path, dict] | str:
    found = probe.find_plugin("spec-guard", project)
    if isinstance(found, str):
        return found
    doc = probe.read_interface(found.root, probe.SPEC_GUARD_MAJOR)
    if isinstance(doc, str):
        return doc
    commands = (doc.get("checkoutRole") or {}).get("commands")
    if not isinstance(commands, dict):
        return "spec-guard 的 interface.json 没有 checkoutRole 入口（需要 interface 1.1）"
    return found.root, commands


def _set_role(roles: tuple[Path, dict] | str, key: str, checkout: Path, module: str | None) -> str:
    """Write one checkout role marker; failures are reported, never fatal."""
    want = f"module {module}" if module else "coordinator"
    if isinstance(roles, str):
        return f"角色标记未设：{roles}"
    root, commands = roles
    cmd = probe.safe_command(root, {key: {"command": commands.get(key)}}, key,
                             {"<module-id>": module or "", "<checkout-root>": str(checkout)})
    if isinstance(cmd, str):
        return f"角色标记未设：{cmd}"
    cmd = cmd + ["--confirm"]
    manual = " ".join(cmd)
    try:
        ran = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=probe.MAP_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"角色标记未设：{exc}；可在 spec-guard 目录手动执行：{manual}"
    if ran.returncode != 0 or role.read(checkout) != (("module", module) if module else ("coordinator", None)):
        why = (ran.stderr or ran.stdout).strip()[:200] or f"退出码 {ran.returncode}"
        return f"角色标记未设：{why}；可在 spec-guard 目录手动执行：{manual}"
    return f"角色标记：{want}"


# S22 (LIVE-SAAS): a worktree starts without node_modules/.venv, so the project's commit hooks (lefthook, husky)
# could not run until review approve committed to the integration branch. Each command matches
# permissions.LOCKFILE_CLAUDE and LOCKFILE_CODEX, so it runs without a prompt on either host.
JS_LOCKFILES = (("pnpm-lock.yaml", "pnpm install --frozen-lockfile"), ("package-lock.json", "npm ci"),
                ("yarn.lock", "yarn install"))


def install_commands(root: str | os.PathLike) -> list[str]:
    """The dependency installs for the lockfiles at the project root: one JS, then uv.lock or requirements*.txt
    (creating .venv first when the worktree has none)."""
    root = Path(root)
    cmds = [next((cmd for name, cmd in JS_LOCKFILES if (root / name).is_file()), None)]
    if (root / "uv.lock").is_file():
        cmds.append("uv sync")
    else:
        reqs = [f".venv/bin/pip install -r {p.name}" for p in sorted(root.glob("requirements*.txt")) if p.is_file()]
        if reqs and not (root / ".venv").exists():
            cmds.append("python3 -m venv .venv")   # T135: a new worktree has no .venv for pip to run from
        cmds += reqs
    return [c for c in cmds if c]


def install_line(root: str | os.PathLike) -> list[str]:
    """The kickoff's first step, empty when the project has no lockfile."""
    cmds = install_commands(root)
    return [f"第一步：先在本 worktree 装依赖，再写 Spec／动手：{'；'.join(cmds)}（提交钩子要靠它们才能跑）"] if cmds else []


def _first_step(module: str, cadence: str) -> str:
    """R13: what the module does before its first approval, by the project's review cadence.

    The paths are spec-guard's layout convention (see review.REQUIRED_FILES; boundary review 7)."""
    if cadence == "combined":
        return (f"这一步只做：用 /spec 写 spec/{module}.md 与 tasks/{module}/plan.md、todo.md，写好后给模块协调发【交审】"
                "（节点 Spec、Plan 各一条，或接口提案）。项目评审节奏：combined；遇到新决策、范围不清或高风险不可逆改动时仍先只交 Spec。")
    return (f"这一步只做：用 /spec 只写 spec/{module}.md，写好后给模块协调发【交审】（节点 Spec，或接口提案）；"
            f"Spec 批准的【用户答复】到了再写 tasks/{module}/plan.md、todo.md 交审（节点 Plan）。项目评审节奏：separate。")


def _reopen_lines(module: str, reopen: dict, integration: str, cadence: str) -> list[str]:
    """crew-reopen-module decision 5: the revision paragraph and the first step, chosen by the review state at reopen."""
    branch = (f"旧的模块分支已快进到集成分支 {integration}" if reopen["branch"] == "fast-forward"
              else f"旧的模块分支不在了，已从集成分支 {integration} 新切")
    lines = [f"这是重开修订（第 {reopen['round']} 轮）：模块 {module} 已经做完过，spec-guard 已把它原地重开。"
             f"只做 tasks/{module}/todo.md 里新加的未勾项，已勾的不要重做；",
             f"plan.md 里新补的一节说明这次为什么返工。{branch}，旧一轮的邮箱名已退役，不要用。"]
    spec, plan = reopen["review"]["spec"], reopen["review"]["plan"]
    if spec == "approved" and plan == "approved":   # in-scope rework: naming the module to reopen is the go-ahead (Q2)
        return lines + [f"Spec 与 Plan 仍是批准状态（范围内返工）。先 module-crew sync，再从 tasks/{module}/todo.md 第一个未勾项开始构建，"
                        "不用等开工通知；做完发最终验收【交审】。"]
    if spec == "approved":
        lines.append(f"这一步只做：把 tasks/{module}/plan.md、todo.md 发【交审】（节点 Plan）；Plan 批准后收到开工类【协调通知】再构建。")
    else:
        lines.append(_first_step(module, cadence))
    return lines + ["收到开工类【协调通知】之前不要开始构建。"]


def codex_open_lines(items: list[tuple[str, str, str]]) -> list[str]:
    """crew-codex-coordinator decision 7: with the coordinator on Codex every session is opened by hand in Codex.

    items: (label, worktree, kickoff file)."""
    lines = ["请用户去 Codex 新建任务（模块协调在 Codex，模块会话与轻任务会话也都开在 Codex；Codex 叫不醒停掉的 Claude 会话）："]
    lines += [f"  {label}：工作目录选 {worktree}，第一条消息贴 {kickoff} 全文" for label, worktree, kickoff in items]
    return lines


def _constraint_line(cfg: dict) -> str:
    """crew-declared-scope decision 6: with the switch on, declared public files are edited in the module branch."""
    if cfg.get("declaredScope") == "on":
        return ("全局约束：Plan「预先声明」名单内的公共文件直接在本分支改（`module-crew scope <文件>` 可查）；名单外的不改，"
                "要改发【公共变更请求】；被挡住发【等待其他会话】；发出前 module-crew protocol check。")
    return "全局约束：不改公共文件（要改发【公共变更请求】）；被挡住发【等待其他会话】；发出前 module-crew protocol check。"


def render_kickoff(module: str, info: dict, worktree: Path, cfg: dict, relay: str, coord: str, approval: int,
                   host: str = "claude-desktop", reopen: dict | None = None) -> str:
    deps = "\n".join(f"spec/{d}.md" for d in info.get("dependsOn") or []) or "无"
    from module_crew.hooks import ENTRY_LINE
    extra = codex_lines(relay, store.open_store(worktree).path) if host == "codex-desktop" else []
    return "\n".join([
        f"你是 module-crew 的模块会话，负责模块 {module}：{info.get('responsibility', '')}。",
        "先加载 crew-dev skill，照它的规则做；规则不要抄进这个 worktree 的 CLAUDE.md。",
        "",
        f"工作目录：{worktree}（分支 {module}，从集成分支 {cfg['integrationBranch']} 切出）",
        f"邮箱名：{relay}，用 agent-relay bridge_register 注册，wake: \"auto\"",
        f"注册后先运行 module-crew bind {relay}：登记本会话的身份，module-crew 的钩子只认登记过的会话",
        f"模块协调：{coord}（你只和它说话）",
        *([] if host == "codex-desktop" else [ENTRY_LINE]),   # Codex has no hooks: codex_lines gives the path
        f"开会话依据：用户批准事项 C{approval}",
        "",
        *install_line(worktree),
        *(_reopen_lines(module, reopen, cfg["integrationBranch"], cfg.get("reviewCadence", "separate")) if reopen else
          [_first_step(module, cfg.get("reviewCadence", "separate")), "收到开工类【协调通知】之前不要开始构建。"]),
        "",
        f"接口：\n{deps}",
        _constraint_line(cfg),
    ] + extra) + "\n"
