# Todo: crew-glossary-rename

测试命令：`python3 -m unittest discover -s tests -v`

- [ ] Task 1：旧称扫描测试（先失败）
  - 验收：Spec 验收 1（护栏）
  - 文件：`tests/test_glossary.py`

- [ ] Task 2：等待记录 W 前缀
  - 验收：Spec 验收 3
  - 文件：`module_crew/refs.py`、显示等待记录编号的模块、`module_crew/__main__.py`、`tests/test_refs.py`

- [ ] Task 3：代码字符串改名
  - 验收：Spec 验收 1（代码部分）、2、5
  - 文件：`module_crew/*.py`（不含 `protocol.py`）、受影响的现有测试

- [ ] Checkpoint 1（report）：代码部分扫描通过、契约一致性测试通过、`protocol.py` 无改动、全量测试通过

- [ ] Task 4：三份 SKILL.md 改名
  - 验收：Spec 验收 1（skill 部分）、4、5
  - 文件：`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`tests/test_skills.py`

- [ ] Task 5：README、命令帮助与版本 0.4.0
  - 验收：Spec 验收 1、6
  - 文件：`README.md`、`module_crew/__main__.py`、`.claude-plugin/plugin.json`、`.codex-plugin/plugin.json`、`interface.json`

- [ ] Checkpoint 2（gate）：模块最终验收（0.4.0）——全量测试、验收逐条证据、改动文件清单、需求逐项勾清单
