"""The pre-push guard module-crew installs in the common git directory (see spec/crew-host-permissions.md key decision 5).

Host "ask" rules were seen not to prompt in a session opened by another session, so pushing is guarded by git itself:
module worktrees never push, and the integration checkout pushes only with the one-time pass `merge push` writes right
before it runs `git push` (the user's words are what `merge push` requires).  The hook is a standalone stdlib script
with the module-crew directory baked in, so it does not depend on the plugin's location or version.  module-crew never
deletes files: a spent pass is marked used, and removing the guard turns the hook into a no-op.
"""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path

MARK = "# module-crew pre-push"
TOKEN = "push-token.json"
TOKEN_SECONDS = 120

SCRIPT = '''#!/usr/bin/env python3
{mark}
# 由 module-crew permissions apply 安装；module-crew permissions remove 会把它改成空操作。
import json, os, subprocess, sys, time

CREW_DIR = {crew_dir!r}     # module worktrees live under here
STORE = {store!r}           # module-crew state store (holds the one-time push pass)


def deny(why):
    sys.stderr.write("module-crew 推送守门：已拒绝推送。" + why + "\\n")
    sys.exit(1)


if not os.path.isdir(STORE):
    sys.exit(0)             # the project no longer uses module-crew
top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
if top and os.path.realpath(top).startswith(os.path.realpath(CREW_DIR) + os.sep):
    deny("模块会话不推送：做完发最终验收交审，由模块协调合并、按用户原话推送。")
refs = [line.split()[2] for line in sys.stdin.read().splitlines() if len(line.split()) == 4]
path = os.path.join(STORE, {token!r})
try:
    with open(path, encoding="utf-8") as f:
        token = json.load(f)
except (OSError, ValueError):
    token = None
why = "推送只经模块协调的 module-crew merge push（要用户原话）；你自己在终端推送可以加 --no-verify。"
if not token or token.get("used"):
    deny("没有放行凭证。" + why)
if token.get("expires", 0) < time.time():
    deny("放行凭证已过期。" + why)
if not refs or any(r != token.get("ref") for r in refs):
    deny("要推送的分支和放行凭证不符（凭证只放行 " + str(token.get("ref")) + "）。" + why)
token["used"] = True
with open(path, "w", encoding="utf-8") as f:
    json.dump(token, f)
sys.exit(0)
'''

NOOP = '''#!/usr/bin/env python3
{mark}
# module-crew permissions remove 已停用推送守门：本脚本什么都不做，可以手动删除。
import sys
sys.exit(0)
'''


def install(path: Path, crew_dir: str, store_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SCRIPT.format(mark=MARK, crew_dir=crew_dir, store=str(store_dir), token=TOKEN), encoding="utf-8")
    path.chmod(0o755)


def disable(path: Path) -> None:
    path.write_text(NOOP.format(mark=MARK), encoding="utf-8")
    path.chmod(0o755)


def is_active(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return MARK in text.splitlines()[:3] and "CREW_DIR" in text


def write_token(store_dir: Path, ref: str) -> None:
    """One-time pass for exactly one remote ref, valid for TOKEN_SECONDS."""
    (store_dir / TOKEN).write_text(json.dumps({"ref": ref, "expires": time.time() + TOKEN_SECONDS,
                                               "nonce": secrets.token_hex(8), "used": False}), encoding="utf-8")


def spend_token(store_dir: Path) -> None:
    path = store_dir / TOKEN
    if path.exists():
        try:
            token = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            token = {}
        path.write_text(json.dumps({**token, "used": True}), encoding="utf-8")
