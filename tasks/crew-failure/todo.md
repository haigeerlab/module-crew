# Todo: crew-failure

测试命令：`python3 -m unittest discover -s tests -v`

- [x] Task 1：`suspend`／`resume` 与 crew-start 空位修订
  - 验收：Spec 验收 1、2、3；验收 9 的空位部分
  - 验证：`python3 -m unittest discover -s tests -p "test_failure.py" -v`，再跑 `test_start_*.py`
  - 文件：`module_crew/failure.py`、`module_crew/start.py`、`tests/test_failure.py`

- [x] Task 2：`sessions`
  - 验收：Spec 验收 4
  - 验证：同上
  - 文件：`module_crew/failure.py`、`tests/test_failure.py`

- [x] Task 3：`resume-kit`
  - 验收：Spec 验收 5
  - 验证：同上
  - 文件：`module_crew/failure.py`、`tests/test_failure.py`

- [x] Checkpoint 1（report）：全部测试全绿，记下命令与结果后继续
  - 记录：`python3 -m unittest discover -s tests -v` → Ran 206 tests in 95.563s OK（2026-10-18）

- [x] Task 4：`serial` 与 crew-start 拒绝开新模块
  - 验收：Spec 验收 6；验收 9 的 serial 部分
  - 验证：同上
  - 文件：`module_crew/failure.py`、`module_crew/start.py`、`tests/test_failure.py`

- [x] Task 5：跨模块互不拖累
  - 验收：Spec 验收 7
  - 验证：同上
  - 文件：`tests/test_failure.py`

- [x] Task 6：命令行、两份 skill、crew-start 变更记录
  - 验收：Spec 验收 8、9
  - 验证：`python3 -m unittest discover -s tests -v`
  - 文件：`module_crew/__main__.py`、`skills/crew-coordinator/SKILL.md`、`skills/crew-dev/SKILL.md`、`tests/test_skills.py`、`tests/test_failure.py`、`spec/crew-start.md`

- [ ] Checkpoint 2（gate）：模块最终验收——全部测试全绿、9 条验收标准逐条对应测试、附 `sessions` 与恢复说明样例、附 crew-start 变更记录复审、列出实际改动文件；停下等用户确认
