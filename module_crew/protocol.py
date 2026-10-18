"""Parse and render session-protocol v1.9 messages (see spec/crew-protocol.md).

Pure functions only: no file, git or agent-relay access. Field names, tags and
problem codes follow the contract text in session-protocol PROTOCOL.md.
Writing is lenient (either colon width, values spanning lines); judging is
strict (a required field that cannot be found is a problem, never guessed).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CONTRACT_VERSION = "1.9"

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
    "负责人转交": "owner-handoff",
}
UNSUPPORTED = ("answer-notice",)

# Field names each kind knows (contract section 3).
FIELDS = {
    "wait-user": ("来自", "项目", "要你决定", "要点", "架构审查", "选项与我的建议", "你该回",
                  "是否完全停住", "适用会话", "各线范围"),
    "user-reply": ("事项", "转自", "用户原话", "选项原文", "适用于你的范围", "答复时间", "转交范围", "原事项全文"),
    "owner-handoff": ("事项", "来自", "用户原话", "答复时间", "转交范围"),
    "wait-session": ("在等谁", "等什么"),
    "resumed": (),
    "withdraw": ("事项", "原因"),
    "review-conclusion": ("审查编号", "节点", "模块", "送审方", "结论", "来自", "要点", "须修改", "待用户决定"),
    "answer-notice": ("事项", "用户原话", "答复时间", "说明"),
    "review-request": ("模块", "节点", "文件", "要点", "改动统计", "越界检查", "不同意"),
    "shared-change-request": ("来自", "文件", "改什么", "为什么", "是否完全停住"),
    "coordination-notice": ("类型", "原因", "依据", "轮次", "要你做什么"),
    "unknown": (),
}
TERMINAL = {"原事项全文"}  # takes every remaining line

_TAG_RE = re.compile(r"【([^】]*)】")
_COLON = "[：:]"
_END_RE = re.compile(rf"^结束\s*{_COLON}\s*(.*)$")
_REPLY_RE = re.compile(rf"^回复\s*{_COLON}\s*#\s*(\d+)\s*$")
_NUM_RE = re.compile(r"#\s*(\d+)")
_OPTION_RE = re.compile(r"^(推荐\s*)?([A-Z])\s*[：:.、)）]\s*(.*)$")
_RECOMMEND_RE = re.compile(rf"^推荐\s*{_COLON}?\s*([A-Z])\s*$")
_CONSEQUENCE_RE = re.compile(rf"^选了会怎样\s*{_COLON}\s*(.*)$")
_SCOPE_RE = re.compile(rf"^[-*•·]?\s*([^\s：:]+)\s*{_COLON}\s*(.*)$")
_SESSION_SEP = re.compile(r"[、,，+＋\s]+")
_FILE_LINE_RE = re.compile(r"^(?:-\s+)?(\S.*?)\s+(sha256:[0-9a-f]{12,64})$")
REVIEW_NODES = {"Spec": "spec", "Plan": "plan", "接口提案": "interface", "最终验收": "final"}
NOTICE_KINDS = {"开工": "start", "同步基线": "sync-baseline", "接口变更": "interface-change", "收尾": "wrap-up", "退回": "returned",
                "挂起": "suspend", "恢复": "resume", "返工": "rework", "撤销批准": "revoke"}
# notices whose 依据 must cite the user's approval: a hub item #N, or the coordinator's own approval C<N> (v2.0 draft)
NEED_REF = ("start", "returned", "suspend", "resume", "revoke")
_CREW_RE = re.compile(r"(?<![A-Za-z])C\s*(\d+)")
_REVIEW_ID_RE = re.compile(r"(?<![A-Za-z])R-?\d+")
_VERDICT_FORMS = (
    (re.compile(r"^通过$"), "passed"),
    (re.compile(r"^通过[，,]\s*附建议(\d+)条"), "passed-with-advice"),
    (re.compile(r"^有须修改项(?:(\d+)条)?$"), "changes-required"),
)
_DECISION_HEAD_RE = re.compile(rf"^(D\d+)\s*{_COLON}\s*(.+)$")
_DECISION_OPTION_RE = re.compile(r"^([A-Z])\s*[.．、：:)）]\s*(.+)$")
_DECISION_LEAN_RE = re.compile(rf"^倾向\s*{_COLON}\s*([A-Z])")
_DISAGREE_RE = re.compile(rf"^(#?[A-Za-z]+-?\d+)\s*{_COLON}\s*(.+)$")
_THIN_WORDS = ("详见", "已明确", "同上")
# v1.6 「转自」: only these two wordings (contract section 3)
_RELAY_HUB_RE = re.compile(r"^收件枢纽\s*[，,]\s*消息\s*#\s*(\d+)$")
_RELAY_OWNER_RE = re.compile(r"^(.+?)（负责人转交）\s*[，,]\s*消息\s*#\s*(\d+)$")
_ORIGINALS_RE = re.compile(r"原消息\s*((?:#\s*\d+\s*[、,，]?\s*)+)")


def _originals(value: str | None) -> list[int]:
    m = _ORIGINALS_RE.search(value or "")
    return [int(x) for x in _NUM_RE.findall(m.group(1))] if m else []
# 架构审查 wordings (decision-inbox 0.0.7 behaviour carried into v1.0); anything else is "unrecognized".
_REVIEW_REF_RE = re.compile(r"（\s*(#?[A-Za-z]*-?\d+)\s*）$")
_REVIEW_FORMS = (
    (re.compile(r"^通过$"), "passed"),
    (re.compile(r"^通过，附建议(\d+)条(（.*）)?$"), "passed-with-advice"),
    (re.compile(r"^进行中，请勿先批$"), "in-progress"),
    (re.compile(r"^不适用（不属于审查节点）$"), "not-applicable"),
    (re.compile(r"^用户豁免$"), "waived"),
)


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


def _options(block: str) -> tuple[list[dict], str | None]:
    """Split 选项与我的建议 into lettered options; never merge or complete them."""
    options: list[dict] = []
    recommended = None
    for raw in block.split("\n"):
        line = raw.strip()
        if not line:
            continue
        rec, opt, cons = _RECOMMEND_RE.match(line), _OPTION_RE.match(line), _CONSEQUENCE_RE.match(line)
        if rec:
            recommended = rec.group(1)
        elif opt:
            options.append({"letter": opt.group(2), "text": [opt.group(3)], "consequence": None})
            if opt.group(1):
                recommended = opt.group(2)
        elif cons and options:
            options[-1]["consequence"] = [cons.group(1)]
        elif options:
            (options[-1]["consequence"] or options[-1]["text"]).append(line)
    return [{"letter": o["letter"], "text": "\n".join(o["text"]).strip(),
             "consequence": "\n".join(o["consequence"]).strip() if o["consequence"] else None}
            for o in options], recommended


def _scopes(block: str) -> dict[str, str]:
    """各线范围: one 「会话：范围」 entry per line; later lines continue it without their indent."""
    scopes: dict[str, list[str]] = {}
    last = None
    for raw in block.split("\n"):
        line = raw.strip()
        if not line:
            continue
        m = _SCOPE_RE.match(line)
        if m:
            last = m.group(1)
            scopes.setdefault(last, []).append(m.group(2).strip())
        elif last is not None:
            scopes[last].append(line)
    return {k: "\n".join(v) for k, v in scopes.items()}


def _review_line(raw: str | None) -> dict:
    if raw is None:
        return {"status": "absent", "adviceCount": None, "ref": None}
    value = raw.strip().replace(",", "，").replace("(", "（").replace(")", "）")
    ref = None
    m = _REVIEW_REF_RE.search(value)
    if m:
        ref, value = m.group(1), value[:m.start()].rstrip()
    for pattern, status in _REVIEW_FORMS:
        hit = pattern.match(value)
        if hit:
            advice = int(hit.group(1)) if status == "passed-with-advice" else None
            return {"status": status, "adviceCount": advice, "ref": ref}
    return {"status": "unrecognized", "adviceCount": None, "ref": None}


def _brief_thin(value: str | None) -> bool:
    lines = [x for x in (value or "").split("\n") if x.strip()]
    return len(lines) < 2 or any(w in (value or "") for w in _THIN_WORDS)


def _stop_flag(fields: dict, problems: list[str]) -> bool | None:
    flag = fields.get("是否完全停住", "").strip()
    if not flag:
        problems.append("missing-field:是否完全停住")
        return None
    if flag not in ("是", "否"):
        problems.append("bad-stop-flag")
        return None
    return flag == "是"


def _lines(block: str | None) -> list[str]:
    """Non-blank lines of a list field, stripped, with an optional leading 「- 」 removed."""
    out = []
    for raw in (block or "").split("\n"):
        line = raw.strip()
        if line.startswith("- "):
            line = line[2:].strip()
        if line:
            out.append(line)
    return out


def _require(fields: dict, names, problems: list[str]) -> None:
    for name in names:
        if not fields.get(name, "").strip():
            problems.append(f"missing-field:{name}")


def _numbered(block: str | None) -> list[str]:
    """「1. …」「2. …」 items of 须修改; a line without a number continues the previous item."""
    items: list[str] = []
    for line in _lines(block):
        m = re.match(r"^\d+\s*[.．、)）]\s*(.*)$", line)
        if m:
            items.append(m.group(1).strip())
        elif items:
            items[-1] += "\n" + line
        else:
            items.append(line)
    return items


def _decisions(block: str) -> list[dict] | None:
    """待用户决定: 「D1：问题」 then lettered options and 「倾向：X」; None when any item is malformed."""
    out: list[dict] = []
    for line in _lines(block):
        head, opt, lean = _DECISION_HEAD_RE.match(line), _DECISION_OPTION_RE.match(line), _DECISION_LEAN_RE.match(line)
        if head:
            out.append({"id": head.group(1), "question": head.group(2).strip(), "options": [], "lean": None})
        elif not out:
            return None
        elif lean:
            out[-1]["lean"] = lean.group(1)
        elif opt:
            out[-1]["options"].append({"letter": opt.group(1), "text": opt.group(2).strip()})
        else:
            return None
    if not out or any(len(d["options"]) < 2 or d["lean"] not in {o["letter"] for o in d["options"]} for d in out):
        return None
    return out


def _conclusion(fields: dict, problems: list[str], hints: list[str]) -> dict | None:
    _require(fields, ("审查编号", "节点", "送审方", "结论"), problems)
    raw_node = fields.get("节点", "").strip()
    node = REVIEW_NODES.get(raw_node)
    if raw_node and node is None:
        problems.append("bad-node")
    raw = fields.get("结论", "").strip()
    verdict, number = None, None
    for pattern, code in _VERDICT_FORMS:
        m = pattern.match(raw)
        if m:
            verdict, number = code, (int(m.group(1)) if m.groups() and m.group(1) else None)
            break
    if raw and verdict is None:
        problems.append("bad-verdict")
    out = {"ref": fields.get("审查编号", "").strip() or None, "node": node,
           "submitter": fields.get("送审方", "").strip() or None, "verdict": verdict,
           "adviceCount": number if verdict == "passed-with-advice" else None,
           "module": fields.get("模块", "").strip() or None}
    if verdict == "changes-required" and (number is not None or "须修改" in fields):
        changes = _numbered(fields.get("须修改"))
        if not changes:
            problems.append("missing-field:须修改")
        elif number is None:
            hints.append("change-count-missing")
        elif number != len(changes):
            problems.append("change-count-mismatch")
        out.update(changeCount=number, changes=changes)
    if "待用户决定" in fields:
        decisions = _decisions(fields["待用户决定"])
        if decisions is None:
            problems.append("bad-decision-item")
        else:
            out["decisions"] = decisions
    return None if problems else out


def _conclusion_verdict(raw: str) -> str | None:
    """passed / passed-with-advice / changes-required for a 结论 value, None when it is none of them."""
    return next((code for pattern, code in _VERDICT_FORMS if pattern.match(raw.strip())), None)


def _item_ref(value: str | None) -> int | None:
    """事项：#N (hub item) or C<N> (the coordinator's own item when there is no hub, v2.0 draft)."""
    m = _CREW_RE.match((value or "").strip())
    return int(m.group(1)) if m else _number(value)


def split_sections(text: str) -> list[str]:
    """One message holding several 【审查结论】 sections, cut at each bare tag line; one section stays whole."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    starts = [i for i, line in enumerate(lines) if line.strip() == "【审查结论】"]
    if len(starts) <= 1:
        return [text]
    cut = [0] + starts[1:] + [len(lines)]
    return ["\n".join(lines[a:b]).rstrip("\n") + "\n" for a, b in zip(cut, cut[1:])]


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
    elif kind == "wait-user":
        if not end.present:
            problems.append("missing-end")
        _require(fields, ("来自", "要你决定"), problems)
        options, recommended = _options(fields.get("选项与我的建议", ""))
        if not options:
            problems.append("missing-options")
        stopped = _stop_flag(fields, problems)
        hints += [f"no-consequence:{o['letter']}" for o in options if o["consequence"] is None]
        if options and recommended is None:
            hints.append("no-recommendation")
        if _brief_thin(fields.get("要点")):
            hints.append("brief-thin")
        in_scope: list[str] = []
        scopes: dict[str, str] = {}
        if fields.get("适用会话", "").strip():
            in_scope = [x for x in _SESSION_SEP.split(fields["适用会话"].strip()) if x]
            if not fields.get("各线范围", "").strip():
                problems.append("missing-field:各线范围")
            else:
                scopes = _scopes(fields["各线范围"])
                problems += [f"scope-missing:{n}" for n in in_scope if not scopes.get(n, "").strip()]
                problems += [f"scope-unknown:{n}" for n in scopes if n not in in_scope]
        extra = {"options": options, "recommended": recommended, "suggestedReply": fields.get("你该回") or None,
                 "fullyStopped": stopped, "linesInScope": in_scope, "scopes": scopes,
                 "reviewLine": _review_line(fields.get("架构审查"))}
    elif kind == "review-request":
        if not end.present:
            problems.append("missing-end")
        node = REVIEW_NODES.get(fields.get("节点", "").strip())
        required = ("模块", "节点", "文件", "要点") + (("改动统计", "越界检查") if node == "final" else ())
        _require(fields, required, problems)
        if fields.get("节点", "").strip() and node is None:
            problems.append("bad-node")
        files, bad_line = [], False
        for line in _lines(fields.get("文件")):
            m = _FILE_LINE_RE.match(line)
            if m:
                files.append({"path": m.group(1), "fingerprint": m.group(2)})
            else:
                bad_line = True
        if bad_line:
            problems.append("bad-file-line")
        if fields.get("要点", "").strip() and _brief_thin(fields["要点"]):
            hints.append("brief-thin")
        extra = {"submission": {"module": fields.get("模块", "").strip() or None, "node": node, "files": files}}
        if "不同意" in fields:
            m = _DISAGREE_RE.match(fields["不同意"].strip())
            if m:
                extra["submission"]["disagree"] = {"ref": m.group(1), "reason": m.group(2).strip()}
            else:
                problems.append("bad-disagree")
    elif kind == "shared-change-request":
        if not end.present:
            problems.append("missing-end")
        _require(fields, ("来自", "文件", "改什么", "为什么"), problems)
        stopped = _stop_flag(fields, problems)
        extra = {"fullyStopped": stopped, "changeRequest": {"files": _lines(fields.get("文件"))}}
    elif kind == "coordination-notice":
        _require(fields, ("类型", "依据", "要你做什么"), problems)
        raw_kind = fields.get("类型", "").strip()
        notice_kind = NOTICE_KINDS.get(raw_kind)
        if raw_kind and notice_kind is None:
            problems.append("bad-notice-kind")
        basis = fields.get("依据", "")
        refs = [int(x) for x in _NUM_RE.findall(basis)]
        if notice_kind == "suspend":
            _require(fields, ("原因",), problems)
        if notice_kind in NEED_REF and not (refs or _CREW_RE.search(basis)):
            problems.append("missing-approval-ref")
        extra = {"notice": {"kind": notice_kind, "refs": refs}}
        if notice_kind == "rework":
            if basis.strip() and not _REVIEW_ID_RE.search(basis):
                problems.append("missing-review-ref")
            raw_round = fields.get("轮次", "").strip()
            if not raw_round:
                problems.append("missing-field:轮次")
            elif not raw_round.isdigit() or int(raw_round) < 1:
                problems.append("bad-round")
            else:
                extra["notice"]["round"] = int(raw_round)
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
    elif kind == "review-conclusion":
        extra = {"conclusion": _conclusion(fields, problems, hints)}
    elif kind == "user-reply":
        item = _item_ref(fields.get("事项"))
        if item is None:
            problems.append("missing-field:事项")
        _require(fields, ("用户原话", "答复时间"), problems)
        if "多线事项" in fields.get("事项", ""):
            _require(fields, ("适用于你的范围", "原事项全文"), problems)
        relayed, relay_msg = None, None
        if "转自" in fields:
            raw = fields["转自"].strip()
            hub, owner = _RELAY_HUB_RE.match(raw), _RELAY_OWNER_RE.match(raw)
            if hub:
                relayed, relay_msg = "hub", int(hub.group(1))
            elif owner:
                relayed, relay_msg = "owner", int(owner.group(2))
            else:
                problems.append("bad-relay-source")
            if relayed == "owner":
                _require(fields, ("转交范围",), problems)
            extra = {"origin": {"originals": _originals(fields.get("事项")), "relayedFrom": relayed,
                                "relayMessage": relay_msg}}
    elif kind == "owner-handoff":
        item = _number(fields.get("事项"))
        if item is None:
            problems.append("missing-field:事项")
        _require(fields, ("来自", "用户原话", "答复时间", "转交范围"), problems)
        extra = {"origin": {"originals": _originals(fields.get("事项")), "relayedFrom": None, "relayMessage": None}}

    return Message(kind=kind, supported=kind not in UNSUPPORTED, problems=tuple(problems), hints=tuple(hints),
                   fields=fields, end=end, reply_to=reply_to, markers=tuple(markers), item=item, extra=extra)


# ---------------------------------------------------------------- rendering

def _as_parsed(value: str) -> str:
    """What a field value reads back as: first line trimmed, trailing blank lines dropped (contract section 2)."""
    lines = value.split("\n")
    lines[0] = lines[0].strip()
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _self_check(text: str, kind: str, expected: dict[str, str]) -> str:
    msg = parse(text)
    if msg.kind != kind or not msg.ok:
        raise ValueError(f"生成的消息不合格：{', '.join(msg.problems) or msg.kind}")
    for name, value in expected.items():
        if msg.fields.get(name) != _as_parsed(value):
            raise ValueError(f"「{name}」里有会被读成其他字段的行，不能原样发出")
    return text


def render_user_reply(item: int, original: str, answered_at: str, option_text: str | None = None,
                      source_relay_id: int | None = None, originals: list[int] | None = None,
                      relay: str | None = None, scope: str | None = None, crew: bool = False) -> str:
    """【用户答复】 from the coordinator; the user's words are copied unchanged.

    v1.6 relay: `originals` lists every message of the recipient this hub item covers, `relay` is the
    「转自」 line (收件枢纽，消息 #R / <短名>（负责人转交），消息 #R) and `scope` the handed-over scope.
    `crew` marks `item` as the coordinator's own number (C<N>, no hub involved) rather than a hub item #N."""
    if not isinstance(item, int) or isinstance(item, bool) or item < 1:
        raise ValueError(f"事项编号必须是正整数：{item!r}")
    if not isinstance(original, str) or not original.strip():
        raise ValueError("用户原话不能为空")
    if not answered_at or not answered_at.strip():
        raise ValueError("答复时间不能为空")
    refs = [int(x) for x in originals] if originals else ([] if source_relay_id is None else [int(source_relay_id)])
    ref = (f"C{item}" if crew else f"#{item}") + (f"（你的原消息 {'、'.join(f'#{n}' for n in refs)}）" if refs else "")
    lines = ["【用户答复】", f"事项：{ref}"] + ([f"转自：{relay}"] if relay else []) + [f"用户原话：{original}"]
    expected = {"用户原话": original, "答复时间": answered_at}
    if option_text is not None:
        m = _OPTION_RE.match(option_text.strip())
        if not m:
            raise ValueError(f"选项原文必须以选项字母开头：{option_text!r}")
        lines.append(f"选项 {m.group(2)} 原文：{option_text}")
        expected["选项原文"] = option_text
    lines.append(f"答复时间：{answered_at}")
    if scope is not None:
        lines.append(f"转交范围：{scope}")
        expected["转交范围"] = scope
    return _self_check("\n".join(lines) + "\n", "user-reply", expected)


def render_resumed(items: list[int], note: str) -> str:
    """【已恢复】 closing the given items (e.g. a hub item after its answer was relayed to every module)."""
    text = "【已恢复】\n结束：" + "、".join(f"#{int(n)}" for n in items) + "\n" + note.strip() + "\n"
    msg = parse(text)
    if msg.kind != "resumed" or not msg.ok:
        raise ValueError(f"生成的消息不合格：{', '.join(msg.problems) or msg.kind}")
    return text


def render_coordination_notice(kind: str, basis: str, todo: str, reason: str | None = None, round: int | None = None) -> str:
    """【协调通知】 from the coordinator; not an approval, never asks for a reply."""
    labels = {code: label for label, code in NOTICE_KINDS.items()}
    if kind not in labels:
        raise ValueError(f"通知类型只能是 {'／'.join(labels)}：{kind!r}")
    for name, value in (("依据", basis), ("要你做什么", todo)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"「{name}」不能为空")
    if kind in NEED_REF and not (_NUM_RE.search(basis) or _CREW_RE.search(basis)):
        raise ValueError("开工、退回、挂起、恢复、撤销批准类通知的「依据」必须写明批准事项编号（#N 或 C<N>）")
    if (kind == "rework") != (round is not None):
        raise ValueError("「轮次」只用于返工类，且返工类必填")
    if kind == "rework" and (not isinstance(round, int) or round < 1 or not _REVIEW_ID_RE.search(basis)):
        raise ValueError("返工类的「轮次」必须是正整数，「依据」必须写审查编号（R-N）")
    if (kind == "suspend") != bool(reason and reason.strip()):
        raise ValueError("「原因」只用于挂起类，且挂起类必填")
    head = ["【协调通知】", f"类型：{labels[kind]}"] + ([f"原因：{reason}"] if kind == "suspend" else [])
    text = "\n".join(head + [f"依据：{basis}"] + ([f"轮次：{round}"] if kind == "rework" else [])
                     + [f"要你做什么：{todo}"]) + "\n"
    expected = {"依据": basis, "要你做什么": todo, **({"原因": reason} if kind == "suspend" else {})}
    return _self_check(text, "coordination-notice", expected)
