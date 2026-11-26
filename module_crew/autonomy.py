"""spec-guard autonomyTier: what module-crew loosens at each tier, the evidence for a step up and the automatic step
down after an incident (see spec/crew-autonomy-tier.md)."""

from __future__ import annotations

import os
from pathlib import Path

from module_crew import probe, store

DIGEST = "digest"                     # config/main.digest: on | off (crew-takeover-approve)
FIELD = "autonomy"                    # config/main.autonomy: cap, capFor, incident, seen, suggestedFor, toldSeq
INCIDENTS = ("merge-returned", "revoked", "rework-over-limit", "baseline-red")


def integration_checkout(db: store.Store, project: str | os.PathLike) -> Path:
    """Assumption 3: the tier is read where the integration branch is checked out."""
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch")
    found = probe._checkout_of(Path(project), branch) if branch else None
    return found or Path(project)


def state(db: store.Store) -> dict:
    """module-crew's own tier bookkeeping, kept in config/main (the config kind has one key)."""
    return dict((store.get(db, "config", "main") or {}).get(FIELD) or {})


def _state(tx) -> dict:
    return dict((tx.get("config", "main") or {}).get(FIELD) or {})


def _put(tx, rec: dict, action: str, data: dict) -> None:
    tx.put("config", "main", {**(tx.get("config", "main") or {}), FIELD: rec}, action=action, data=data)


def project_of(db: store.Store) -> Path:
    """The repository a store belongs to (the store lives in its common git dir)."""
    return db.path.parent.parent


def digest_on(db: store.Store) -> bool:
    """crew-takeover-approve decision 11: the wrap-up digest is its own switch now."""
    return (store.get(db, "config", "main") or {}).get(DIGEST) == "on"


def report(db: store.Store, project: str | os.PathLike) -> tuple[dict, list[str]]:
    """`tier` (read only): the digest switch, the last step-down."""
    doc = {"digest": "on" if digest_on(db) else "off", "lastIncident": last_incident(db)}
    return doc, [f"收尾汇总：{'开' if doc['digest'] == 'on' else '关'}（config set --digest on|off，要用户原话）"]


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
    """`status --json` store.autonomy: None unless the digest switch is on."""
    doc, lines = report(db, project)
    if doc["digest"] != "on":
        return None
    return {**doc, "lines": lines}


def status_lines(doc: dict | None) -> list[str]:
    return [f"  {line}" for line in (doc or {}).get("lines") or []]
