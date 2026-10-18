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
        existing = checkout / rel
        if existing.exists() and not _codex_is_ours(existing):
            out["problem"] = f"{existing} 已存在且不是 module-crew 写的，不覆盖"
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


def _codex_is_ours(path: Path) -> bool:
    try:
        return path.read_text(encoding="utf-8").splitlines()[:1] == [CODEX_MARK]
    except (OSError, UnicodeDecodeError):
        return False


def render_codex(rules: list[dict]) -> str:
    """Starlark prefix_rule calls; match / not_match let Codex self-check the file when it loads it."""
    lines = [CODEX_MARK, "# 由 module-crew permissions apply 写入；module-crew permissions remove 会删除本文件。", ""]
    for r in rules:
        args = [f"pattern = {json.dumps(r['pattern'], ensure_ascii=False)}", f"decision = {json.dumps(r['decision'])}"]
        if r.get("justification"):
            args.append(f"justification = {json.dumps(r['justification'], ensure_ascii=False)}")
        args.append(f"match = {json.dumps(r['match'], ensure_ascii=False)}")
        args.append('not_match = ["git status --short"]' if r["pattern"][:2] != ["git", "status"] else 'not_match = ["git stash"]')
        lines.append("prefix_rule(\n    " + ",\n    ".join(args) + ",\n)\n")
    return "\n".join(lines)


class Refused(Exception):
    """Nothing was written."""


def _need(original: str | None) -> str:
    if not original or not original.strip():
        raise Refused("用户原话不能为空：写权限规则要用户明确同意")
    return original


def _blockers(p: dict) -> list[str]:
    out = []
    for t in p["targets"]:
        if t.get("problem"):
            out.append(t["problem"])
        elif t["file"] and not t["ignored"]:
            out.append(f"{t['file']} 没有被 git 忽略")
    return out


def _write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def apply(project: str | os.PathLike, original: str | None) -> list[str]:
    """Write every checkout's rules, all or nothing, and record what was added."""
    project = Path(project)
    original = _need(original)
    db, cfg, _ = checkouts(project)
    p = plan(project)
    problems = _blockers(p)
    if problems:
        raise Refused("没有写任何文件：" + "；".join(problems))
    record = cfg.get("permissions") or {}
    files = dict(record.get("files") or {})
    codex_files = set(record.get("codexFiles") or [])
    lines = []
    for t in p["targets"]:
        path = Path(t["file"])
        if "rules" in t:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_codex(t["rules"]), encoding="utf-8")
            codex_files.add(str(path))
            lines.append(f"已写 Codex 规则：{path}（{TRUST_TEXT[t['trust']]}）")
            continue
        doc, _ = _read_settings(path)
        perms = doc.setdefault("permissions", {})
        for key in ("allow", "deny"):
            perms.setdefault(key, []).extend(t[key])
        _write_json(path, doc)
        added = files.setdefault(str(path), {"allow": [], "deny": []})
        for key in ("allow", "deny"):
            added[key] += [e for e in t[key] if e not in added[key]]
        lines.append(f"已写 {path}：追加放行 {len(t['allow'])} 条、禁止 {len(t['deny'])} 条")
    hook = install_hook(project)
    lines.append(hook["line"])
    with db.transaction(actor="coordinator") as tx:
        _put(tx, {**record, "applied": True, "original": original, "at": store.now(),
                                         **store.source_field(), "files": files, "codexFiles": sorted(codex_files),
                  "hook": {k: v for k, v in hook.items() if k != "line"}})
    return lines


def remove(project: str | os.PathLike, original: str | None) -> list[str]:
    """Take out only the entries, rules files and hook module-crew added; everything else stays."""
    project = Path(project)
    original = _need(original)
    db = store.open_store(project)
    record = read_record(db)
    files = record.get("files") or {}
    docs = {}
    for name in files:
        path = Path(name)
        if path.exists():
            doc, problem = _read_settings(path)
            if problem:
                raise Refused("没有改任何文件：" + problem)
            docs[name] = doc
    lines = []
    for name, doc in docs.items():
        perms = doc.get("permissions") or {}
        gone = 0
        for key in ("allow", "deny"):
            if key in perms:
                keep = [e for e in perms[key] if e not in files[name].get(key, [])]
                gone += len(perms[key]) - len(keep)
                perms[key] = keep
        _write_json(Path(name), doc)
        lines.append(f"已从 {name} 删除 module-crew 追加的 {gone} 条")
    for name in record.get("codexFiles") or []:
        path = Path(name)
        if path.exists() and _codex_is_ours(path):
            path.unlink()
            lines.append(f"已删除 Codex 规则：{path}")
    lines.append(uninstall_hook(project))
    with db.transaction(actor="coordinator") as tx:
        _put(tx, {**record, "applied": False, "files": {}, "codexFiles": [],
                  "removed": {"original": original, "at": store.now(), **store.source_field()}})
    return lines


def read_record(db: store.Store) -> dict:
    """What module-crew wrote, kept in the run configuration (store format unchanged)."""
    return (store.get(db, "config", "main") or {}).get("permissions") or {}


def _put(tx, record: dict) -> None:
    tx.put("config", "main", {**(tx.get("config", "main") or {}), "permissions": record}, action="set")


def install_hook(project: Path) -> dict:
    """Placeholder until the pre-push guard lands (Task 4)."""
    return {"installed": False, "path": None, "reason": "推送守门还没实现", "line": "推送守门：还没实现"}


def uninstall_hook(project: Path) -> str:
    return "推送守门：没有要删的"
