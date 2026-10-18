"""Permission rules the host actually honours, for the integration checkout and every module worktree
(see spec/crew-host-permissions.md).

Routine work inside decision 44 (1) is allowed; irreversible work is denied (Claude) or forbidden (Codex), never
"ask": an ask rule was seen not to prompt in a session opened by another session.  Nothing is written without the
user's words, files that git does not ignore are never touched, and only what module-crew added is ever removed.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path

from module_crew import probe, store

ROOT = Path(__file__).resolve().parents[1]
CREW_BIN = str(ROOT / "bin" / "module-crew")
CLAUDE_FILE = Path(".claude") / "settings.local.json"
CODEX_FILE = Path(".codex") / "rules" / "module-crew.rules"
CODEX_MARK = "# module-crew rules"

ROUTINE = ["git add", "git commit", "git status", "git diff", "git log", "git show"]
IRREVERSIBLE = ["git push", "rm -rf", "git reset --hard", "git branch -D", "git worktree remove", "git config --global",
                "npm install -g", "pnpm add -g", "pip install", "brew install"]
PIPED = ["curl * | sh", "curl * | bash"]          # Claude only: not expressible as a Codex prefix rule


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def claude_entries(cfg: dict) -> dict[str, list[str]]:
    """The fixed allow/deny lists (key decision 1); the check command is allowed as written, nothing wider."""
    allow = [f"Bash({CREW_BIN} *)"] + [f"Bash({c} *)" for c in ROUTINE] + ["mcp__agent-relay"]
    if cfg.get("checkCommand"):
        allow += [f"Bash({cfg['checkCommand']})", f"Bash({cfg['checkCommand']} *)"]
    deny = [f"Bash({c} *)" for c in IRREVERSIBLE] + ["Bash(git push)"] + [f"Bash({c})" for c in PIPED]
    return {"allow": allow, "deny": deny}


def checkouts(project: Path) -> tuple[store.Store, dict, list[dict]]:
    """The integration checkout (always Claude) and every active module worktree with its host."""
    db = store.open_store(project)
    cfg = store.get(db, "config", "main") or {}
    found = []
    integration = probe._checkout_of(project, cfg.get("integrationBranch", ""))
    if integration is not None:
        found.append({"role": "integration", "module": None, "name": None, "host": "claude-desktop", "checkout": integration})
    for name, rec in sorted(store.records(db, "session").items()):
        if rec.get("role") == "dev" and rec.get("status") == "active":
            found.append({"role": "dev", "module": rec.get("module"), "name": name,
                          "host": rec.get("host", "claude-desktop"), "checkout": Path(rec["worktree"])})
    return db, cfg, found


def _ignored(checkout: Path, rel: Path) -> bool:
    return _git(checkout, "check-ignore", "-q", str(rel)).returncode == 0


def codex_trust(checkout: Path, project: Path) -> str:
    """trusted / untrusted / not-set / unknown, read-only from $CODEX_HOME/config.toml (or ~/.codex)."""
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    try:
        text = (home / "config.toml").read_text(encoding="utf-8")
    except FileNotFoundError:
        return "not-set"
    except (OSError, UnicodeDecodeError):
        return "unknown"
    wanted = {str(checkout), str(checkout.resolve()), str(project), str(project.resolve())}
    current, levels = None, {}
    for line in text.splitlines():
        head = re.match(r'\s*\[projects\.(?:"([^"]+)"|\'([^\']+)\')\]\s*$', line)
        if head:
            current = head.group(1) or head.group(2)
            continue
        if line.strip().startswith("["):
            current = None
            continue
        level = re.match(r'\s*trust_level\s*=\s*"(\w+)"', line)
        if current and level:
            levels[current] = level.group(1)
    hits = [levels[p] for p in wanted if p in levels]
    if "trusted" in hits:
        return "trusted"
    return "untrusted" if hits else "not-set"


def hook_state(project: Path) -> dict:
    """Can the pre-push guard go into the common git directory? (key decision 5)"""
    hooks_path = _git(project, "config", "core.hooksPath").stdout.strip()
    common = _git(project, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
    path = Path(common) / "hooks" / "pre-push"
    if hooks_path:
        return {"installable": False, "installed": False, "path": str(path),
                "reason": f"仓库设了 core.hooksPath（{hooks_path}），git 不读公共目录的钩子"}
    if path.exists():
        ours = _is_ours(path)
        return {"installable": ours, "installed": ours, "path": str(path),
                "reason": None if ours else "已有别的 pre-push 钩子，不覆盖"}
    return {"installable": True, "installed": False, "path": str(path), "reason": None}


def _is_ours(path: Path) -> bool:
    from module_crew import prepush
    try:
        return prepush.MARK in path.read_text(encoding="utf-8").splitlines()[:3]
    except (OSError, UnicodeDecodeError):
        return False


def _target(t: dict, cfg: dict, project: Path) -> dict:
    checkout = t["checkout"]
    out = {k: v for k, v in t.items() if k != "checkout"}
    out["checkout"] = str(checkout)
    if not checkout.is_dir():
        return {**out, "file": None, "ignored": False, "problem": f"checkout 不存在：{checkout}"}
    if t["host"] == "codex-desktop":
        rel = CODEX_FILE
        out.update(rules=codex_rules(cfg), trust=codex_trust(checkout, project))
    else:
        rel = CLAUDE_FILE
        want = claude_entries(cfg)
        have, problem = _read_settings(checkout / rel)
        out["problem"] = problem
        perms = (have or {}).get("permissions") or {}
        out.update(allow=[e for e in want["allow"] if e not in perms.get("allow", [])],
                   deny=[e for e in want["deny"] if e not in perms.get("deny", [])])
    out.update(file=str(checkout / rel), ignored=_ignored(checkout, rel))
    out.setdefault("problem", None)
    return out


def _read_settings(path: Path) -> tuple[dict | None, str | None]:
    if not path.exists():
        return {}, None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return None, f"读不出 {path}：{exc}"
    if not isinstance(doc, dict) or not isinstance(doc.get("permissions", {}), dict):
        return None, f"{path} 的格式认不出（顶层或 permissions 不是对象）"
    return doc, None


def plan(project: str | os.PathLike) -> dict:
    """Read-only preview: what each checkout would get, what blocks it, and whether the push guard can go in."""
    project = Path(project)
    _, cfg, found = checkouts(project)
    return {"targets": [_target(t, cfg, project) for t in found], "hook": hook_state(project)}


TRUST_TEXT = {"trusted": "项目已被 Codex 信任，规则会生效",
              "untrusted": "项目被标为不受 Codex 信任，规则不会生效；要生效请你在 Codex 里信任该项目",
              "not-set": "项目没有被 Codex 信任，规则不会生效；要生效请你在 Codex 里信任该项目",
              "unknown": "读不出 Codex 的信任设置，不知道规则会不会生效"}


def render_plan(p: dict) -> list[str]:
    lines = []
    for t in p["targets"]:
        who = "集成 checkout（模块协调）" if t["role"] == "integration" else f"模块 {t['module']}（{t['name']}）"
        lines.append(f"{who}：{t['file'] or t['checkout']}")
        if t.get("problem"):
            lines.append(f"  ❌ 不能写：{t['problem']}")
        if t["file"] and not t["ignored"]:
            lines.append("  ❌ 不能写：这个文件没有被 git 忽略（先加进 .gitignore）")
        if "rules" in t:
            lines.append(f"  Codex 规则：放行 {len([r for r in t['rules'] if r['decision'] == 'allow'])} 条、禁止 "
                         f"{len([r for r in t['rules'] if r['decision'] == 'forbidden'])} 条")
            lines.append(f"  {TRUST_TEXT[t['trust']]}")
        else:
            lines.append("  追加放行：" + ("、".join(t["allow"]) or "无（已都有）"))
            lines.append("  追加禁止：" + ("、".join(t["deny"]) or "无（已都有）"))
    h = p["hook"]
    lines.append("推送守门（pre-push 钩子）：" + ("已装" if h["installed"] else "可以装" if h["installable"]
                                            else f"不装——{h['reason']}；推送只能靠宿主的禁止规则"))
    return lines


def codex_rules(cfg: dict) -> list[dict]:
    """Codex prefix rules matching the Claude lists (key decision 3)."""
    rules = [{"pattern": [CREW_BIN], "decision": "allow", "match": [f"{CREW_BIN} status"]}]
    rules += [{"pattern": c.split(), "decision": "allow", "match": [c]} for c in ROUTINE]
    if cfg.get("checkCommand"):
        tokens = shlex.split(cfg["checkCommand"])
        rules.append({"pattern": tokens, "decision": "allow", "match": [cfg["checkCommand"]]})
    rules += [{"pattern": c.split(), "decision": "forbidden", "match": [f"{c} x"],
               "justification": "module-crew：不可逆操作不在会话里做；推送只经模块协调的 module-crew merge push（要用户原话）"}
              for c in IRREVERSIBLE]
    return rules
