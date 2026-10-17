"""Parse and render session-protocol v1.1 messages (see spec/crew-protocol.md).

Pure functions only: no file, git or agent-relay access. Field names, tags and
problem codes follow the contract text in session-protocol PROTOCOL.md.
Writing is lenient (either colon width, values spanning lines); judging is
strict (a required field that cannot be found is a problem, never guessed).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CONTRACT_VERSION = "1.1"

KIND_TAGS = {
    "等待用户": "wait-user",
    "用户答复": "user-reply",
    "等待其他会话": "wait-session",
    "已恢复": "resumed",
    "撤回": "withdraw",
    "审查结论": "review-conclusion",
    "答复告知": "answer-notice",
    "交审": "review-request",
    "公共变更请求": "shared-change-request",
    "协调通知": "coordination-notice",
}
UNSUPPORTED = ("review-conclusion", "answer-notice")

# Field names each kind knows (contract section 3).
FIELDS = {
    "wait-user": ("来自", "项目", "要你决定", "要点", "架构审查", "选项与我的建议", "你该回",
                  "是否完全停住", "适用会话", "各线范围"),
    "user-reply": ("事项", "用户原话", "选项原文", "适用于你的范围", "答复时间", "原事项全文"),
    "wait-session": ("在等谁", "等什么"),
    "resumed": (),
    "withdraw": ("事项", "原因"),
    "review-conclusion": ("审查编号", "节点", "模块", "送审方", "结论", "来自", "要点"),
    "answer-notice": ("事项", "用户原话", "答复时间", "说明"),
    "review-request": ("模块", "节点", "文件", "要点", "改动统计", "越界检查"),
    "shared-change-request": ("来自", "文件", "改什么", "为什么", "是否完全停住"),
    "coordination-notice": ("类型", "依据", "要你做什么"),
    "unknown": (),
}
TERMINAL = {"原事项全文"}  # takes every remaining line

_TAG_RE = re.compile(r"【([^】]*)】")
_COLON = "[：:]"
_END_RE = re.compile(rf"^结束\s*{_COLON}\s*(.*)$")
_REPLY_RE = re.compile(rf"^回复\s*{_COLON}\s*#\s*(\d+)\s*$")
_NUM_RE = re.compile(r"#\s*(\d+)")


@dataclass(frozen=True)
class End:
    present: bool = False
    items: tuple[int, ...] = ()
    none: bool = False
    unnumbered_reason: str | None = None


@dataclass(frozen=True)
class Message:
    kind: str
    supported: bool
    problems: tuple[str, ...]
    hints: tuple[str, ...]
    fields: dict[str, str]
    end: End = End()
    reply_to: int | None = None
    markers: tuple[tuple[str, int], ...] = ()
    item: int | None = None
    extra: dict = field(default_factory=dict)  # type-specific contract keys

    @property
    def ok(self) -> bool:
        return not self.problems

    def contract(self) -> dict:
        """The parse result in the shape of contract section 12."""
        doc = {
            "type": self.kind,
            "valid": self.ok,
            "replyTo": self.reply_to,
            "end": {"present": self.end.present, "items": list(self.end.items), "none": self.end.none,
                    "unnumberedReason": self.end.unnumbered_reason},
            "markers": [{"kind": k, "item": n} for k, n in self.markers],
            "item": self.item,
            "fields": dict(self.fields),
            "options": [],
            "recommended": None,
            "suggestedReply": None,
            "fullyStopped": None,
            "linesInScope": [],
            "scopes": {},
            "reviewLine": {"status": "absent", "adviceCount": None, "ref": None},
            "conclusion": None,
            "problems": list(self.problems),
            "hints": list(self.hints),
        }
        doc.update(self.extra)
        return doc


def _parse_end(value: str) -> End:
    value = value.strip()
    m = re.match(r"^无编号\s*[（(](.*)[）)]\s*$", value)
    if m:
        return End(present=True, unnumbered_reason=m.group(1).strip())
    if value == "无":
        return End(present=True, none=True)
    return End(present=True, items=tuple(int(x) for x in _NUM_RE.findall(value)))


def _split(text: str) -> tuple[list[str], End, int | None, list[str]]:
    """Leading lines (tags, 结束, 回复) first, then the field area."""
    lines = text.replace("\r\n", "\n").split("\n")
    tags: list[str] = []
    end = End()
    reply_to = None
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        found = _TAG_RE.findall(line)
        if found and not _TAG_RE.sub("", line).strip():
            tags += found
        elif _END_RE.match(line):
            end = _parse_end(_END_RE.match(line).group(1))
        elif _REPLY_RE.match(line):
            reply_to = int(_REPLY_RE.match(line).group(1))
        else:
            break
        i += 1
    return tags, end, reply_to, lines[i:]


def _field_re(name: str) -> re.Pattern:
    if name == "选项原文":
        return re.compile(rf"^选项\s*[A-Z]\s*原文\s*{_COLON}\s*(.*)$")
    return re.compile(rf"^{re.escape(name)}\s*{_COLON}\s*(.*)$")


def _fields(kind: str, body: list[str]) -> dict[str, str]:
    patterns = [(name, _field_re(name)) for name in FIELDS[kind]]
    values: dict[str, list[str]] = {}
    current = None
    for line in body:
        if current in TERMINAL:
            values[current].append(line)
            continue
        for name, pattern in patterns:
            m = pattern.match(line.strip())
            if m and name not in values:
                current = name
                values[name] = [m.group(1)] if m.group(1) else []
                break
        else:
            if current is not None:
                values[current].append(line)
    out = {}
    for name, chunk in values.items():
        while chunk and not chunk[-1].strip():
            chunk.pop()
        out[name] = "\n".join(chunk)
    return out


def _number(value: str | None) -> int | None:
    m = _NUM_RE.search(value or "")
    return int(m.group(1)) if m else None


def _require(fields: dict, names, problems: list[str]) -> None:
    for name in names:
        if not fields.get(name, "").strip():
            problems.append(f"missing-field:{name}")


def parse(text: str) -> Message:
    tags, end, reply_to, body = _split(text or "")
    kind = "unknown"
    markers: list[tuple[str, int]] = []
    problems: list[str] = []
    for tag in (t.strip() for t in tags):
        if tag in KIND_TAGS and kind == "unknown":
            kind = KIND_TAGS[tag]
        elif tag.startswith("取代"):
            n = _number(tag)
            if n:
                markers.append(("supersede", n))
            else:
                problems.append("missing-field:取代编号")
        elif tag.startswith("与") and tag.endswith("并行"):
            n = _number(tag)
            if n:
                markers.append(("parallel", n))
            else:
                problems.append("missing-field:并行编号")
    fields = _fields(kind, body)
    hints: list[str] = []
    extra: dict = {}
    item = None

    if kind == "unknown":
        problems.append("unknown-kind")
    elif kind == "wait-session":
        if not end.present:
            problems.append("missing-end")
        _require(fields, ("在等谁", "等什么"), problems)
    elif kind == "resumed":
        if not (end.items or end.unnumbered_reason):
            problems.append("missing-end")
    elif kind == "withdraw":
        item = _number(fields.get("事项"))
        if item is None:
            problems.append("missing-field:事项")
    elif kind == "user-reply":
        item = _number(fields.get("事项"))
        if item is None:
            problems.append("missing-field:事项")
        _require(fields, ("用户原话", "答复时间"), problems)
        if "多线事项" in fields.get("事项", ""):
            _require(fields, ("适用于你的范围", "原事项全文"), problems)

    return Message(kind=kind, supported=kind not in UNSUPPORTED, problems=tuple(problems), hints=tuple(hints),
                   fields=fields, end=end, reply_to=reply_to, markers=tuple(markers), item=item, extra=extra)
