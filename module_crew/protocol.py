"""Parse and render session-protocol v1.1 messages (see spec/crew-protocol.md).

Pure functions only: no file, git or agent-relay access. Field names, tags and
problem codes follow the contract text in session-protocol PROTOCOL.md.
"""

from __future__ import annotations

from dataclasses import dataclass

CONTRACT_VERSION = "1.1"


@dataclass(frozen=True)
class Message:
    kind: str
    supported: bool
    problems: tuple[str, ...]
    hints: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems

    def contract(self) -> dict:
        return {"type": self.kind, "valid": self.ok}


def parse(text: str) -> Message:
    return Message("unknown", False, ("unknown-kind",), ())
