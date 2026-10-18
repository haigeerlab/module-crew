"""module-crew's own numbers as users and messages see them: C<N> (contract v2.0 draft, R6).

The store keeps plain integers; only text shown to people or sent to other sessions carries the prefix,
so a crew number can never be mistaken for a decision-hub item (#N).
"""

from __future__ import annotations

import argparse
import re

_RE = re.compile(r"^[CcWw]?\s*(\d+)$")


def fmt(n: int) -> str:
    return f"C{int(n)}"


def wait(n: int) -> str:
    """A wait record (store kind `ticket`) is shown as W<N> (glossary v1.1); the number comes from the same counter."""
    return f"W{int(n)}"


def parse(value: str) -> int:
    """「15」, 「C15」 or 「W15」 (any case); anything else, including a hub-style 「#15」, is refused."""
    m = _RE.match(str(value).strip())
    if not m or int(m.group(1)) < 1:
        raise argparse.ArgumentTypeError(f"编号写 C15、W15 或 15：{value!r}")
    return int(m.group(1))
