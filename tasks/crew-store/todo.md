# Todo: crew-store

测试命令：`python3 -m unittest discover -s tests -v`

- [x] Task 1：插件骨架、临时仓库测试工具、包级静态检查
  - 验收：清单是合法 JSON、`name` 为 `module-crew`；`module_crew/` 只 import 标准库；代码里对状态库文件没有 `unlink`／`rmtree`／`truncate`（Spec 验收 14）；`tests/helpers.py` 能建临时仓库与 worktree
  - 验证：`python3 -m unittest discover -s tests -p test_package.py -v`
  - 文件：`.claude-plugin/plugin.json`、`bin/module-crew`、`module_crew/__init__.py`、`module_crew/__main__.py`、`tests/__init__.py`、`tests/helpers.py`、`tests/test_package.py`

- [x] Checkpoint 1（report）：全部测试全绿，记下命令与结果后继续
  - 记录：`python3 -m unittest discover -s tests -v` → Ran 5 tests, OK（2026-10-18）

- [ ] Task 2：定位与 `store init`
  - 验收：Spec 验收 1、2、3、13（权限位；重复 init 不改内容与修改时间；worktree 里定位到同一路径且 `git status` 看不到；非 git 目录或未 init 退出码 2 且不建目录；`meta.json` 版本 2 时读写都拒绝）
  - 验证：`python3 -m unittest discover -s tests -p test_store_init.py -v`
  - 文件：`module_crew/store.py`、`module_crew/__main__.py`、`tests/test_store_init.py`

- [ ] Task 3：事务、编号、事件日志与回滚
  - 验收：Spec 验收 5、10；编号与 `seq` 从日志算出；同一事务内多次 `put` 各一条事件；`events(key=, kind=)` 按 seq 排序
  - 验证：`python3 -m unittest discover -s tests -p test_store_tx.py -v`
  - 文件：`module_crew/store.py`、`tests/test_store_tx.py`

- [ ] Task 4：快照、从日志重建、落后与损坏处理
  - 验收：Spec 验收 6、7（读接口部分）、8、9（读接口与追加部分）
  - 验证：`python3 -m unittest discover -s tests -p test_store_rebuild.py -v`
  - 文件：`module_crew/store.py`、`tests/test_store_rebuild.py`

- [ ] Task 5：多进程并发，跨主 checkout 与 worktree
  - 验收：Spec 验收 4；记录 1000 条时单事务耗时
  - 验证：`python3 -m unittest discover -s tests -p test_store_concurrency.py -v` 连续跑 5 次
  - 文件：`module_crew/store.py`、`tests/test_store_concurrency.py`

- [ ] Checkpoint 2（report）：全部测试全绿，并发测试连续 5 次通过，记下命令与结果后继续

- [ ] Task 6：正文文件
  - 验收：Spec 验收 12 的 `write_body`／`read_body` 部分；回滚时不留正文；目标已存在时旧文件改名 `.orphan-<时间>`
  - 验证：`python3 -m unittest discover -s tests -p test_store_body.py -v`
  - 文件：`module_crew/store.py`、`tests/test_store_body.py`

- [ ] Task 7：会话登记校验
  - 验收：Spec 验收 11
  - 验证：`python3 -m unittest discover -s tests -p test_store_session.py -v`
  - 文件：`module_crew/store.py`、`tests/test_store_session.py`

- [ ] Task 8：`store check`
  - 验收：Spec 验收 3、7、9、12 中 `check` 的输出与退出码；孤立正文报告为警告
  - 验证：`python3 -m unittest discover -s tests -p test_store_check.py -v`
  - 文件：`module_crew/store.py`、`module_crew/__main__.py`、`tests/test_store_check.py`

- [ ] Checkpoint 3（gate）：模块最终验收——全部测试全绿、14 条验收标准逐条对应测试、列出实际改动文件；停下等用户确认
