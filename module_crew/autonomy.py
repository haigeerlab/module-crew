"""spec-guard autonomyTier: what module-crew loosens at each tier, the evidence for a step up and the automatic step
down after an incident (see spec/crew-autonomy-tier.md)."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from module_crew import probe, store

FIELD = "autonomy"                    # config/main.autonomy: cap, capFor, incident, seen, suggestedFor, toldSeq
TIERS = ("strict", "standard", "relaxed")
READ_FROM = ("python3", "-B", "hooks/project_config.py", "show", "--project", "<project-root>", "--format", "json")
MIN_VERSION = (0, 85, 0)
STREAK = 3                            # assumption 6: merged modules in a row that meet the bar
MAX_REWORK = 1
INCIDENTS = ("merge-returned", "revoked", "rework-over-limit", "baseline-red")
_MARKS = ("config.tier-seen", "config.tier-lowered", "config.tier-restored", "config.tier-cap-cleared")


@dataclass
class Tier:
    value: str = "strict"
    source: str = "default"
    usable: bool = False
    reason: str | None = None

    @property
    def explicit(self) -> bool:
        """Assumption 1: the tier is the switch; only a value written in .agent/config.json turns it on."""
        return self.usable and not self.source.startswith("default")


@dataclass
class Effective:
    configured: Tier
    cap: str | None = None
    value: str = "strict"
    record: dict = field(default_factory=dict)

    @property
    def explicit(self) -> bool:
        return self.configured.explicit

    @property
    def active(self) -> bool:
        """Anything of this module shows at all: the tier was set, or an earlier step down still holds."""
        return self.explicit or self.cap is not None


def rank(tier: str) -> int:
    return TIERS.index(tier) if tier in TIERS else 0


def _lower(tier: str) -> str:
    return TIERS[max(rank(tier) - 1, 0)]


def _higher(tier: str) -> str:
    return TIERS[min(rank(tier) + 1, len(TIERS) - 1)]


def integration_checkout(db: store.Store, project: str | os.PathLike) -> Path:
    """Assumption 3: the tier is read where the integration branch is checked out."""
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch")
    found = probe._checkout_of(Path(project), branch) if branch else None
    return found or Path(project)


def _interface(project: Path):
    found = probe.find_plugin("spec-guard", project)
    if isinstance(found, str):
        return f"找不到 spec-guard（{found}）"
    doc = probe.read_interface(found.root, probe.SPEC_GUARD_MAJOR)
    if isinstance(doc, str):
        return doc
    if not isinstance(doc.get("autonomyTier"), dict):
        return f"装的 spec-guard 接口 {doc.get('interface')} 低于 1.11（没有 autonomyTier）"
    return found, doc


def _command(root: Path, doc: dict, checkout: Path) -> list[str] | str:
    """Assumption 2: readFrom is prose; only its one known shape is run, as a fixed argv."""
    text = doc["autonomyTier"].get("readFrom")
    if not isinstance(text, str) or not text.startswith(" ".join(READ_FROM)):
        return "interface.json 的 autonomyTier.readFrom 写法和预期不同，没有运行"
    base = root.resolve()
    if not (base / READ_FROM[2]).resolve().is_relative_to(base):
        return f"{READ_FROM[2]} 不在 spec-guard 安装目录内，不安全，没有运行"
    return [str(checkout) if x == "<project-root>" else x for x in READ_FROM]


_CACHE: dict = {}


def _stamp(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def read(checkout: str | os.PathLike) -> Tier:
    """The project's autonomyTier as spec-guard reports it; strict with a reason whenever it cannot be read."""
    checkout = Path(checkout)
    got = _interface(checkout)
    if isinstance(got, str):
        return Tier(reason=got)
    found, doc = got
    stamp = (str(checkout), str(found.root), _stamp(checkout / ".agent" / "config.json"), _stamp(found.root / "interface.json"))
    if stamp in _CACHE:
        return _CACHE[stamp]
    cmd = _command(found.root, doc, checkout)
    if isinstance(cmd, str):
        return Tier(reason=cmd)
    try:
        ran = subprocess.run(cmd, cwd=found.root, capture_output=True, text=True, timeout=probe.MAP_TIMEOUT)
        items = json.loads(ran.stdout).get("items") if ran.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError, AttributeError) as exc:
        return Tier(reason=f"读档位的命令没跑成（{exc}）")
    if ran.returncode != 0:
        return Tier(reason=f"读档位的命令退出码 {ran.returncode}：{ran.stderr.strip()[:200]}")
    item = next((i for i in items or [] if isinstance(i, dict) and i.get("key") == "autonomyTier"), None)
    if item is None:
        return Tier(reason="spec-guard 的配置输出里没有 autonomyTier")
    value = item.get("value") if item.get("value") in TIERS else "strict"
    tier = Tier(value, str(item.get("source") or "default"), True)
    _CACHE[stamp] = tier
    return tier


def state(db: store.Store) -> dict:
    """module-crew's own tier bookkeeping, kept in config/main (the config kind has one key)."""
    return dict((store.get(db, "config", "main") or {}).get(FIELD) or {})


def _state(tx) -> dict:
    return dict((tx.get("config", "main") or {}).get(FIELD) or {})


def _put(tx, rec: dict, action: str, data: dict) -> None:
    tx.put("config", "main", {**(tx.get("config", "main") or {}), FIELD: rec}, action=action, data=data)


def marks(db: store.Store) -> list[dict]:
    """The events that restart the evidence: the effective tier changed, was lowered, restored or uncapped."""
    return [e for e in store.events(db, key="main", kind="config") if e["type"] in _MARKS]


def effective(db: store.Store, project: str | os.PathLike) -> Effective:
    """Decision 3: the configured tier under module-crew's step-down cap; notes when the cap no longer applies and
    when the effective tier changed (the start of the evidence). Nothing is written while the tier is unset."""
    tier = read(integration_checkout(db, project))
    rec = state(db)
    cap = rec.get("cap")
    try:
        if cap and tier.value != rec.get("capFor"):
            with db.transaction(actor="autonomy") as tx:
                rec = _state(tx)
                old = rec.pop("cap", None)
                rec.pop("capFor", None)
                _put(tx, rec, "tier-cap-cleared", {"cap": old, "configured": tier.value})
            cap = None
        value = TIERS[min(rank(tier.value), rank(cap))] if cap else tier.value
        if (tier.explicit or cap) and rec.get("seen") != value:
            with db.transaction(actor="autonomy") as tx:
                rec = dict(_state(tx), seen=value, seenAt=store.now())
                _put(tx, rec, "tier-seen", {"seen": value})
    except store.StoreBusy:
        value = TIERS[min(rank(tier.value), rank(cap))] if cap else tier.value
    return Effective(tier, cap, value, rec)


def project_of(db: store.Store) -> Path:
    """The repository a store belongs to (the store lives in its common git dir)."""
    return db.path.parent.parent


def describe(eff: Effective) -> str:
    t = eff.configured
    if not t.usable:
        return f"读不到档位：{t.reason}，按 strict"
    if not eff.active:
        return "档位没设（spec-guard 默认 strict），module-crew 照今天做"
    line = f"自治档位：设的 {t.value}（{t.source}），生效 {eff.value}"
    inc = eff.record.get("incident") or {}
    if eff.cap:
        line += f"（{(inc.get('at') or '')[:10]} 因 {inc.get('reason') or '出事'} 降档，恢复要用户原话：module-crew tier restore）"
    return line


def report(db: store.Store, project: str | os.PathLike) -> tuple[dict, list[str]]:
    """`tier`: the configured tier, the cap, the effective tier, the evidence and the advice (read only)."""
    eff = effective(db, project)
    t = eff.configured
    doc = {"configured": {"value": t.value, "source": t.source, "usable": t.usable, "reason": t.reason},
           "explicit": eff.explicit, "cap": eff.cap, "effective": eff.value, "cadence": None, "cadenceHint": None,
           "evidence": [], "suggest": None}
    lines = [describe(eff)]
    if eff.active:
        from module_crew import start
        doc["cadence"] = start.review_cadence(project)
        doc["cadenceHint"] = cadence_hint(eff, doc["cadence"])
        lines += [doc["cadenceHint"]] if doc["cadenceHint"] else []
        doc["evidence"] = evidence(db)
        doc["suggest"] = suggestion(db, eff, doc["evidence"])
        advice = suggestion_line(db, project) if doc["suggest"] else None
        lines += [advice] if advice else []
    return doc, lines


def cadence_hint(eff: Effective, cadence: str) -> str | None:
    """Decision 4: spec-guard does not link reviewCadence to the tier; module-crew only points it out."""
    if rank(eff.value) >= rank("standard") and cadence != "combined":
        return (f"档位 {eff.value} 要 Spec 与 Plan 一起审，但 reviewCadence 是 {cadence}："
                "请用户确认后用 /spec-guard:config 设成 combined（在那之前照 separate 交审）")
    return None


def _version(text: str | None) -> tuple[int, ...] | None:
    try:
        return tuple(int(x) for x in (text or "").split("."))
    except ValueError:
        return None


def preflight(db: store.Store, project: str | os.PathLike) -> tuple[int, list[str]]:
    """Decision 2: before /spec-guard:config writes autonomyTier — 0.67.1 and older would call the whole file invalid."""
    checkout = integration_checkout(db, project)
    reasons = []
    found = probe.find_plugin("spec-guard", checkout)
    if isinstance(found, str):
        reasons.append(f"找不到 spec-guard（{found}）")
    else:
        got = _version(found.version)
        if got is None or got < MIN_VERSION:
            reasons.append(f"本机 spec-guard {found.version or '版本读不出'} 低于 0.85.0："
                           "0.68.0～0.84.2 会忽略这个键，0.67.1 及更早会把整份配置判无效；先升级")
        got = _interface(checkout)
        if isinstance(got, str):
            reasons.append(got)
    codex = sorted(n for n, s in store.records(db, "session").items()
                   if s.get("host") == "codex-desktop" and s.get("status") == "active")
    note = ([f"Codex 那边的 spec-guard 版本 module-crew 查不到（登记的 Codex 会话：{'、'.join(codex)}）："
             "0.67.1 及更早会把整份配置判无效，请用户确认 Codex 也装了 0.85.0 以上"] if codex else [])
    if reasons:
        return 3, ["不能写 autonomyTier：", *(f"- {r}" for r in reasons), *note]
    return 0, [f"可以写 autonomyTier：本机 spec-guard {found.version}，接口有 autonomyTier。"
               "引用用户原话后用 /spec-guard:config 写入；要设 standard 或 relaxed 时同一句原话里一并设 reviewCadence=combined，"
               "写完把 .agent/config.json 单独提交", *note]


INCIDENT_NAMES = {"merge-returned": "合并因模块的原因退回", "revoked": "用户撤销合并批准",
                  "rework-over-limit": "返工满 3 次", "baseline-red": "基线完整检查新跑出失败"}


def incident(db: store.Store, project: str | os.PathLike, kind: str, ref: str, reason: str = "") -> str | None:
    """Decision 8: one step down per incident (never below strict, never twice for the same item); the line the
    calling command prints so the coordinator tells the user at once. Errors only cost the line, never the caller."""
    try:
        eff = effective(db, project)
        if eff.value == "strict":
            return None
        key = f"{kind}:{ref}"
        new = _lower(eff.value)
        what = INCIDENT_NAMES.get(kind, kind) + (f"（{reason}）" if reason else "")
        with db.transaction(actor="autonomy") as tx:
            rec = _state(tx)
            if key in (rec.get("incidentKeys") or []):
                return None
            rec.update(cap=new, capFor=eff.configured.value, seen=new, seenAt=store.now(),
                       incident={"kind": kind, "key": key, "reason": what, "at": store.now()},
                       incidentKeys=((rec.get("incidentKeys") or []) + [key])[-50:])
            _put(tx, rec, "tier-lowered", {"from": eff.value, "to": new, "kind": kind, "key": key, "reason": what})
    except (store.StoreError, OSError) as exc:
        return f"自治档位没能降档（{exc}）：请告诉用户，由用户决定是否用 /spec-guard:config 调低档位"
    return f"自治档位已从 {eff.value} 降到 {new}：{what}。马上告诉用户；恢复要用户原话（module-crew tier restore）"


class Refused(Exception):
    pass


def restore(db: store.Store, project: str | os.PathLike, original: str | None) -> list[str]:
    """Decision 3: one step back up toward the configured tier, on the user's words."""
    if not original or not original.strip():
        raise Refused("用户原话不能为空：恢复降档要用户明确说")
    eff = effective(db, project)
    if not eff.cap:
        raise Refused("现在没有降档上限：要升到设的档位以上，先 module-crew tier --preflight，再引用用户原话用 /spec-guard:config")
    up = _higher(eff.cap)
    with db.transaction(actor="coordinator") as tx:
        rec = _state(tx)
        if rank(up) >= rank(eff.configured.value):
            rec.pop("cap", None)
            rec.pop("capFor", None)
            up = eff.configured.value
        else:
            rec["cap"] = up
        rec.update(seen=up, seenAt=store.now())
        _put(tx, rec, "tier-restored", {"from": eff.value, "to": up, "original": original, **store.source_field()})
    return [f"自治档位已从 {eff.value} 恢复到 {up}" + ("（已回到设的档位，降档上限清掉）" if up == eff.configured.value else "")]


def _start(db: store.Store) -> int:
    """Assumption 6: the evidence counts from the last change of the effective tier."""
    found = marks(db)
    return found[-1]["seq"] if found else 0


def evidence(db: store.Store) -> list[dict]:
    """Per module merged since the start, in merge order: merge returns (module's fault), revocations, rework rounds,
    the user's own returns of a submission; `ok` when it meets the bar (light tasks are not counted)."""
    since = _start(db)
    events = [e for e in store.events(db, kind="item") if e["seq"] > since]
    rec_of = lambda e: (e.get("data") or {}).get("record") or {}
    merged = [rec_of(e)["module"] for e in events if e["type"] == "item.merged"
              and rec_of(e).get("kind") == "merge-approval" and not rec_of(e).get("task") and rec_of(e).get("module")]
    rows = []
    for m in dict.fromkeys(merged):
        mine = lambda e: rec_of(e).get("module") == m
        row = {"module": m,
               "returned": sum(1 for e in events if e["type"] == "item.returned" and mine(e)
                               and rec_of(e).get("returnKind") == "module"),
               "revoked": sum(1 for e in events if e["type"] == "item.revoked" and mine(e)),
               "rework": sum(1 for e in events if e["type"] == "item.rework-sent" and (e.get("data") or {}).get("module") == m),
               "userReturned": sum(1 for e in events if e["type"] == "item.answered" and mine(e)
                                   and rec_of(e).get("kind") == "review"
                                   and not (rec_of(e).get("answer") or {}).get("approval"))}
        row["ok"] = row["returned"] == 0 and row["revoked"] == 0 and row["rework"] <= MAX_REWORK and row["userReturned"] == 0
        rows.append(row)
    return rows


def suggestion(db: store.Store, eff: Effective, rows: list[dict]) -> str | None:
    """Decision 7: the next tier once the last STREAK merged modules all met the bar; advice only."""
    if not eff.explicit or eff.value == "relaxed":
        return None
    last = rows[-STREAK:]
    if len(last) < STREAK or not all(r["ok"] for r in last):
        return None
    return _higher(eff.value)


def suggestion_line(db: store.Store, project: str | os.PathLike) -> str | None:
    """The advice line for `tier`, `status` and a merge; the first time for a start it is also recorded, once."""
    eff = effective(db, project)
    rows = evidence(db)
    up = suggestion(db, eff, rows)
    if up is None:
        return None
    names = "、".join(r["module"] for r in rows[-STREAK:])
    how = "用户确认后用 module-crew tier restore（要原话）" if eff.cap else \
        "用户确认后先 module-crew tier --preflight，再引用原话用 /spec-guard:config"
    since = _start(db)
    try:
        if state(db).get("suggestedFor") != since:
            with db.transaction(actor="autonomy") as tx:
                _put(tx, dict(_state(tx), suggestedFor=since), "tier-suggested", {"to": up, "modules": names})
    except store.StoreError:
        pass
    return (f"可以建议升到 {up}：最近 {STREAK} 个模块（{names}）合并退回 0、撤销 0、返工 ≤ {MAX_REWORK}、用户退回 0。"
            f"只是建议，不自动升；{how}")


INTEGRATION = "集成分支"


def digest(db: store.Store, project: str | os.PathLike, mark_told: bool = False) -> tuple[int, dict, list[str]]:
    """Decision 6: the sync, check-ledger, unqueued-commit and early-landing messages since the last wrap-up, by
    module, for a relaxed tier's one summary; `mark_told` is bookkeeping, not an approval."""
    from module_crew import changes, checks, unqueued
    told = int(state(db).get("toldSeq") or 0)
    sessions = store.records(db, "session")
    module_of = lambda name: (sessions.get(name) or {}).get("module") or name
    groups: dict[str, list[str]] = {}
    add = lambda who, text: groups.setdefault(who, []).append(text)
    last = told
    for e in store.events(db):
        last = max(last, e["seq"])
        if e["seq"] <= told:
            continue
        rec = (e.get("data") or {}).get("record") or {}
        if e["type"] == "item.merged" and rec.get("kind") == "merge-approval" and rec.get("module"):
            commit = (rec.get("mergeCommit") or "")[:7]
            add(rec["module"], f"合入集成分支{f' {commit}' if commit else ''}，已给其他在用模块发同步基线通知")
        elif e["type"] in ("request.landed", "request.partly-landed"):
            early = "（名单内提前落地）" if rec.get("fromModule") else ""
            add(module_of(rec.get("from")), f"公共变更 C{e['key']}（{'、'.join(rec.get('files') or [])}）落地 "
                f"{((e.get('data') or {}).get('commit') or '')[:7]}{early}，已通知各模块同步")
        elif e["type"] == "check.recorded":
            who = rec.get("by")
            add(module_of(who) if who in sessions else INTEGRATION,
                f"{checks.NAMES.get(rec.get('kind'), rec.get('kind'))} {checks.RESULT_NAMES.get(rec.get('result'), rec.get('result'))}"
                f"（树 {(rec.get('tree') or '')[:7]}{'' if who in sessions else f'，{who}'}）")
        elif e["type"] == "config.integration-seen" and (e.get("data") or {}).get("by") == "unqueued":
            d = e["data"]
            add(INTEGRATION, f"不经合并队列的提交已通知各模块同步（到 {(d.get('new') or '')[:7]}）")
    found = unqueued.find(db, project)
    if found.commits and found.head != state(db).get("toldUnqueued"):
        add(INTEGRATION, unqueued.describe(found) + "，还没通知各模块同步")
    landed = changes.landed_rows(db)
    doc = {"groups": groups, "landed": [r["request"] for r in landed], "toldSeq": told}
    if not groups:
        return 3, doc, ["没有要汇总的：上次汇总之后没有同步、检查账、不经队列的提交或提前落地"]
    lines = ["收尾汇总（relaxed：以下几类不逐条告诉用户，收尾时一次说明）："]
    for who, texts in groups.items():
        lines.append(f"- {who}：")
        lines += [f"  - {t}" for t in texts]
    if mark_told:
        if landed:
            changes.mark_told(db, [r["request"] for r in landed])
        with db.transaction(actor="coordinator") as tx:
            _put(tx, dict(_state(tx), toldSeq=last, toldUnqueued=found.head if found.commits else None), "digest-told",
                 {"toldSeq": last})
        lines.append("已记为汇总给用户（只是记账，不是批准）")
    return 0, doc, lines
