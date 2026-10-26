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
    return doc, [describe(eff)]
