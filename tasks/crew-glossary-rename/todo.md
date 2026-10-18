# Todo: crew-glossary-rename

测试命令：`python3 -m unittest discover -s tests -v`

- [x] Task 1：旧称扫描测试（先失败）——改名前命中 255 处（含「收件枢纽」与「枢纽」重复计数），暂标 expectedFailure，Task 5 去掉
  - 验收：Spec 验收 1（护栏）
  - 文件：`tests/test_glossary.py`

- [x] Task 2：等待记录 W 前缀
  - 验收：Spec 验收 3
  - 文件：`module_crew/refs.py`、显示等待记录编号的模块、`module_crew/__main__.py`、`tests/test_refs.py`

- [x] Task 3：代码字符串改名
  - 验收：Spec 验收 1（代码部分）、2、5
  - 文件：`module_crew/*.py`（不含 `protocol.py`）、受影响的现有测试

- [x] Checkpoint 1（report）：代码部分扫描通过、契约一致性测试通过、`protocol.py` 无改动、全量测试通过（2026-10-19：代码部分命中 0；`git diff 8ba90d7 -- module_crew/protocol.py` 为空；全量 402 个测试通过；豁免新增两条：契约「转自」字段的两种取值、宿主状态名「等待审批」；「已恢复：<会话>（重新占名额）」实为取消挂起，改为「已取消挂起」而非「已结项」）

- [ ] Task 4：三份 SKILL.md 改名
  - 验收：Spec 验收 1（skill 部分）、4、5
  - 文件：`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`codex-skills/crew-dev/SKILL.md`、`tests/test_skills.py`

- [ ] Task 5：README、命令帮助与版本 0.4.0
  - 验收：Spec 验收 1、6
  - 文件：`README.md`、`module_crew/__main__.py`、`.claude-plugin/plugin.json`、`.codex-plugin/plugin.json`、`interface.json`

- [ ] Checkpoint 2（gate）：模块最终验收（0.4.0）——全量测试、验收逐条证据、改动文件清单、需求逐项勾清单
