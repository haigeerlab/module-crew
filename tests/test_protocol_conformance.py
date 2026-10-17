"""Run the pinned session-protocol fixtures against module_crew.protocol."""

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from module_crew import protocol

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "session-protocol" / "v1.3"

# Types this plugin parses / generates (spec 假设 2、3). Everything else is skipped and listed.
PARSED = {"review-request", "shared-change-request", "coordination-notice", "wait-user", "wait-session", "resumed", "withdraw", "user-reply", "unknown"}
GENERATED = {"user-reply"}
# Fixtures whose expectation the contract itself must fix; skipped with a reason, never silently.
CONTRACT_DEFECTS: dict[str, str] = {}


def verify_sums(root: Path) -> list[str]:
    """Return the problems found when checking root/SHA256SUMS; empty means every file matches."""
    problems = []
    listed = set()
    for line in (root / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split(None, 1)
        name = name.strip().removeprefix("./")
        listed.add(name)
        path = root / name
        if not path.exists():
            problems.append(f"missing {name}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"changed {name}")
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        if path.is_file() and rel not in ("SHA256SUMS", "SOURCE") and rel not in listed:
            problems.append(f"unlisted {rel}")
    return problems


def cases():
    for exp in sorted(FIXTURES.glob("*/*.json")):
        yield exp.parent.name + "/" + exp.stem, exp.with_suffix(".txt"), json.loads(exp.read_text())


def diff(expected, actual, path="parse"):
    if isinstance(expected, dict) and isinstance(actual, dict):
        out = []
        for key, value in expected.items():
            out += diff(value, actual.get(key, "<missing>"), f"{path}.{key}")
        return out
    return [] if expected == actual else [f"{path}: expected {expected!r}, got {actual!r}"]


class FingerprintTest(unittest.TestCase):
    def test_pinned_fixtures_match_sums(self):
        self.assertEqual(verify_sums(FIXTURES), [])
        self.assertIn("commit: 42fe5f6", (FIXTURES / "SOURCE").read_text())

    def test_one_changed_byte_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "v1.3"
            shutil.copytree(FIXTURES, copy)
            target = copy / "withdraw" / "basic.txt"
            data = bytearray(target.read_bytes())
            data[-2] ^= 1
            target.write_bytes(bytes(data))
            self.assertEqual(verify_sums(copy), ["changed withdraw/basic.txt"])


class ConformanceTest(unittest.TestCase):
    def test_parse_fixtures(self):
        skipped, checked = [], 0
        for name, txt, doc in cases():
            if "parse" not in doc:
                continue
            kind = doc["parse"]["type"]
            if name in CONTRACT_DEFECTS:
                skipped.append(f"{name} (contract defect: {CONTRACT_DEFECTS[name]})")
                continue
            if kind not in PARSED:
                skipped.append(name)
                continue
            checked += 1
            with self.subTest(fixture=name):
                actual = protocol.parse(txt.read_text(encoding="utf-8")).contract()
                problems = diff(doc["parse"], actual)
                self.assertEqual(problems, [], "\n".join(problems))
        print(f"\n  parse checked: {checked}; skipped: {', '.join(skipped) or 'none'}", file=sys.stderr)
        self.assertEqual(checked, 41)


class GenerateConformanceTest(unittest.TestCase):
    def test_generate_fixtures(self):
        skipped, checked = [], 0
        for name, txt, doc in cases():
            gen = doc.get("generate")
            if gen is None:
                continue
            if gen["kind"] not in GENERATED:
                skipped.append(name)
                continue
            checked += 1
            i = gen["inputs"]
            with self.subTest(fixture=name):
                out = protocol.render_user_reply(item=i["item"], original=i["original"], answered_at=i["answeredAt"],
                                                 option_text=i["optionText"], source_relay_id=i["sourceRelayId"])
                self.assertEqual(out, txt.read_text(encoding="utf-8"))
        print(f"\n  generate checked: {checked}; skipped: {', '.join(skipped)}", file=sys.stderr)
        self.assertEqual(checked, 2)


class UnsupportedKindsTest(unittest.TestCase):
    def test_review_conclusion_and_answer_notice_are_recognised_not_judged(self):
        for name in ("review-conclusion/bad-node", "review-conclusion/basic", "answer-notice/basic"):
            with self.subTest(name):
                msg = protocol.parse((FIXTURES / f"{name}.txt").read_text(encoding="utf-8"))
                self.assertEqual(msg.kind, name.split("/")[0])
                self.assertFalse(msg.supported)
                self.assertEqual(msg.problems, ())


if __name__ == "__main__":
    unittest.main()
