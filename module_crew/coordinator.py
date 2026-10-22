"""Upgrade a conversation to the project's coordinator, or switch it off (see spec/crew-coordinator-switch.md).

Both need the user's own words. One git repository has at most one active coordinator registration;
`up` never takes over another conversation's registration (that is `takeover` + `bind`).
"""

from __future__ import annotations

import os
from pathlib import Path

from module_crew import probe, start, store
from module_crew.hooks import _home_of, own_session_id

UP_CHECKS = ("git", "agent-relay", "spec-guard", "spec-guard-enabled", "baseline")


def _blockers(report: probe.Report) -> list[str]:
    """The prerequisites for `up`: no capability map yet is fine, the planning layer is not looked at."""
    out = []
    for cid in UP_CHECKS:
        c = report.checks[cid]
        if c.state == "blocker" and not (cid == "spec-guard" and c.code == "no-capability-map"):
            out.append(f"{cid}：{c.reason}" + (f"（怎么办：{c.fix}）" if c.fix else ""))
    return out


def active(db: store.Store | None) -> tuple[str, dict] | None:
    if db is None:
        return None
    return next(((n, s) for n, s in sorted(store.records(db, "session").items())
                 if s.get("role") == "coordinator" and s.get("status") == "active"), None)


def where(db: store.Store, rec: dict) -> str:
    """'在 <dir>，分支 <branch>' for a coordinator registration."""
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch") or "?"
    home = _home_of(db, rec)
    return f"在 {home or '（集成分支没有被检出）'}，分支 {branch}"


def up(project: str | os.PathLike, short: str | None, original: str,
       session_id: str | None = None) -> tuple[int, list[str]]:
    """Make the conversation running this the coordinator. Raises NotInRepo outside a git repository."""
    project = Path(project)
    if not original or not original.strip():
        return 3, ["没有升级，原因：", "用户原话不能为空：升级模块协调要用户在本会话明说"]
    sid = session_id or own_session_id()
    if not sid:
        return 3, ["没有升级，原因：", "读不到本会话的会话 id（CLAUDE_CODE_SESSION_ID）：只能在要升级的那个会话里运行"]
    report = probe.run(project)
    db = start._open_store(project)
    existing = active(db)
    if existing:
        name, rec = existing
        bound = (rec.get("hostSession") or {}).get("sessionId")
        if bound == sid:
            return 0, [f"本会话已是模块协调 {name}，没有改动"]
        state = "已绑定另一个会话" if bound else "还没绑定会话"
        return 3, ["没有升级，原因：", f"本项目已有模块协调 {name}（{where(db, rec)}，{state}）；一个仓库只能有一个",
                   f"要换成本会话：请用户明说接管后运行 module-crew takeover {name} --original-file <原话文件>，"
                   f"再在本会话运行 module-crew bind {name} --original-file <原话文件>"]
    reasons = _blockers(report)
    cfg, cfg_reasons = start._settings(project, db, short, None)
    reasons += cfg_reasons
    if reasons:
        return 3, ["没有升级，原因："] + reasons
    db = db or store.init_store(project)[0]
    coord = f"{cfg['projectShort']}-coord"
    with db.transaction(actor=coord) as tx:
        if "crewDir" not in (tx.get("config", "main") or {}):
            from module_crew.hostcheck import plugin_version
            tx.put("config", "main", {**(tx.get("config", "main") or {}), **cfg, "pluginVersion": plugin_version(),
                                      "reviewCadence": start.review_cadence(project)}, action="set")
        tx.put("session", coord, {"role": "coordinator", "host": "claude-desktop", "status": "active",
                                  "hostSession": {"sessionId": sid, "boundAt": store.now()}},
               action="coordinator-up", data={"original": original, "sessionId": sid})
    return 0, [f"已升级：本会话是本项目的模块协调 {coord}（{where(db, store.get(db, 'session', coord))}）",
               f"多模块并行上限 {(store.get(db, 'config', 'main') or {}).get('maxModules')}",
               f"下一步：用 agent-relay bridge_register 注册邮箱名 {coord}（wake: \"auto\"），再跑 module-crew status"]


def down(project: str | os.PathLike, original: str, session_id: str | None = None) -> tuple[int, list[str]]:
    """Switch the coordinator off; only when no module session is in use. History stays."""
    if not original or not original.strip():
        return 3, ["没有关闭，原因：", "用户原话不能为空：关闭模块协调要用户在本会话明说"]
    db = start._open_store(Path(project))
    existing = active(db)
    if not existing:
        return 0, ["本项目没有在用的模块协调，没有改动"]
    name, rec = existing
    sid = session_id or own_session_id()
    bound = (rec.get("hostSession") or {}).get("sessionId")
    if bound and bound != sid:
        return 3, ["没有关闭，原因：", f"模块协调 {name} 绑定的是另一个会话：只能在它自己的会话里关闭"]
    devs = sorted(f"{s.get('module')}（{n}）" for n, s in store.records(db, "session").items()
                  if s.get("role") == "dev" and s.get("status") == "active")
    if devs:
        return 3, ["没有关闭，原因：", "还有在用的模块会话：" + "、".join(devs) + "；先合并或收回它们"]
    with db.transaction(actor=name) as tx:
        cur = tx.get("session", name)
        tx.put("session", name, {**{k: v for k, v in cur.items() if k != "hostSession"}, "status": "retired"},
               action="coordinator-down", data={"original": original})
    return 0, [f"已关闭模块协调 {name}：module-crew 对本项目的会话不再注入任何规矩；状态库与历史保留，之后可以再 coordinator up"]
