# Todo: crew-stall-signals

测试命令：`python3 -m unittest discover -s tests -v`

- [x] Task 1：提交事实与开工时间（`startedAt`、`commits`）
  - 验收：Spec 验收 1、2、3
  - 文件：`module_crew/stall.py`、`module_crew/failure.py`、`tests/test_stall_signals.py`

- [ ] Task 2：问过你、合并退回、等待用户（`asks`、`returns`、`waitUser`）
  - 验收：Spec 验收 4、5、6、7
  - 文件：`module_crew/stall.py`、`module_crew/failure.py`、`tests/test_stall_signals.py`

- [ ] Checkpoint 1（report）：新字段齐全；现有 sessions 契约测试原样通过、状态库读不到仍退出 2（验收 8）

- [ ] Task 3：人看的 `sessions` 与 `status`；crew-hub-bridge 契约一句与变更记录；README 第 121 行
  - 验收：Spec 验收 9
  - 文件：`module_crew/failure.py`、`module_crew/probe.py`、`spec/crew-hub-bridge.md`、`README.md`、`tests/test_stall_signals.py`

- [ ] Checkpoint 2（gate）：模块最终验收——全量测试全绿（验收 10）、验收逐条对应测试、改动文件清单与提交号
