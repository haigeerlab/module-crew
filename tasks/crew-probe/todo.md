# Todo: crew-probe

测试命令：`python3 -m unittest discover -s tests -v`

- [x] Task 1：依赖定位与接口版本
  - 验收：Spec 验收 1、2（项目级优先；只装在别的项目；接口 2.0 ok，1.0／3.0／缺失／坏 JSON 各有原因）；目录 marketplace 读源码目录
  - 验证：`python3 -m unittest discover -s tests -p test_probe_deps.py -v`
  - 文件：`module_crew/probe.py`、`tests/helpers.py`、`tests/fixtures/plugins/**`、`tests/test_probe_deps.py`

- [x] Task 2：`/map --json` 运行、命令安全与规划层判据
  - 验收：Spec 验收 3、4
  - 验证：`python3 -m unittest discover -s tests -p test_probe_map.py -v`
  - 文件：`module_crew/probe.py`、`tests/fixtures/plugins/**`、`tests/test_probe_map.py`

- [x] Task 3：git 与集成基线
  - 验收：Spec 验收 5、6
  - 验证：`python3 -m unittest discover -s tests -p test_probe_repo.py -v`
  - 文件：`module_crew/probe.py`、`tests/test_probe_repo.py`

- [x] Checkpoint 1（report）：全部测试全绿，记下命令与结果后继续
  - 记录：`python3 -m unittest discover -s tests -v` → Ran 78 tests in 12.089s OK（2026-10-18）

- [ ] Task 4：状态库汇总与 `run()` 报告
  - 验收：Spec 验收 7、9
  - 验证：`python3 -m unittest discover -s tests -p test_probe_status.py -v`
  - 文件：`module_crew/probe.py`、`tests/test_probe_status.py`

- [ ] Task 5：`status` 命令与 `--json`
  - 验收：Spec 验收 8、9
  - 验证：同上
  - 文件：`module_crew/__main__.py`、`tests/test_probe_status.py`

- [ ] Task 6：本机真实环境冒烟
  - 验收：Spec 验收 10；输出原样记入本 todo
  - 验证：`bin/module-crew status; echo $?`
  - 文件：`tasks/crew-probe/todo.md`

- [ ] Checkpoint 2（gate）：模块最终验收——全部测试全绿、10 条验收标准逐条对应测试、列出实际改动文件；停下等用户确认

## 记录

- 2026-10-18 spec-guard 负责人回复 1.1 字段（打算，未定稿，以 map-startable／checkout-role／crew-interface 三份 Spec 获批为准）：`/map --json` 顶层 `moduleConcurrency: "on"`（off 时新字段全部不出现）、`buildOrderGroups: [[..]]`、`startable: {modules, conflicts: [{modules, paths}]}`、模块 `scope`、`worktree`；interface 1.1 加 `scopeCheck`、`reviewMark`、`checkoutRole`；发 0.68.0。夹具已按此写，规划层判据拆成「未发版／开关没开／缺 startable」三种原因。
