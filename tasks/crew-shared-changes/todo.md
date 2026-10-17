# Todo: crew-shared-changes

测试命令：`python3 -m unittest discover -s tests -v`

- [x] Task 1：`change add` 与 `change list`
  - 验收：Spec 验收 1、2、3、4
  - 验证：`python3 -m unittest discover -s tests -p test_changes.py -v`
  - 文件：`module_crew/changes.py`、`tests/test_changes.py`

- [x] Task 2：`change answer`
  - 验收：Spec 验收 8
  - 验证：同上
  - 文件：`module_crew/changes.py`、`tests/test_changes.py`

- [x] Checkpoint 1（report）：全部测试全绿，记下命令与结果后继续
  - 记录：`python3 -m unittest discover -s tests -v` → Ran 154 tests in 51.698s OK（2026-10-18）；任务 1、2 测试在同一文件，一并提交

- [x] Task 3：`change land`
  - 验收：Spec 验收 5、6、7
  - 验证：同上
  - 文件：`module_crew/changes.py`、`tests/test_changes.py`

- [x] Task 4：命令行与协调会话 skill
  - 验收：Spec 验收 9
  - 验证：`python3 -m unittest discover -s tests -p "test_[cs]*.py" -v`
  - 文件：`module_crew/__main__.py`、`skills/crew-coordinator/SKILL.md`、`tests/test_skills.py`、`tests/test_changes.py`

- [x] Checkpoint 2（gate）：模块最终验收——全部测试全绿、9 条验收标准逐条对应测试、列出实际改动文件并贴出 skill 改动；停下等用户确认
  - 记录：160 个测试全绿（连跑 3 次）；6 个文件 +471/−7；用户 2026-10-18 验收通过

## 记录

- 2026-10-18 spec-guard 负责人通知 map-startable 已实现并验收（0.68.0 发版），输出与夹具一致；细节：Build order 第一个未完成模块算 in_progress，不进 startable.modules；`paths` 取较具体路径，`apps/bill/` 与 `apps/billing/` 不算重叠。
