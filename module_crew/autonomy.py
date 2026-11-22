"""spec-guard autonomyTier: what module-crew loosens at each tier, the evidence for a step up and the automatic step
down after an incident (see spec/crew-autonomy-tier.md)."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from module_crew import probe, store

DIGEST = "digest"                     # config/main.digest: on | off (crew-takeover-approve)
FIELD = "autonomy"                    # config/main.autonomy: cap, capFor, incident, seen, suggestedFor, toldSeq
TIERS = ("strict", "standard", "relaxed")
READ_FROM = ("python3", "-B", "hooks/project_config.py", "show", "--project", "<project-root>", "--format", "json")
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


def retired(eff: Effective) -> str | None:
    """crew-takeover-approve decision 11: an old autonomyTier still written in .agent/config.json (not strict)."""
    t = eff.configured
    return t.value if t.explicit and t.value != "strict" else None


def retired_line(value: str) -> str:
    return (f"autonomyTier 已退役、不再生效（旧值 {value} 不映射为接管档位）：要接管用 /spec-guard:config 设 takeover；"
            "原来顺带打开的评审节奏（reviewCadence）、声明范围（config set --declared-scope）、"
            "收尾汇总（config set --digest）请分别设")


def digest_on(db: store.Store) -> bool:
    """crew-takeover-approve decision 11: the wrap-up digest is its own switch now."""
    return (store.get(db, "config", "main") or {}).get(DIGEST) == "on"


def report(db: store.Store, project: str | os.PathLike) -> tuple[dict, list[str]]:
    """`tier` (read only): the retired-tier hint, the digest switch, the last step-down."""
    eff = effective(db, project)
    old = retired(eff)
    doc = {"retiredTier": old, "digest": "on" if digest_on(db) else "off", "lastIncident": last_incident(db)}
    lines = ([retired_line(old)] if old else []) + [f"收尾汇总：{'开' if doc['digest'] == 'on' else '关'}"
                                                    "（config set --digest on|off，要用户原话）"]
    return doc, lines


INCIDENT_NAMES = {"merge-returned": "合并因模块的原因退回", "revoked": "用户撤销合并批准",
                  "auto-merge-returned": "自动合的合并因模块的原因退回",          # crew-takeover-merge decision 8
                  "rework-over-limit": "返工满 3 次", "baseline-red": "基线完整检查新跑出失败",
                  "external": "外部信号"}


def incident(db: store.Store, project: str | os.PathLike, kind: str, ref: str, reason: str = "",
             module: str | None = None) -> str | None:
    """crew-takeover-approve decision 9: one step stricter through spec-guard's narrowing entry (never twice for the
    same item); the line the calling command prints so the coordinator tells the user at once. Errors only cost the
    line, never the caller."""
    from module_crew import takeover
    key = f"{kind}:{ref}"
    what = INCIDENT_NAMES.get(kind, kind) + (f"（{reason}）" if reason else "")
    try:
        if key in (state(db).get("incidentKeys") or []):
            return None
        last = state(db).get("incident") or {}
        if kind == "baseline-red" and last.get("kind") == kind and last.get("commit") and \
                last.get("commit") == probe._git(takeover.checkout(db, project), "rev-parse", "HEAD").stdout.strip():
            return None             # the same red baseline, re-run only because the narrowing commit changed the tree
        got = takeover.narrow(db, project, module, what)
        if got is None:
            return None
        with db.transaction(actor="autonomy") as tx:
            rec = _state(tx)
            rec.update(incident={"kind": kind, "key": key, "ref": ref, "reason": what, "at": store.now(), **got},
                       incidentKeys=((rec.get("incidentKeys") or []) + [key])[-50:])
            _put(tx, rec, "takeover-narrowed", {"kind": kind, "key": key, "reason": what, **got})
    except (store.StoreError, OSError, takeover.NarrowFailed) as exc:
        return f"接管档位没能收窄（{exc}）：请告诉用户，由用户决定是否用 /spec-guard:config 调低"
    change = "；".join(f"{k} {got['before'][k]} → {got['after'].get(k)}" for k in got["before"])
    return f"接管档位已收窄（{change}）：{what}。马上告诉用户；恢复要用户原话，经 /spec-guard:config 一次升一档"


class Refused(Exception):
    pass


def degrade(db: store.Store, project: str | os.PathLike, reason: str | None, ref: str | None) -> tuple[int, str]:
    """S95, parameters unchanged: an outside signal narrows one step by the same rules as incident(); module-crew does
    not read or parse anything behind --ref or --reason. No user words needed (widening still needs them)."""
    reason, ref = (reason or "").strip(), (ref or "").strip()
    if not reason or not ref:
        raise Refused("--reason 和 --ref 都不能为空")
    what = f"{INCIDENT_NAMES['external']}（{reason}）"
    if f"external:{ref}" in (state(db).get("incidentKeys") or []):
        return 0, f"同一个 --ref 已经收窄过，这次没收窄：{ref}"
    line = incident(db, project, "external", ref, reason)
    if line is None:
        return 0, f"没有收窄（没有接管的项，或已是最严）：{what}"
    return (2 if "没能收窄" in line else 0), line


def last_incident(db: store.Store) -> dict | None:
    """S95: the most recent step-down as {kind, reason, ref, at}; older records keep the ref only inside their key."""
    inc = state(db).get("incident")
    if not inc:
        return None
    ref = inc.get("ref") or (inc.get("key") or "").partition(":")[2]
    return {"kind": inc.get("kind"), "reason": inc.get("reason"), "ref": ref, "at": inc.get("at")}


def restore(db: store.Store, project: str | os.PathLike, original: str | None) -> list[str]:
    """crew-takeover-approve decision 10: retired; widening is spec-guard's, on the user's words."""
    raise Refused("tier restore 已退役：放宽档位要用户原话、一次升一档，用 /spec-guard:config 写（module-crew 不再存降档上限）")


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


def status(db: store.Store, project: str | os.PathLike) -> dict | None:
    """`status --json` store.autonomy: None unless an old tier is still written or the digest switch is on."""
    doc, lines = report(db, project)
    if not doc["retiredTier"] and doc["digest"] != "on":
        return None
    return {**doc, "lines": lines}


def status_lines(doc: dict | None) -> list[str]:
    return [f"  {line}" for line in (doc or {}).get("lines") or []]
