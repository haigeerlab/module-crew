"""Project state store under <git-common-dir>/module-crew/ (see spec/crew-store.md).

The append-only event log is the only source of truth. Every write appends an
event carrying the full record after the change, so each snapshot under state/
is a cache that can always be recomputed from the log.
"""

from __future__ import annotations

import contextlib
import contextvars
import fcntl
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

VERSION = 1
KINDS = ("config", "session", "item", "request", "ticket", "body")
NUMBERED = ("item", "request", "ticket", "body")
ROLES = ("coordinator", "dev")
HOSTS = ("claude-desktop", "codex-desktop")   # coordinators are Claude desktop only (crew-codex-host)
SESSION_STATUSES = ("active", "retired")
_ACTION_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_NUMBER_RE = re.compile(r"^[1-9][0-9]*$")


class StoreError(Exception):
    """Base class for every store failure."""


class NotInRepo(StoreError):
    """The directory is not inside a git repository."""


class StoreNotFound(StoreError):
    """The repository has no initialised store."""


class StoreCorrupt(StoreError):
    """A store file exists but cannot be trusted; keep it as evidence."""


class InvalidRecord(StoreError):
    """A write breaks the generic record rules; nothing was written."""


class InvalidSession(InvalidRecord):
    """A session entry breaks the session rules; nothing was written."""


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")


def store_path(cwd: str | os.PathLike | None = None) -> Path:
    """Locate <git-common-dir>/module-crew for the checkout containing cwd."""
    cwd = Path(cwd) if cwd is not None else Path.cwd()
    try:
        out = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                             capture_output=True, text=True)
    except OSError as exc:
        raise NotInRepo(f"无法运行 git：{exc}") from exc
    if out.returncode != 0 or not out.stdout.strip():
        raise NotInRepo(f"{cwd} 不在 git 仓库里")
    return Path(out.stdout.strip()) / "module-crew"


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _dump(doc: dict) -> bytes:
    return (json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _set_aside(path: Path, tag: str) -> Path:
    """Rename a file out of the way without deleting it."""
    target = path.with_name(f"{path.name}.{tag}-{_stamp()}")
    n = 1
    while target.exists():
        n += 1
        target = path.with_name(f"{path.name}.{tag}-{_stamp()}-{n}")
    os.replace(path, target)
    return target


# ---------------------------------------------------------------- log

class _Log:
    """Parsed view of events.jsonl."""

    def __init__(self, events: list[dict], warnings: list[str], bad_lines: int, ends_with_newline: bool):
        self.events = events
        self.warnings = warnings
        self.bad_lines = bad_lines
        self.ends_with_newline = ends_with_newline

    @property
    def max_seq(self) -> int:
        return max((e["seq"] for e in self.events), default=0)

    @property
    def max_number(self) -> int:
        return max((int(e["key"]) for e in self.events
                    if e["type"].split(".")[0] in NUMBERED and _NUMBER_RE.match(e["key"])), default=0)


def _valid_event(doc) -> bool:
    if not isinstance(doc, dict) or doc.get("v") != VERSION:
        return False
    if not isinstance(doc.get("seq"), int) or not isinstance(doc.get("key"), str):
        return False
    kind, _, action = str(doc.get("type", "")).partition(".")
    data = doc.get("data")
    return (kind in KINDS and bool(_ACTION_RE.match(action)) and isinstance(data, dict)
            and isinstance(data.get("record"), dict))


def _scan_log(path: Path) -> _Log:
    raw = path.read_bytes() if path.exists() else b""
    lines = raw.split(b"\n")
    ends_nl = raw == b"" or raw.endswith(b"\n")
    if ends_nl:
        lines = lines[:-1]
    events, warnings, bad = [], [], 0
    for i, line in enumerate(lines, start=1):
        try:
            doc = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            doc = None
        if _valid_event(doc):
            events.append(doc)
            continue
        bad += 1
        last = i == len(lines) and not ends_nl
        warnings.append(f"事件日志第 {i} 行{'是末尾半行' if last else '无法解析或版本不认识'}，已跳过")
    events.sort(key=lambda e: e["seq"])
    return _Log(events, warnings, bad, ends_nl)


def _fold(events: list[dict], kind: str, base: dict | None = None, after: int = 0) -> dict:
    records = dict(base or {})
    for e in events:
        if e["seq"] > after and e["type"].split(".")[0] == kind:
            records[e["key"]] = e["data"]["record"]
    return records


# ---------------------------------------------------------------- snapshots

def _read_snapshot(path: Path) -> tuple[str, dict | None]:
    """Return (status, doc): status is ok / missing / corrupt."""
    if not path.exists():
        return "missing", None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "corrupt", None
    if (not isinstance(doc, dict) or doc.get("version") != VERSION or not isinstance(doc.get("lastSeq"), int)
            or not isinstance(doc.get("records"), dict)):
        return "corrupt", None
    return "ok", doc


class _KindView:
    """Current records of one kind, plus how its snapshot compares with the log."""

    def __init__(self, records: dict, status: str, lag: int, last_seq: int):
        self.records = records
        self.status = status  # ok / lag / missing / corrupt
        self.lag = lag
        self.last_seq = last_seq


def _view(path: Path, log: _Log, kind: str) -> _KindView:
    kind_events = [e for e in log.events if e["type"].split(".")[0] == kind]
    last_seq = max((e["seq"] for e in kind_events), default=0)
    status, doc = _read_snapshot(path / "state" / f"{kind}.json")
    if status == "ok" and doc["lastSeq"] > log.max_seq:
        status = "corrupt"
    if status != "ok":
        if status == "missing" and not kind_events:
            return _KindView({}, "ok", 0, 0)
        return _KindView(_fold(kind_events, kind), status, len(kind_events), last_seq)
    lag = sum(1 for e in kind_events if e["seq"] > doc["lastSeq"])
    records = _fold(kind_events, kind, doc["records"], doc["lastSeq"])
    return _KindView(records, "lag" if lag else "ok", lag, last_seq)


def _view_warning(kind: str, v: _KindView) -> str | None:
    if v.status == "lag":
        return f"快照落后于日志 {v.lag} 条：{kind}"
    if v.status == "missing":
        return f"快照缺失，已从日志重算：{kind}"
    if v.status == "corrupt":
        return f"快照损坏，已从日志重算：state/{kind}.json"
    return None


# ---------------------------------------------------------------- store

def _check_meta(path: Path) -> None:
    meta = path / "meta.json"
    if not meta.exists():
        raise StoreNotFound(f"还没有建状态库：{path}（先运行 module-crew store init）")
    try:
        doc = json.loads(meta.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StoreCorrupt(f"无法解析：{meta}") from exc
    if not isinstance(doc, dict) or doc.get("version") != VERSION:
        raise StoreCorrupt(f"版本不认识：{meta}")


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.warnings: list[str] = []

    def transaction(self, actor: str) -> "Transaction":
        return Transaction(self, actor)


def open_store(cwd: str | os.PathLike | None = None) -> Store:
    path = store_path(cwd)
    _check_meta(path)
    return Store(path)


def init_store(cwd: str | os.PathLike | None = None) -> tuple[Store, bool]:
    """Create the store; an existing store is left byte-for-byte untouched."""
    path = store_path(cwd)
    if (path / "meta.json").exists():
        return open_store(cwd), False
    for d in (path, path / "state", path / "bodies"):
        d.mkdir(mode=0o700, exist_ok=True)
        os.chmod(d, 0o700)
    for name in ("events.jsonl", ".lock"):
        if not (path / name).exists():
            _atomic_write_bytes(path / name, b"")
    _atomic_write_bytes(path / "meta.json", _dump({"version": VERSION, "createdAt": now()}))
    return Store(path), True


# ---------------------------------------------------------------- reads (no lock)

def _read_view(db: Store, kind: str) -> _KindView:
    if kind not in KINDS:
        raise InvalidRecord(f"不认识的记录种类：{kind}")
    _check_meta(db.path)
    log = _scan_log(db.path / "events.jsonl")
    v = _view(db.path, log, kind)
    db.warnings = list(log.warnings)
    w = _view_warning(kind, v)
    if w:
        db.warnings.append(w)
    return v


def get(db: Store, kind: str, key: str) -> dict | None:
    return _read_view(db, kind).records.get(key)


def records(db: Store, kind: str) -> dict:
    return dict(_read_view(db, kind).records)


def events(db: Store, key: str | None = None, kind: str | None = None) -> list[dict]:
    _check_meta(db.path)
    log = _scan_log(db.path / "events.jsonl")
    db.warnings = list(log.warnings)
    return [e for e in log.events
            if (key is None or e["key"] == key) and (kind is None or e["type"].split(".")[0] == kind)]


def read_body(db: Store, number: int) -> str | None:
    rec = get(db, "body", str(number))
    if rec is None:
        return None
    path = db.path / rec["path"]
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise StoreCorrupt(f"正文文件读不到：{path}") from exc
    if hashlib.sha256(data).hexdigest() != rec["sha256"] or len(data) != rec["bytes"]:
        raise StoreCorrupt(f"正文指纹不符：{path}")
    return data.decode("utf-8")


# ---------------------------------------------------------------- writes

def _validate_session(key: str, rec: dict, others: dict) -> None:
    def bad(msg: str) -> InvalidSession:
        return InvalidSession(f"会话登记不合法（{key}）：{msg}")

    role, host, status = rec.get("role"), rec.get("host"), rec.get("status")
    if role not in ROLES:
        raise bad(f"role 只能是 {'／'.join(ROLES)}")
    if host not in HOSTS:
        raise bad(f"host 只能是 {'／'.join(HOSTS)}")
    if role == "coordinator" and host != "claude-desktop":
        raise bad("模块协调只能是 claude-desktop")
    if status not in SESSION_STATUSES:
        raise bad(f"status 只能是 {'／'.join(SESSION_STATUSES)}")
    if role == "dev":
        module, worktree = rec.get("module"), rec.get("worktree")
        if not isinstance(module, str) or not module:
            raise bad("dev 必填 module")
        if not isinstance(worktree, str) or not os.path.isabs(worktree):
            raise bad("dev 必填 worktree，且必须是绝对路径")
    if status != "active":
        return
    for other_key, other in others.items():
        if other_key == key or other.get("status") != "active" or other.get("role") != role:
            continue
        if role == "coordinator":
            raise bad(f"已有在用的模块协调 {other_key}")
        if other.get("module") == rec.get("module"):
            raise bad(f"模块 {rec.get('module')} 已有在用的模块会话 {other_key}")


_SOURCE: contextvars.ContextVar[dict | None] = contextvars.ContextVar("approval_source", default=None)


@contextlib.contextmanager
def approval_source(source: dict | None):
    """While active, every event written carries data.source, and answers record it (crew-hub-bridge)."""
    token = _SOURCE.set(source)
    try:
        yield
    finally:
        _SOURCE.reset(token)


def source_field() -> dict:
    """{"source": ...} to merge into an answer record, or {} when no approval source is active."""
    src = _SOURCE.get()
    return {"source": src} if src else {}


class Transaction:
    """Holds the store lock; on a clean exit writes bodies, then events, then snapshots."""

    def __init__(self, db: Store, actor: str):
        self.db = db
        self.actor = actor
        self.warnings: list[str] = []
        self._lock_fd: int | None = None

    def __enter__(self) -> "Transaction":
        path = self.db.path
        self._lock_fd = os.open(path / ".lock", os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(self._lock_fd, fcntl.LOCK_EX)
        try:
            _check_meta(path)
            self._log = _scan_log(path / "events.jsonl")
            self._views = {k: _view(path, self._log, k) for k in KINDS}
        except BaseException:
            self._release()
            raise
        self.warnings = list(self._log.warnings)
        self.warnings += [w for k, v in self._views.items() if (w := _view_warning(k, v))]
        self._next_seq = self._log.max_seq + 1
        self._next_number = self._log.max_number + 1
        self._pending: list[dict] = []
        self._bodies: dict[int, bytes] = {}
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            if exc_type is None and self._pending:
                self._commit()
        finally:
            self._release()
        return False

    def _release(self) -> None:
        if self._lock_fd is not None:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            self._lock_fd = None

    # -- reads inside the transaction see pending writes

    def get(self, kind: str, key: str) -> dict | None:
        return self.records(kind).get(key)

    def records(self, kind: str) -> dict:
        if kind not in KINDS:
            raise InvalidRecord(f"不认识的记录种类：{kind}")
        return dict(self._views[kind].records)

    def allocate_number(self) -> int:
        n = self._next_number
        self._next_number += 1
        return n

    def put(self, kind: str, key: str, record: dict, action: str, data: dict | None = None) -> dict:
        if kind not in KINDS:
            raise InvalidRecord(f"不认识的记录种类：{kind}")
        if not isinstance(action, str) or not _ACTION_RE.match(action):
            raise InvalidRecord(f"动作只能用小写字母、数字、连字符：{action!r}")
        if not isinstance(record, dict):
            raise InvalidRecord("record 必须是 JSON 对象")
        if not isinstance(key, str) or not key:
            raise InvalidRecord("key 必须是非空字符串")
        if kind in NUMBERED and not _NUMBER_RE.match(key):
            raise InvalidRecord(f"{kind} 的键必须是编号：{key!r}")
        if kind == "config" and key != "main":
            raise InvalidRecord("config 的键固定为 main")
        if data is not None and (not isinstance(data, dict) or "record" in data):
            raise InvalidRecord("data 必须是对象，且不能含 record")
        if kind == "session":
            _validate_session(key, record, self._views["session"].records)
        try:
            body = json.loads(json.dumps(record, ensure_ascii=False))
        except (TypeError, ValueError) as exc:
            raise InvalidRecord("record 不能序列化为 JSON") from exc
        extra = {"source": _SOURCE.get()} if _SOURCE.get() else {}
        event = {"v": VERSION, "seq": self._next_seq, "at": now(), "type": f"{kind}.{action}",
                 "key": key, "actor": self.actor, "data": {**extra, **(data or {}), "record": body}}
        self._next_seq += 1
        if kind in NUMBERED:
            self._next_number = max(self._next_number, int(key) + 1)
        self._pending.append(event)
        view = self._views[kind]
        view.records[key] = body
        view.last_seq = event["seq"]
        return event

    def write_body(self, number: int, text: str) -> dict:
        key = str(number)
        if not _NUMBER_RE.match(key):
            raise InvalidRecord(f"正文编号不合法：{number!r}")
        if key in self._views["body"].records:
            raise InvalidRecord(f"正文 C{number} 已存在，正文不可修改")
        data = text.encode("utf-8")
        rec = {"path": f"bodies/{number}.txt", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        self.put("body", key, rec, action="written")
        self._bodies[number] = data
        return dict(rec)

    def _commit(self) -> None:
        path = self.db.path
        for number, data in self._bodies.items():
            target = path / "bodies" / f"{number}.txt"
            if target.exists():
                _set_aside(target, "orphan")
            _atomic_write_bytes(target, data)
        log_path = path / "events.jsonl"
        payload = b"".join((json.dumps(e, ensure_ascii=False) + "\n").encode("utf-8") for e in self._pending)
        if not self._log.ends_with_newline:
            payload = b"\n" + payload
        fd = os.open(log_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        written = {e["type"].split(".")[0] for e in self._pending}
        for kind, view in self._views.items():
            if kind not in written and view.status == "ok":
                continue
            snap = path / "state" / f"{kind}.json"
            if view.status == "corrupt" and snap.exists():
                _set_aside(snap, "corrupt")
            _atomic_write_bytes(snap, _dump({"version": VERSION, "lastSeq": view.last_seq, "records": view.records}))


# ---------------------------------------------------------------- check

def check(db: Store) -> dict:
    """Read-only health report; never writes."""
    _check_meta(db.path)
    log = _scan_log(db.path / "events.jsonl")
    views = {k: _view(db.path, log, k) for k in KINDS}
    problems = list(log.warnings)
    warnings = []
    for kind, v in views.items():
        w = _view_warning(kind, v)
        if w:
            (problems if v.status == "corrupt" else warnings).append(w)
    body_files = set()
    for rec in views["body"].records.values():
        p = db.path / rec.get("path", "")
        body_files.add(p.name)
        try:
            data = p.read_bytes()
        except OSError:
            problems.append(f"正文文件读不到：{rec.get('path')}")
            continue
        if hashlib.sha256(data).hexdigest() != rec.get("sha256") or len(data) != rec.get("bytes"):
            problems.append(f"正文指纹不符：{rec.get('path')}")
    bodies_dir = db.path / "bodies"
    if bodies_dir.is_dir():
        for p in sorted(bodies_dir.glob("*.txt")):
            if p.name not in body_files:
                warnings.append(f"孤立正文（没有事件指向）：bodies/{p.name}")
    return {
        "path": str(db.path),
        "version": VERSION,
        "events": len(log.events),
        "nextNumber": log.max_number + 1,
        "counts": {k: len(v.records) for k, v in views.items()},
        "lag": {k: v.lag for k, v in views.items() if v.status == "lag"},
        "problems": problems,
        "warnings": warnings,
    }
