"""【公共变更请求】: record, hint, land on the integration baseline, or decline (see spec/crew-shared-changes.md)."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from module_crew import commits, probe, protocol, store, sync
from module_crew.inbox import AnswerRefused, Outcome, Reply

# Routing hints (spec decision 4); only ever added to.
DEPENDENCY_FILES = {"package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "pyproject.toml", "poetry.lock",
                    "Cargo.toml", "Cargo.lock", "go.mod", "go.sum", "Gemfile", "Gemfile.lock"}
CI_PREFIXES = (".github/", ".gitlab-ci.yml", ".circleci/")
ASK_USER = ("dependency", "ci", "migration", "conflict:")


def hints_for(files: list[str], others: dict[str, list[str]]) -> list[str]:
    """Hints for one request; `others` maps open request numbers to their file lists."""
    hints = []
    names = [PurePosixPath(f).name for f in files]
    if any(n in DEPENDENCY_FILES or (n.startswith("requirements") and n.endswith(".txt")) for n in names):
        hints.append("dependency")
    if any(f.startswith(CI_PREFIXES) for f in files):
        hints.append("ci")
    if any("migration" in f.lower() for f in files):
        hints.append("migration")
    hints += [f"conflict:{n}" for n, theirs in others.items() if set(files) & set(theirs)]
    return hints


def _asks_user(hints: list[str]) -> bool:
    return any(h.startswith(ASK_USER) for h in hints)


def _module_of(sessions: dict, sender: str) -> str:
    return (sessions.get(sender) or {}).get("module") or sender


def _active(db: store.Store, sender: str) -> bool:
    rec = store.get(db, "session", sender)
    return bool(rec) and rec.get("role") == "dev" and rec.get("status") == "active"


def add(db: store.Store, text: str, sender: str, relay_id: int) -> Outcome:
    msg = protocol.parse(text)
    if not _active(db, sender):
        return Outcome(msg.kind, 3, lines=[f"发件人 {sender} 不是状态库里登记的在用模块会话，拒收"])
    if msg.kind != "shared-change-request":
        return Outcome(msg.kind, 3, lines=[f"这不是【公共变更请求】（{msg.kind}）"])
    if not msg.ok:
        return Outcome(msg.kind, 3, lines=["消息不合格，请退回：" + "、".join(msg.problems)])
    doc = msg.contract()
    req_files = doc["changeRequest"]["files"]
    scope = _declared_scope(db, sender)          # crew-declared-scope: a subprocess, so outside the transaction
    with db.transaction(actor=sender) as tx:
        out = Outcome(msg.kind, 0)
        if any(e["actor"] == sender and e["data"].get("relayId") == relay_id for e in store.events(db)):
            out.lines.append(f"已记过：{sender} 的邮箱消息 #{relay_id}，没有重复记账")
            return out
        open_reqs = {k: v for k, v in tx.records("request").items() if v.get("state") == "open"}
        sessions = tx.records("session")
        module = _module_of(sessions, sender)
        # S27 (T133): the module's own older request on the same files, nothing landed yet, is replaced by this one
        replaced = {k: v for k, v in sorted(open_reqs.items(), key=lambda kv: int(kv[0]))
                    if _module_of(sessions, v["from"]) == module and not v.get("partial")
                    and set(req_files) & set(v["files"])}
        open_reqs = {k: v for k, v in open_reqs.items() if k not in replaced}
        hints = hints_for(req_files, {k: v["files"] for k, v in open_reqs.items()})
        inside = [f for f in req_files if scope is not None and scope.inside(f)]
        early = bool(inside) and len(inside) == len(req_files) and not any(h.startswith("conflict:") for h in hints)
        ticket = None
        if doc["fullyStopped"]:
            coord = next((k for k, v in tx.records("session").items()
                          if v.get("role") == "coordinator" and v.get("status") == "active"), "coordinator")
            ticket = tx.allocate_number()
            tx.put("ticket", str(ticket), {
                "state": "open", "from": sender, "relayId": relay_id, "text": text, "waitingFor": coord,
                "what": "公共变更请求的处理结果", "closedReason": None, "closedBy": None,
            }, action="opened", data={"relayId": relay_id})
        n = tx.allocate_number()
        for k, rec in replaced.items():
            tx.put("request", k, dict(rec, state="closed", closedReason="superseded", supersededBy=n),
                   action="superseded", data={"by": n, "relayId": relay_id})
            _close_ticket(tx, rec)
            out.closed.append(int(k))
        for k in (k for k, v in open_reqs.items() if set(req_files) & set(v["files"])):
            tx.put("request", k, dict(open_reqs[k], hints=open_reqs[k]["hints"] + [f"conflict:{n}"]),
                   action="hinted", data={"relayId": relay_id})
        tx.put("request", str(n), {
            "state": "open", "from": sender, "relayId": relay_id, "text": text, "files": req_files,
            "what": msg.fields.get("改什么", ""), "why": msg.fields.get("为什么", ""),
            "fullyStopped": doc["fullyStopped"], "hints": hints, "ticket": ticket,
            "closedReason": None, "commit": None, "answer": None,
            **({"declared": early} if scope is not None else {}),
            **({"declaredCommit": scope.approved_commit} if early else {}),
        }, action="created", data={"relayId": relay_id})
        out.number = n
        out.lines.append(f"已记为公共变更请求 C{n}" + (f"，等待记录 W{ticket}" if ticket else ""))
        if out.closed:
            out.lines.append("取代了 " + "、".join(f"C{k}" for k in out.closed) + f"（{module} 未落地的旧请求，文件重叠），"
                             "旧请求不再处理；告诉 " + "、".join(sorted({v["from"] for v in replaced.values()}))
                             + f"：以新请求 C{n} 为准")
        if hints:
            out.lines.append("提示：" + "、".join(hints))
        if scope is not None and not scope.usable:
            out.lines.append(f"声明不可用：{scope.reason}，照今天处理")
        elif inside and not early and len(inside) < len(req_files):
            out.lines.append(f"名单内：{'、'.join(inside)}；有名单外的文件，整条照今天处理")
        elif inside and not early:
            out.lines.append("名单内，但和别的请求改同一个文件：照今天处理")
        if early:
            out.lines.append(f"名单内：提前落地，不用问用户；用 change land C{n} --from-module")
        else:
            out.lines.append("要问用户" if _asks_user(hints) else "可由模块协调判断是否在已批准 Spec 范围内直接办")
        return out


def _declared_scope(db: store.Store, sender: str):
    """crew-declared-scope decision 3: the sender module's declaration, read in the integration checkout, or None
    when the switch is off."""
    from module_crew import declared
    if not declared.enabled(db):
        return None
    module = _module_of(store.records(db, "session"), sender)
    branch = (store.get(db, "config", "main") or {}).get("integrationBranch", "")
    checkout = probe._checkout_of(db.path.parent, branch) if branch else None
    if checkout is None:
        return declared.Declared(module, reason="找不到集成分支所在的 checkout")
    return declared.read(checkout, module)


def pending(db: store.Store) -> list[tuple[int, dict]]:
    return sorted(((int(k), v) for k, v in store.records(db, "request").items() if v.get("state") == "open"),
                  key=lambda kv: kv[0])


def _close_ticket(tx, rec: dict) -> None:
    if rec.get("ticket"):
        t = tx.get("ticket", str(rec["ticket"]))
        if t and t.get("state") == "open":
            tx.put("ticket", str(rec["ticket"]), dict(t, state="closed", closedReason=3), action="closed",
                   data={"reason": 3})


def _open_request(tx, number: int) -> dict:
    rec = tx.get("request", str(number))
    if rec is None:
        raise AnswerRefused(f"没有公共变更请求 C{number}")
    if rec.get("state") != "open":
        raise AnswerRefused(f"公共变更请求 C{number} 已关闭（{rec.get('closedReason')}）")
    return rec


def supersede(db: store.Store, number: int, by: int | None = None) -> dict:
    """S27 (T133) fallback: close a request a newer one replaced; no user words, nothing sent, the baseline untouched."""
    with db.transaction(actor="coordinator") as tx:
        rec = _open_request(tx, number)
        if by is not None and tx.get("request", str(by)) is None:
            raise AnswerRefused(f"没有公共变更请求 C{by}")
        tx.put("request", str(number), dict(rec, state="closed", closedReason="superseded", supersededBy=by),
               action="superseded", data={"by": by})
        _close_ticket(tx, rec)
    return rec


def answer(db: store.Store, number: int, original: str) -> Reply:
    """Decline a request with the user's words; the baseline is not touched."""
    with db.transaction(actor="coordinator") as tx:
        rec = _open_request(tx, number)
        answered_at = store.now()
        try:
            text = protocol.render_user_reply(item=number, original=original, answered_at=answered_at,
                                              source_relay_id=rec["relayId"], crew=True)
        except ValueError as exc:
            raise AnswerRefused(str(exc)) from exc
        body = tx.allocate_number()
        meta = tx.write_body(body, text)
        tx.put("request", str(number), dict(rec, state="closed", closedReason="declined",
                                            answer={"original": original, "answeredAt": answered_at, **store.source_field(), "body": body}),
               action="declined", data={"body": body})
        _close_ticket(tx, rec)
    return Reply(rec["from"], rec["relayId"], body, db.path / meta["path"])


@dataclass
class LandResult:
    code: int                                     # 0 done / 3 refused, nothing changed / 4 commit failed
    lines: list[str] = field(default_factory=list)
    commit: str | None = None
    sends: list[dict] = field(default_factory=list)   # {"to", "replyTo", "body", "path"}


def _changed_paths(checkout: Path) -> list[str]:
    """Every path git reports as changed or untracked, both sides of renames included."""
    raw = probe._git(checkout, "--no-optional-locks", "status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    entries = raw.split("\0")
    paths, i = [], 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        paths.append(path)
        if "R" in status or "C" in status:
            paths.append(entries[i])
            i += 1
    return paths


def _from_module(db: store.Store, checkout: Path, rec: dict, number: int) -> tuple[str | None, str | None]:
    """crew-declared-scope decision 4: (module commit, None) once every check passed and the listed files are taken
    from the requester's module branch into the integration checkout; (None, why) when refused, nothing touched."""
    from module_crew import declared
    if not rec.get("declared"):
        return None, f"C{number} 不是名单内的提前落地请求（change add 时没认成名单内），不能 --from-module"
    dirty = _changed_paths(checkout)
    if dirty:
        return None, "集成 checkout 落地前就有改动，没有取文件：" + "、".join(dirty)
    module = _module_of(store.records(db, "session"), rec["from"])
    commit = probe._git(checkout, "rev-parse", "--verify", "--quiet", f"refs/heads/{module}^{{commit}}").stdout.strip()
    if not commit:
        return None, f"找不到模块分支 {module}"
    for f in rec["files"]:
        if probe._git(checkout, "cat-file", "-e", f"{commit}:{f}").returncode != 0:
            return None, f"模块分支上没有 {f}（{commit[:7]}）；删除不能预先声明，照今天的做法处理"
    same = [f for f in rec["files"] if probe._git(checkout, "rev-parse", f"{commit}:{f}").stdout
            == probe._git(checkout, "rev-parse", f"HEAD:{f}").stdout]
    if same:
        return None, f"模块分支上这些文件和集成分支一样，没有可落地的：{'、'.join(same)}"
    scope = declared.read(checkout, module)
    if not scope.usable:
        return None, f"声明不可用：{scope.reason}；照今天的做法处理"
    outside = [f for f in rec["files"] if not scope.inside(f)]
    if outside:
        return None, "这些文件已不在名单内：" + "、".join(outside) + "；照今天的做法处理"
    took = probe._git(checkout, "checkout", commit, "--", *rec["files"])
    if took.returncode != 0:
        return None, f"从模块分支取文件失败：{(took.stderr or took.stdout).strip()[:200]}"
    return commit, None


def land(project: str | os.PathLike, number: int, original: str | None = None, partial: bool = False,
         from_module: bool = False) -> LandResult:
    """Commit the coordinator's edits for one request on the integration baseline and prepare the notices;
    with `from_module`, take the declared files from the requester's module branch first (crew-declared-scope)."""
    project = Path(project)
    db = store.open_store(project)
    rec = store.get(db, "request", str(number))
    if rec is None:
        return LandResult(3, [f"没有公共变更请求 C{number}"])
    if rec.get("state") != "open":
        return LandResult(3, [f"公共变更请求 C{number} 已关闭（{rec.get('closedReason')}）"])
    cfg = store.get(db, "config", "main") or {}
    checkout = probe._checkout_of(project, cfg.get("integrationBranch", "")) if cfg else None
    if checkout is None:
        return LandResult(3, ["找不到集成分支所在的 checkout"])
    module_commit = None
    if from_module:
        if partial:
            return LandResult(3, ["--from-module 不和 --partial 一起用"])
        module_commit, why = _from_module(db, checkout, rec, number)
        if why:
            return LandResult(3, [why])
    changed = _changed_paths(checkout)
    outside = [p for p in changed if p not in rec["files"]]
    if outside:
        return LandResult(3, ["集成 checkout 里有清单外的改动，没有提交：" + "、".join(outside)])
    if not changed:
        return LandResult(3, [f"清单里的文件都没有改动：{'、'.join(rec['files'])}"])
    done_before = {f for p in rec.get("partial") or [] for f in p["files"]}
    left = [p for p in rec["files"] if p not in changed and p not in done_before]
    if left and not partial:       # 0.10.2 (spec-guard trial, C42): a half-landed request must not be closed
        return LandResult(3, [f"公共变更请求 C{number} 清单里还有 {len(left)} 个文件没改：{'、'.join(left)}；没有提交",
                              "全部改完再 change land；确实要先落地已改的部分，请用户同意后加 --partial --original-file <原话文件>"])
    if left and not (original and original.strip()):
        return LandResult(3, ["部分落地要用户原话：请用户同意后加 --original-file <原话文件>"])
    probe._git(checkout, "add", "-A", "--", *changed)
    from module_crew import merge
    try:
        done = probe._git(checkout, "commit", "-q", "-m",
                          commits.message(f"公共变更请求 C{number}（{rec['from']}）{'提前落地' if module_commit else ''}："
                                          f"{rec['what'][:40]}", commits.prefix_of(db)),
                          timeout=merge.commit_timeout(cfg))
    except subprocess.TimeoutExpired as exc:
        return LandResult(4, [probe.timed_out("集成分支提交", exc), "已暂存的文件：" + "、".join(changed) + "（仍是暂存状态）",
                              f"这次没有提交，请求 C{number} 仍开着；确认没有 .git/index.lock、钩子进程已结束、"
                              "集成 checkout 里除清单文件外没有别的改动后，可以重试同一条 change land，不用先 unstage"])
    if done.returncode != 0:
        return LandResult(4, [commits.failure(checkout, done, "集成分支提交失败")] + commits.hook_lines(checkout, done)
                          + ["已暂存的文件：" + "、".join(changed)])
    commit = probe._git(checkout, "rev-parse", "HEAD").stdout.strip()
    from module_crew import unqueued
    unqueued.mark(db, checkout, "change-land")       # crew-unqueued-commits: module-crew's own commit
    result = LandResult(0, commit=commit)
    if left:
        result.lines.append(f"公共变更请求 C{number} 部分落地 {commit[:7]}，还剩 {'、'.join(left)}；请求保持打开，改完再 change land")
    else:
        result.lines.append(f"公共变更请求 C{number} 已在集成分支提交 {commit[:7]}")
    if module_commit:
        result.lines.append(f"从模块分支 {module_commit[:7]} 取的文件；提前落地，记入待汇总（change landed）")
    result.lines.append(probe.took_line(done, merge.commit_timeout(cfg)))
    if original is None and _asks_user(rec.get("hints", [])):
        result.lines.append("提醒：这条请求带「要问用户」提示，但没有记下用户原话")
    basis = (f"公共变更请求 C{number} 部分落地 {commit[:7]}（还剩 {'、'.join(left)}）" if left
             else f"公共变更请求 C{number} 已在集成分支提交 {commit[:7]}")
    todo = f"{sync.STEP}，跑完整检查后继续"
    with db.transaction(actor="coordinator") as tx:
        answer_rec = {"original": original, "answeredAt": store.now(), **store.source_field()} if original is not None else None
        if left:
            parts = list(rec.get("partial") or []) + [{"commit": commit, "files": changed, "answer": answer_rec}]
            tx.put("request", str(number), dict(rec, partial=parts), action="partly-landed",
                   data={"commit": commit, "left": left})
        else:
            early = {"fromModule": {"commit": module_commit}, "toldUser": False} if module_commit else {}
            tx.put("request", str(number), dict(rec, state="closed", closedReason="landed", commit=commit, answer=answer_rec,
                                                **early),
                   action="landed", data={"commit": commit, **({"fromModule": module_commit} if module_commit else {})})
            _close_ticket(tx, rec)
        skip = merge.no_sync(tx)               # same rule as merge run (0.9.3); the requester still gets its reply
        for name, sess in sorted(tx.records("session").items()):
            if sess.get("role") != "dev" or sess.get("status") != "active":
                continue
            if sess.get("module") in skip and name != rec["from"]:
                continue
            text = protocol.render_coordination_notice(kind="sync-baseline", basis=basis, todo=todo)
            reply_to = rec["relayId"] if name == rec["from"] else None
            if reply_to is not None:
                text = f"回复：#{reply_to}\n" + text
                if protocol.parse(text).reply_to != reply_to:
                    raise ValueError("回复行没有被读回")
            body = tx.allocate_number()
            meta = tx.write_body(body, text)
            result.sends.append({"to": name, "replyTo": reply_to, "body": body, "path": db.path / meta["path"]})
    return result
