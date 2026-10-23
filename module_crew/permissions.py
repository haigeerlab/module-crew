"""Permission rules the host actually honours, for the integration checkout and every module worktree
(see spec/crew-host-permissions.md).

Routine work inside decision 44 (1) is allowed; irreversible work is denied (Claude) or forbidden (Codex), never
"ask": an ask rule does prompt, but one "allow" click runs the command (decision 67).  Nothing is written without the
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
MANAGED_SETTINGS = Path("/Library/Application Support/ClaudeCode/managed-settings.json")

ROUTINE = ["git add", "git commit", "git status", "git diff", "git log", "git show"]
IRREVERSIBLE = ["git push", "rm -rf", "git reset --hard", "git branch -D", "git worktree remove", "git config --global",
                "npm install -g", "pnpm add -g", "brew install"]
PIPED = ["curl * | sh", "curl * | bash"]          # Claude only: not expressible as a Codex prefix rule
# R21 MC-1 (decision 62, 0.5.1): installing dependencies is routine, adding a new package included (new dependencies
# are listed at final acceptance by spec-guard SG-5). Bare `pip install x` gets no rule: outside a venv it installs
# into the system or user Python. Installing globally stays denied, wherever the flag sits.
LOCKFILE_CLAUDE = ["npm ci", "npm ci *", "npm install", "pnpm install", "pnpm install --frozen-lockfile", "yarn install",
                   "uv sync", "uv sync *", "pip install -r *", ".venv/bin/pip install -r *",
                   "npm install *", "pnpm add *", "yarn add *", "uv add *", "uv pip install *", ".venv/bin/pip install *"]
GLOBAL_CLAUDE = ["npm * -g", "npm * -g *", "npm * --global", "npm * --global *", "pnpm * -g", "pnpm * -g *",
                 "pnpm * --global", "pnpm * --global *", "yarn global *", "uv * --system", "uv * --system *"]
# Codex prefix rules only match from the start: allowing `npm install` would let `npm install x -g` through, so adding a
# package stays with Codex's own approval there, and only prefixes that never add a package are allowed.
LOCKFILE_CODEX = ["npm ci", "pnpm install --frozen-lockfile", "yarn install", "uv sync", "pip install -r",
                  ".venv/bin/pip install -r"]
GLOBAL_CODEX = ["npm i -g", "npm install --global", "npm i --global", "pnpm add --global", "yarn global add"]


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def claude_entries(cfg: dict, entry: str | os.PathLike, worktree: Path | None = None) -> dict[str, list[str]]:
    """The fixed allow/deny lists (key decision 1); the check command is allowed as written, nothing wider.
    `entry` is the store's fixed launcher (crew-command-entry decision 6), so an upgrade does not stale the rule.

    A module worktree also gets its own files to edit (crew-stage-c-fixes MC-13), except its `.claude/`, so the
    session cannot rewrite its permissions. `//` makes the path absolute in Claude Code's gitignore-style rules."""
    allow = ([f"Bash({entry} *)"] + [f"Bash({c} *)" for c in ROUTINE] + ["mcp__agent-relay"]
             + [f"Bash({c})" for c in LOCKFILE_CLAUDE])
    if cfg.get("checkCommand"):
        allow += [f"Bash({cfg['checkCommand']})", f"Bash({cfg['checkCommand']} *)"]
    deny = ([f"Bash({c} *)" for c in IRREVERSIBLE] + ["Bash(git push)"] + [f"Bash({c})" for c in PIPED]
            + [f"Bash({c})" for c in GLOBAL_CLAUDE])
    if worktree is not None:
        root = "//" + str(worktree).lstrip("/")
        allow.append(f"Edit({root}/**)")
        deny.append(f"Edit({root}/.claude/**)")
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
        from module_crew import prepush
        ours = _is_ours(path)
        return {"installable": ours, "installed": ours and prepush.is_active(path), "path": str(path),
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
        from module_crew import launcher
        out.update(rules=codex_rules(cfg, launcher.entry(store.open_store(project).path)),
                   trust=codex_trust(checkout, project))
        existing = checkout / rel
        if existing.exists() and not _codex_is_ours(existing):
            out["problem"] = f"{existing} 已存在且不是 module-crew 写的，不覆盖"
    else:
        rel = CLAUDE_FILE
        from module_crew import launcher
        want = claude_entries(cfg, launcher.entry(store.open_store(project).path),
                              checkout if t["role"] == "dev" else None)
        have, problem = _read_settings(checkout / rel)
        out["problem"] = problem
        perms = (have or {}).get("permissions") or {}
        out.update(allow=[e for e in want["allow"] if e not in perms.get("allow", [])],
                   deny=[e for e in want["deny"] if e not in perms.get("deny", [])])
        out["shadowed"] = shadowed(checkout, want["allow"], want["deny"])
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


def _sample(entry: str) -> tuple[str, str | None]:
    """A command an allow entry lets through: `Bash(npm install *)` -> ("Bash", "npm install x")."""
    if entry.startswith("Bash(") and entry.endswith(")"):
        return "Bash", entry[5:-1].replace("*", "x")
    return entry, None


def rule_matches(rule: str, tool: str, command: str | None) -> bool:
    """Claude Code's rule shape, near enough for single commands: `*` is any text, a lone trailing ` *` (or `:*`) also
    matches the bare command, and a bare tool name (`Bash`, `Bash(*)`, `mcp__x`) matches everything of that tool."""
    if rule in (tool, f"{tool}(*)"):
        return True
    if command is None or not (rule.startswith(f"{tool}(") and rule.endswith(")")):
        return False
    body = rule[len(tool) + 1:-1]
    if body.endswith(":*"):
        body = body[:-2] + " *"
    if body.endswith(" *") and body.count("*") == 1 and command == body[:-2]:
        return True
    return re.fullmatch(".*".join(map(re.escape, body.split("*"))), command) is not None


def _layers(checkout: Path) -> list[Path]:
    """Every other settings file the host reads for a session in this checkout (decision 8)."""
    files = [checkout / ".claude" / "settings.json"]
    common = _git(checkout, "rev-parse", "--path-format=absolute", "--git-common-dir")
    main = Path(common.stdout.strip()).parent if common.returncode == 0 else None
    if main is not None and main.resolve() != checkout.resolve():
        files += [main / CLAUDE_FILE, main / ".claude" / "settings.json"]
    home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    return files + [home / "settings.json", MANAGED_SETTINGS]


def shadowed(checkout: Path, allow: list[str], own_deny: list[str]) -> list[dict]:
    """Allow entries that an ask or deny rule elsewhere would win over (the host checks deny, then ask, then allow)."""
    found = []
    for path in [checkout / CLAUDE_FILE] + _layers(checkout):
        doc, _ = _read_settings(path)
        perms = (doc or {}).get("permissions") or {}
        for kind in ("deny", "ask"):
            for rule in perms.get(kind) or []:
                if not isinstance(rule, str) or (kind == "deny" and rule in own_deny):
                    continue
                found += [{"allow": entry, "file": str(path), "kind": kind, "rule": rule}
                          for entry in allow if rule_matches(rule, *_sample(entry))]
    return found


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
            lines += _shadow_lines(t)
    h = p["hook"]
    lines.append("推送守门（pre-push 钩子）：" + ("已装" if h["installed"] else "可以装" if h["installable"]
                                            else f"不装——{h['reason']}；推送只能靠宿主的禁止规则"))
    return lines


def _shadow_lines(t: dict) -> list[str]:
    return [f"  ⚠️ 会被盖过：{f['allow']} ← {f['file']} 的 {'ask' if f['kind'] == 'ask' else '禁止'} {f['rule']}"
            for f in t.get("shadowed") or []]


def codex_rules(cfg: dict, entry: str | os.PathLike) -> list[dict]:
    """Codex prefix rules matching the Claude lists (key decision 3); `entry` is the store's fixed launcher
    (crew-command-entry), not this plugin copy's versioned bin."""
    entry = str(entry)
    rules = [{"pattern": [entry], "decision": "allow", "match": [f"{entry} status"]}]
    rules += [{"pattern": c.split(), "decision": "allow", "match": [c]} for c in ROUTINE + LOCKFILE_CODEX]
    if cfg.get("checkCommand"):
        tokens = shlex.split(cfg["checkCommand"])
        rules.append({"pattern": tokens, "decision": "allow", "match": [cfg["checkCommand"]]})
    rules += [{"pattern": c.split(), "decision": "forbidden", "match": [f"{c} x"],
               "justification": "module-crew：不可逆操作不在会话里做；推送只经模块协调的 module-crew merge push（要用户原话）"}
              for c in IRREVERSIBLE + GLOBAL_CODEX]
    return rules


def _codex_is_ours(path: Path) -> bool:
    try:
        return path.read_text(encoding="utf-8").splitlines()[:1] == [CODEX_MARK]
    except (OSError, UnicodeDecodeError):
        return False


def render_codex(rules: list[dict]) -> str:
    """Starlark prefix_rule calls; match / not_match let Codex self-check the file when it loads it."""
    lines = [CODEX_MARK, "# 由 module-crew permissions apply 写入；module-crew permissions remove 会清空本文件的规则。", ""]
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
    from module_crew import start
    lines = [start.launcher_line(db)]             # the rules below allow this entry, so it must exist first
    for t in p["targets"]:
        path = Path(t["file"])
        if "rules" in t:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_codex(t["rules"]), encoding="utf-8")
            codex_files.add(str(path))
            lines.append(f"已写 Codex 规则：{path}（{TRUST_TEXT[t['trust']]}）")
            continue
        doc, _ = _read_settings(path)
        before = path.read_text(encoding="utf-8") if path.exists() else None
        perms = doc.setdefault("permissions", {})
        for key in ("allow", "deny"):
            perms.setdefault(key, []).extend(t[key])
        _write_json(path, doc)
        added = files.setdefault(str(path), {"allow": [], "deny": [], "original": before})
        for key in ("allow", "deny"):
            added[key] += [e for e in t[key] if e not in added[key]]
        lines.append(f"已写 {path}：追加放行 {len(t['allow'])} 条、禁止 {len(t['deny'])} 条")
        lines += _shadow_lines(t)
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
        rec = files[name]
        before = rec.get("original")
        try:
            first = json.loads(before) if before else {}
        except ValueError:
            first = None
        had = (first or {}).get("permissions") if isinstance((first or {}).get("permissions"), dict) else {}
        perms = doc.get("permissions") or {}
        gone = 0
        for key in ("allow", "deny"):
            if key in perms:
                keep = [e for e in perms[key] if e not in rec.get(key, [])]
                gone += len(perms[key]) - len(keep)
                perms[key] = keep
                if not keep and key not in (had or {}):
                    del perms[key]          # the list module-crew created
        if "permissions" in doc and not perms and "permissions" not in (first or {}):
            del doc["permissions"]
        path = Path(name)
        if before is not None and first == doc:
            path.write_text(before, encoding="utf-8")       # nothing else changed: the user's own text, byte for byte
            lines.append(f"已从 {name} 删除 module-crew 追加的 {gone} 条，文件恢复为 apply 之前的原文")
        else:
            _write_json(path, doc)
            lines.append(f"已从 {name} 删除 module-crew 追加的 {gone} 条")
    for name in record.get("codexFiles") or []:
        path = Path(name)
        if path.exists() and _codex_is_ours(path):
            # module-crew never deletes files: the rules are emptied, the file itself may be removed by hand
            path.write_text(CODEX_MARK + "\n# 已由 module-crew permissions remove 停用：本文件不含任何规则，可以手动删除。\n", encoding="utf-8")
            lines.append(f"已停用 Codex 规则：{path}（文件只剩说明，可手动删除）")
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
    """Install the pre-push guard when nothing else owns the hook; never overwrite someone else's (key decision 5)."""
    from module_crew import prepush
    state = hook_state(project)
    if not state["installable"]:
        return {"installed": False, "path": state["path"], "reason": state["reason"],
                "line": f"推送守门：没装——{state['reason']}；推送只能靠宿主的禁止规则，要不要另想办法请你决定"}
    db = store.open_store(project)
    cfg = store.get(db, "config", "main") or {}
    prepush.install(Path(state["path"]), cfg.get("crewDir", ""), db.path)
    return {"installed": True, "path": state["path"], "reason": None, "line": f"推送守门：已装 {state['path']}"}


def uninstall_hook(project: Path) -> str:
    from module_crew import prepush
    path = Path(hook_state(project)["path"])
    if path.exists() and _is_ours(path) and prepush.is_active(path):
        prepush.disable(path)
        return f"推送守门：已停用 {path}（文件改为空操作，可手动删除）"
    return "推送守门：没有 module-crew 装的钩子"


def follow(project: str | os.PathLike, name: str) -> str | None:
    """After `start prepare`: when rules were applied, write them for this new worktree too; a failure never blocks."""
    project = Path(project)
    db, cfg, found = checkouts(project)
    record = cfg.get("permissions") or {}
    if not record.get("applied"):
        return None
    t = next((x for x in found if x["name"] == name), None)
    target = _target(t, cfg, project) if t else None
    problem = (target or {}).get("problem") or (None if target and target["ignored"] else "文件没有被 git 忽略")
    if target is None:
        problem = f"没有在用的会话 {name}"
    files = dict(record.get("files") or {})
    codex_files = set(record.get("codexFiles") or [])
    failed = dict(record.get("followFailed") or {})
    if problem:
        failed[name] = problem
        line = f"⚠️ 没给 {name} 写权限规则：{problem}（不影响开工；处理后重跑 permissions apply）"
    else:
        failed.pop(name, None)
        path = Path(target["file"])
        if "rules" in target:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render_codex(target["rules"]), encoding="utf-8")
            codex_files.add(str(path))
        else:
            doc, _ = _read_settings(path)
            before = path.read_text(encoding="utf-8") if path.exists() else None
            perms = doc.setdefault("permissions", {})
            added = files.setdefault(str(path), {"allow": [], "deny": [], "original": before})
            for key in ("allow", "deny"):
                perms.setdefault(key, []).extend(target[key])
                added[key] += [e for e in target[key] if e not in added[key]]
            _write_json(path, doc)
        line = f"已写权限规则：{path}"
    with db.transaction(actor="coordinator") as tx:
        _put(tx, {**record, "files": files, "codexFiles": sorted(codex_files), "followFailed": failed})
    return line


ALLOWED_PROBES = [("git status", "git status"), ("git add --dry-run .", "git add --dry-run ."),
                  ("bridge_agents", "mcp__agent-relay__bridge_agents（工具调用）")]
DENIED_PROBE = "git push --dry-run module-crew-probe HEAD"


def verify_list(project: str | os.PathLike, host: str = "claude") -> list[str]:
    """What the coordinator asks a new module session to run, and what to watch for (key decision 6)."""
    from module_crew import launcher
    probes = [("module-crew status", f"{launcher.entry(store.open_store(project).path)} status"), *ALLOWED_PROBES]
    lines = ["请模块会话在自己的 worktree 里依次运行下面五条，模块协调同时看它的在线状态有没有出现「等待审批」：",
             *[f"  {i}. {cmd}　——应直接运行、不弹确认" for i, (_, cmd) in enumerate(probes, 1)],
             f"  5. {DENIED_PROBE}　——应被宿主拒绝；就算宿主没拦，这个远端名也不存在，推不出去",
             "看完记下：module-crew permissions verify --record <会话名> --allowed ok|prompted --denied ok|ran"]
    if host == "codex":
        lines += _codex_static(project)
    return lines


def _codex_static(project: str | os.PathLike) -> list[str]:
    import shutil
    codex = shutil.which("codex")
    _, cfg, found = checkouts(Path(project))
    files = [Path(t["checkout"]) / CODEX_FILE for t in found if t["host"] == "codex-desktop"]
    if not codex:
        return ["本机没有 codex 命令，跳过 Codex 规则的静态核对"]
    out = []
    for f in files:
        if not f.exists():
            out.append(f"{f} 不存在：先运行 permissions apply")
            continue
        for cmd in ["git status", "git commit -m x", "git push origin main", "rm -rf build"]:
            res = subprocess.run([codex, "execpolicy", "check", "--rules", str(f), *cmd.split()],
                                 capture_output=True, text=True, stdin=subprocess.DEVNULL)
            try:
                decision = json.loads(res.stdout).get("decision") or "无匹配"
            except ValueError:
                decision = f"读不出结果（退出码 {res.returncode}）"
            out.append(f"Codex 静态核对 {f.parent.parent.parent.name}：{cmd} → {decision}")
    return out


def record_verify(project: str | os.PathLike, name: str, allowed: str, denied: str) -> str:
    db = store.open_store(Path(project))
    rec = store.get(db, "session", name)
    if not rec or rec.get("status") != "active":
        raise Refused(f"{name} 不是状态库里在用的会话")
    with db.transaction(actor="coordinator") as tx:
        record = ((tx.get("config", "main") or {}).get("permissions") or {})
        verified = dict(record.get("verified") or {})
        verified[name] = {"allowed": allowed, "denied": denied, "at": store.now()}
        _put(tx, {**record, "verified": verified})
    return f"已记下 {name} 的权限实测：放行 {VERIFY_TEXT[allowed]}，拒绝 {VERIFY_TEXT[denied]}"


VERIFY_TEXT = {"ok": "如预期", "prompted": "弹了确认", "ran": "没拦住"}


def status_fact(record: dict, name: str) -> str:
    """One status-line fact per session: last field test, or that it was never tested."""
    if name in (record.get("followFailed") or {}):
        return f"权限规则没写上：{record['followFailed'][name]}"
    v = (record.get("verified") or {}).get(name)
    if not v:
        return "权限未实测"
    return f"权限实测 {v['at'][:16].replace('T', ' ')}：放行{VERIFY_TEXT[v['allowed']]}、拒绝{VERIFY_TEXT[v['denied']]}"
