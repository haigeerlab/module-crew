"""crew-glossary-rename: text people read uses the names of glossary v1.1 (spec/crew-glossary-rename.md acceptance 1).

Contract tags (【…】) and contract field names keep their contract spelling and are stripped before scanning;
code identifiers are not strings people read, and docstrings are developer notes in English.
"""

import ast
import re
import unittest

from helpers import PLUGIN_ROOT

from module_crew import protocol

OLD_TERMS = ["协调会话", "并行协调", "收件枢纽", "枢纽", "总协调", "负责人", "审查会话", "身份名", "短名", "合批",
             "待用户决定", "适用会话", "等待单", "用户答复", "已恢复", "协调通知", "批准来源", "登记来源", "开工原话",
             "集成基线", "评审标记", "评审", "审核", "审批"]

# (pattern, reason): text that legitimately contains an old term
ALLOWED = [
    (r"评审节奏", "术语表 v1.1 的正式名称（reviewCadence）"),
    (r"插件负责人|契约负责人", "术语表：只指开发插件或契约的会话，出现在给开发者的说明里"),
    (r"可信批准来源", "新名称本身包含旧称「批准来源」"),
    (r"契约标签【[^】]*】", "契约标签照契约原样写"),
    (r"「等待审批」", "宿主与 agent-relay 在线状态里显示的状态名，不是 module-crew 的术语"),
    (r"「你是协调会话」", "skill 触发词：用户可能还这样称呼，保留旧说法才能触发"),
    (r"字段名[：:]\s*[^\s，。；）)]+", "契约字段名照契约原样写"),
    (r"「(待用户决定|适用会话)」字段", "契约字段名照契约原样写"),
    (r"收件枢纽\s*[，,]\s*消息\s*#|（负责人转交）\s*[，,]\s*消息\s*#", "契约 v2.1「转自」字段只认这两种取值（protocol._RELAY_*_RE）"),
]
FIELD_NAMES = sorted({f for fields in protocol.FIELDS.values() for f in fields}, key=len, reverse=True)


def readable_strings(path) -> str:
    """String constants in a module, without docstrings."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))
            and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    return "\n".join(n.value for n in ast.walk(tree)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs)


def strip_contract(text: str) -> str:
    for pattern, _ in ALLOWED:
        text = re.sub(pattern, "", text)
    text = re.sub(r"【[^】]*】", "", text)
    for name in FIELD_NAMES:
        text = re.sub(rf"(^|\n|\s){re.escape(name)}\s*[：:]", r"\1", text)
    return text


def sources() -> dict[str, str]:
    out = {rel: (PLUGIN_ROOT / rel).read_text(encoding="utf-8")
           for rel in ("README.md", "docs/guide.md", "docs/commands.md", "docs/architecture.md")}
    for p in sorted(PLUGIN_ROOT.glob("*skills/*/SKILL.md")):
        out[str(p.relative_to(PLUGIN_ROOT))] = p.read_text(encoding="utf-8")
    for p in sorted((PLUGIN_ROOT / "module_crew").glob("*.py")):
        if p.name != "protocol.py":
            out[f"module_crew/{p.name}"] = readable_strings(p)
    return out


def hits(names: list[str] | None = None) -> list[str]:
    found = []
    for name, text in sources().items():
        if names is not None and not any(name.startswith(n) for n in names):
            continue
        clean = strip_contract(text)
        for term in OLD_TERMS:
            for m in re.finditer(re.escape(term), clean):
                found.append(f"{name}：{term}：…{clean[max(0, m.start() - 20):m.end() + 20]}…".replace("\n", " "))
    return found


class GlossaryTest(unittest.TestCase):
    def test_no_old_terms(self):
        found = hits()
        self.assertEqual(found, [], f"{len(found)} 处旧称：\n" + "\n".join(found[:80]))

    def test_every_allowance_has_a_reason(self):
        for pattern, reason in ALLOWED:
            self.assertTrue(reason.strip(), pattern)


if __name__ == "__main__":
    unittest.main()
